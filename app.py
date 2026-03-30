#!/usr/bin/env python3
"""
AI Evaluation Framework — Web Dashboard
Run: python app.py
Open: http://localhost:5000
"""

import sys
import json
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template_string, request, jsonify, send_from_directory

import config
from prompts.registry import list_roles, get_prompt, get_test_suite, get_weak_variant, role_info
from evaluators.scorer import run_evaluation
from evaluators.recommender import generate_recommendations
from reports.html_report import generate_html_report
from reports.comparison_report import generate_comparison_report
from results_db import log_run, get_runs

app = Flask(__name__)

_jobs: dict[str, dict] = {}


def _make_eval_runner(role, model_override, prompt_source, job_id):
    """Create a single evaluation run with optional model/prompt overrides."""
    def _run():
        try:
            # Override model if specified
            original_model = config.TARGET_MODEL
            original_deployment = config.TARGET_DEPLOYMENT
            original_prompt_source = config.TARGET_SYSTEM_PROMPT
            if model_override:
                config.TARGET_MODEL = model_override
                config.TARGET_DEPLOYMENT = model_override
            if prompt_source:
                config.TARGET_SYSTEM_PROMPT = prompt_source

            # Clear client cache so new model takes effect
            from evaluators.llm_client import _client_cache
            _client_cache.clear()

            SYSTEM_PROMPT, META = get_prompt(role)
            TEST_CASES = get_test_suite(role)
            _jobs[job_id]["total"] = len(TEST_CASES)

            def on_progress(current, total, test_id):
                _jobs[job_id]["progress"] = current
                _jobs[job_id]["current_test"] = test_id

            report = run_evaluation(
                system_prompt=SYSTEM_PROMPT, test_cases=TEST_CASES,
                prompt_name=META["name"], prompt_version=META["version"],
                domain=META["domain"], role_slug=role, on_progress=on_progress,
            )

            recs = generate_recommendations(report)
            used_model = model_override or config.get_model_display_name()

            if prompt_source == "none":
                report_prompt = "(No system prompt sent — testing deployed model)"
            else:
                report_prompt = SYSTEM_PROMPT

            report_path = generate_html_report(
                report, recs,
                output_path=f"reports/evaluation_report_{role}.html",
                system_prompt=report_prompt,
                model_name=used_model,
                mode=config.MODE,
            )

            judge_cfg = config.get_judge_config()
            _judge_name = f"{judge_cfg['model']} ({judge_cfg['provider']})"

            run_id = log_run(
                report=report, role=role,
                model=used_model,
                judge_model=_judge_name,
                provider=config.TARGET_PROVIDER,
                mode=config.MODE,
                prompt_source=prompt_source or config.TARGET_SYSTEM_PROMPT,
                report_path=report_path,
                run_type="evaluation",
            )

            # Restore originals
            config.TARGET_MODEL = original_model
            config.TARGET_DEPLOYMENT = original_deployment
            config.TARGET_SYSTEM_PROMPT = original_prompt_source
            _client_cache.clear()

            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = {
                "run_id": run_id,
                "grade": report.grade,
                "score": report.overall_pct,
                "report_url": f"/reports/evaluation_report_{role}.html",
                "categories": report.category_scores(),
                "perf": report.perf_summary(),
            }
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["result"] = {"error": str(e)}
    return _run


@app.route("/")
def index():
    roles = []
    for slug in list_roles():
        info = role_info(slug)
        info["has_weak"] = get_weak_variant(slug) is not None
        roles.append(info)
    history = get_runs(limit=50)
    return render_template_string(DASHBOARD_HTML, roles=roles, history=history, config=config)


@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.json
    role = data.get("role", config.EVAL_ROLE)
    run_type = data.get("run_type", "evaluation")
    model = data.get("model", "")
    prompt_source = data.get("prompt_source", "local")

    job_id = f"{run_type}_{role}_{len(_jobs)}"
    _jobs[job_id] = {"status": "running", "progress": 0, "total": 0, "current_test": "", "result": None}

    if run_type == "evaluation":
        thread = threading.Thread(target=_make_eval_runner(role, model, prompt_source, job_id))
    elif run_type == "comparison":
        # A/B comparison with flexible config
        run_a = data.get("run_a", {})
        run_b = data.get("run_b", {})
        thread = threading.Thread(target=_run_comparison(role, run_a, run_b, job_id))
    else:
        return jsonify({"error": "Unknown run_type"}), 400

    thread.daemon = True
    thread.start()
    return jsonify({"job_id": job_id})


def _run_comparison(role, run_a_cfg, run_b_cfg, job_id):
    def _run():
        try:
            from evaluators.llm_client import _client_cache

            TEST_CASES = get_test_suite(role)
            _jobs[job_id]["total"] = len(TEST_CASES) * 2

            # Determine prompts for A and B
            a_prompt_source = run_a_cfg.get("prompt_source", "local")
            b_prompt_source = run_b_cfg.get("prompt_source", "local")
            a_model = run_a_cfg.get("model", "")
            b_model = run_b_cfg.get("model", "")

            # --- Run A ---
            original_model = config.TARGET_MODEL
            original_deployment = config.TARGET_DEPLOYMENT
            original_prompt_src = config.TARGET_SYSTEM_PROMPT

            if a_model:
                config.TARGET_MODEL = a_model
                config.TARGET_DEPLOYMENT = a_model
            config.TARGET_SYSTEM_PROMPT = a_prompt_source
            _client_cache.clear()

            # Get prompt based on source
            if a_prompt_source == "weak" and get_weak_variant(role):
                PROMPT_A, META_A = get_prompt(get_weak_variant(role))
            else:
                PROMPT_A, META_A = get_prompt(role)

            def on_a(current, total, test_id):
                _jobs[job_id]["progress"] = current
                _jobs[job_id]["current_test"] = f"Run A: {test_id}"

            report_a = run_evaluation(
                system_prompt=PROMPT_A, test_cases=TEST_CASES,
                prompt_name=META_A["name"], prompt_version=META_A["version"],
                domain=META_A["domain"], role_slug=role, on_progress=on_a,
            )

            # --- Run B ---
            if b_model:
                config.TARGET_MODEL = b_model
                config.TARGET_DEPLOYMENT = b_model
            else:
                config.TARGET_MODEL = original_model
                config.TARGET_DEPLOYMENT = original_deployment
            config.TARGET_SYSTEM_PROMPT = b_prompt_source
            _client_cache.clear()

            if b_prompt_source == "weak" and get_weak_variant(role):
                PROMPT_B, META_B = get_prompt(get_weak_variant(role))
            else:
                PROMPT_B, META_B = get_prompt(role)

            def on_b(current, total, test_id):
                _jobs[job_id]["progress"] = len(TEST_CASES) + current
                _jobs[job_id]["current_test"] = f"Run B: {test_id}"

            report_b = run_evaluation(
                system_prompt=PROMPT_B, test_cases=TEST_CASES,
                prompt_name=META_B["name"], prompt_version=META_B["version"],
                domain=META_B["domain"], role_slug=role, on_progress=on_b,
            )

            # Restore
            config.TARGET_MODEL = original_model
            config.TARGET_DEPLOYMENT = original_deployment
            config.TARGET_SYSTEM_PROMPT = original_prompt_src
            _client_cache.clear()

            recs = generate_recommendations(report_b)
            a_label = f"{a_model or config.get_model_display_name()} / {a_prompt_source}"
            b_label = f"{b_model or config.get_model_display_name()} / {b_prompt_source}"

            report_path = generate_comparison_report(
                report_a, report_b, recs,
                output_path=f"reports/comparison_report_{role}.html",
                system_prompt_v1=PROMPT_A, system_prompt_v2=PROMPT_B,
                model_name=f"A: {a_label} vs B: {b_label}",
                mode=config.MODE,
            )

            log_run(report=report_a, role=role, model=a_model or config.get_model_display_name(),
                    provider=config.TARGET_PROVIDER, mode=config.MODE,
                    report_path=report_path, run_type="comparison_A",
                    notes=f"A: {a_label}")
            run_id = log_run(report=report_b, role=role, model=b_model or config.get_model_display_name(),
                    provider=config.TARGET_PROVIDER, mode=config.MODE,
                    report_path=report_path, run_type="comparison_B",
                    notes=f"B: {b_label}")

            delta = report_b.overall_pct - report_a.overall_pct
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = {
                "run_id": run_id,
                "a_grade": report_a.grade, "a_score": report_a.overall_pct, "a_label": a_label,
                "b_grade": report_b.grade, "b_score": report_b.overall_pct, "b_label": b_label,
                "delta": round(delta, 1),
                "report_url": f"/reports/comparison_report_{role}.html",
            }
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["result"] = {"error": str(e)}
    return _run


@app.route("/api/status/<job_id>")
def api_status(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/history")
def api_history():
    role = request.args.get("role")
    return jsonify(get_runs(limit=100, role=role))


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.json
    role = data.get("role", config.EVAL_ROLE)
    count = int(data.get("count", 10))
    job_id = f"generate_{role}_{len(_jobs)}"
    _jobs[job_id] = {"status": "running", "progress": 0, "total": 1, "current_test": "Generating...", "result": None}

    def _run():
        try:
            from generate_tests import generate_from_role, save_tests
            test_cases = generate_from_role(role, count=count)
            path = save_tests(test_cases, f"generated/{role}_tests.json")
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["progress"] = 1
            _jobs[job_id]["result"] = {
                "count": len(test_cases),
                "test_cases": test_cases,
                "file_path": path,
            }
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["result"] = {"error": str(e)}

    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/save-test-suite", methods=["POST"])
def api_save_test_suite():
    """Save generated tests as a Python test suite file."""
    data = request.json
    role = data.get("role", "generated")
    test_cases = data.get("test_cases", [])
    merge = data.get("merge", False)

    import tempfile, json as _json
    tmp = Path(tempfile.mktemp(suffix=".json"))
    tmp.write_text(_json.dumps(test_cases), encoding="utf-8")

    try:
        from import_tests import json_to_test_suite, merge_into_existing
        if merge:
            result = merge_into_existing(str(tmp), role)
        else:
            result = json_to_test_suite(str(tmp), role_slug=role, suite_name=f"{role}_generated")
        tmp.unlink()
        return jsonify({"success": True, "path": result})
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/eval-generated", methods=["POST"])
def api_eval_generated():
    """Run evaluation using generated test cases (not saved to file)."""
    data = request.json
    role = data.get("role", config.EVAL_ROLE)
    test_cases = data.get("test_cases", [])
    job_id = f"eval_gen_{role}_{len(_jobs)}"
    _jobs[job_id] = {"status": "running", "progress": 0, "total": len(test_cases), "current_test": "", "result": None}

    def _run():
        try:
            from evaluators.scorer import run_evaluation
            from evaluators.recommender import generate_recommendations
            from reports.html_report import generate_html_report
            from prompts.registry import get_prompt

            SYSTEM_PROMPT, META = get_prompt(role)

            def on_progress(current, total, test_id):
                _jobs[job_id]["progress"] = current
                _jobs[job_id]["current_test"] = test_id

            report = run_evaluation(
                system_prompt=SYSTEM_PROMPT, test_cases=test_cases,
                prompt_name=META["name"], prompt_version=META["version"],
                domain=META["domain"], role_slug=role, on_progress=on_progress,
            )

            recs = generate_recommendations(report)
            judge_cfg = config.get_judge_config()

            report_path = generate_html_report(
                report, recs,
                output_path=f"reports/eval_generated_{role}.html",
                system_prompt=SYSTEM_PROMPT,
                model_name=config.get_model_display_name(),
                judge_model_name=f"{judge_cfg['model']} ({judge_cfg['provider']})",
                mode=config.MODE,
            )

            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = {
                "grade": report.grade,
                "score": report.overall_pct,
                "report_url": f"/reports/eval_generated_{role}.html",
                "categories": report.category_scores(),
                "perf": report.perf_summary(),
            }
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["result"] = {"error": str(e)}

    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/reports/<path:filename>")
def serve_report(filename):
    return send_from_directory("reports", filename)


@app.route("/api/redteam", methods=["POST"])
def api_redteam():
    data = request.json
    role = data.get("role", config.EVAL_ROLE)
    model = data.get("model", "")
    prompt_source = data.get("prompt_source", "local")
    job_id = f"redteam_{role}_{len(_jobs)}"
    _jobs[job_id] = {"status": "running", "progress": 0, "total": 1, "current_test": "Attacking...", "result": None}

    def _run():
        try:
            from evaluators.red_team import run_red_team, generate_red_team_report
            from evaluators.llm_client import _client_cache

            # Apply overrides
            original_model = config.TARGET_MODEL
            original_deployment = config.TARGET_DEPLOYMENT
            original_prompt_src = config.TARGET_SYSTEM_PROMPT
            if model:
                config.TARGET_MODEL = model
                config.TARGET_DEPLOYMENT = model
            config.TARGET_SYSTEM_PROMPT = prompt_source
            _client_cache.clear()

            SYSTEM_PROMPT, META = get_prompt(role)

            results = run_red_team(
                system_prompt=SYSTEM_PROMPT,
                role_slug=role,
            )

            # Restore
            config.TARGET_MODEL = original_model
            config.TARGET_DEPLOYMENT = original_deployment
            config.TARGET_SYSTEM_PROMPT = original_prompt_src
            _client_cache.clear()
            report_path = generate_red_team_report(
                results,
                output_path=f"reports/red_team_{role}.html",
            )

            # Log to history table
            from results_db import log_red_team_run
            log_red_team_run(
                results=results,
                role=role,
                model=model or config.get_model_display_name(),
                provider=config.TARGET_PROVIDER,
                mode=config.MODE,
                prompt_source=prompt_source,
                report_path=report_path,
            )

            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["progress"] = 1
            _jobs[job_id]["result"] = {
                "overall_pass_rate": results["overall_pass_rate"],
                "total_attacks": results["total_attacks"],
                "overview": results["overview"],
                "report_url": f"/reports/red_team_{role}.html",
            }
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["result"] = {"error": str(e)}

    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()
    return jsonify({"job_id": job_id})


# ══════════════════════════════════════════════════════════════════════════

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Evaluation Framework</title>
<style>
  :root {
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #e2e8f0; --text2: #94a3b8; --accent: #38bdf8;
    --green: #22c55e; --yellow: #eab308; --red: #ef4444;
    --orange: #f97316; --purple: #a78bfa;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }
  .container { max-width:1200px; margin:0 auto; padding:2rem; }
  h1 { font-size:1.8rem; text-align:center; margin-bottom:0.25rem; }
  h2 { font-size:1.3rem; margin:2rem 0 1rem; color:var(--accent); border-bottom:2px solid var(--surface2); padding-bottom:0.5rem; }
  .subtitle { text-align:center; color:var(--text2); margin-bottom:2rem; font-size:0.95rem; }

  .panel { background:var(--surface); border-radius:16px; padding:1.5rem 2rem; margin-bottom:1.5rem; }
  .panel-title { font-size:1.1rem; font-weight:700; margin-bottom:1rem; display:flex; align-items:center; gap:0.5rem; }
  .panel-title .icon { font-size:1.2rem; }

  .form-row { display:flex; gap:1rem; align-items:end; flex-wrap:wrap; margin-bottom:0.75rem; }
  .form-group { display:flex; flex-direction:column; gap:0.25rem; flex:1; min-width:180px; }
  .form-group label { font-size:0.75rem; color:var(--text2); font-weight:600; text-transform:uppercase; letter-spacing:0.05em; }
  select, input[type=text] { padding:0.55rem 0.8rem; border-radius:8px; border:1px solid var(--surface2); font-size:0.9rem; font-family:inherit; background:var(--bg); color:var(--text); }
  select:focus, input:focus { outline:none; border-color:var(--accent); }

  .btn { padding:0.6rem 1.2rem; border-radius:8px; border:none; font-size:0.9rem; font-weight:600; cursor:pointer; transition:all 0.2s; font-family:inherit; }
  .btn-primary { background:var(--accent); color:var(--bg); }
  .btn-primary:hover { background:#7dd3fc; }
  .btn-purple { background:var(--purple); color:#fff; }
  .btn-purple:hover { background:#c4b5fd; }
  .btn:disabled { opacity:0.4; cursor:not-allowed; }

  /* Tabs */
  .tabs { display:flex; gap:0; margin-bottom:0; }
  .tab { padding:0.6rem 1.5rem; cursor:pointer; font-weight:600; font-size:0.9rem; color:var(--text2);
    border-bottom:3px solid transparent; transition:all 0.2s; }
  .tab:hover { color:var(--text); }
  .tab.active { color:var(--accent); border-bottom-color:var(--accent); }
  .tab-content { display:none; }
  .tab-content.active { display:block; }

  /* A/B config */
  .ab-grid { display:grid; grid-template-columns:1fr auto 1fr; gap:1rem; align-items:start; }
  .ab-vs { display:flex; align-items:center; justify-content:center; font-size:1.5rem; font-weight:800; color:var(--text2); padding-top:1.5rem; }
  .ab-card { background:var(--bg); border-radius:12px; padding:1.25rem; }
  .ab-card h4 { font-size:0.9rem; margin-bottom:0.75rem; }
  .ab-card.run-a h4 { color:var(--orange); }
  .ab-card.run-b h4 { color:var(--accent); }
  @media(max-width:768px) { .ab-grid { grid-template-columns:1fr; } .ab-vs { padding:0; } }

  /* Progress */
  .progress-area { display:none; margin-top:1rem; }
  .progress-area.active { display:block; }
  .progress-bar-wrap { background:var(--bg); border-radius:8px; height:12px; overflow:hidden; margin:0.5rem 0; }
  .progress-bar { height:100%; background:var(--accent); border-radius:8px; transition:width 0.3s; }
  .progress-text { font-size:0.85rem; color:var(--text2); }

  .result-flash { display:none; margin-top:1rem; padding:1.5rem; border-radius:12px; }
  .result-flash.active { display:block; }
  .result-flash.success { background:rgba(34,197,94,0.1); border:1px solid var(--green); }
  .result-flash.error { background:rgba(239,68,68,0.1); border:1px solid var(--red); }
  .result-grade { font-size:2.5rem; font-weight:800; }
  .result-link { color:var(--accent); text-decoration:none; font-weight:600; }
  .result-link:hover { text-decoration:underline; }

  .history-table { width:100%; border-collapse:collapse; background:var(--surface); border-radius:12px; overflow:hidden; }
  .history-table th { background:var(--surface2); padding:0.65rem 0.8rem; text-align:left; font-size:0.75rem; color:var(--text2); text-transform:uppercase; letter-spacing:0.05em; }
  .history-table td { padding:0.55rem 0.8rem; border-bottom:1px solid var(--surface2); font-size:0.85rem; }
  .history-table tr:hover td { background:var(--surface2); }
  .grade-badge { display:inline-block; padding:0.1rem 0.5rem; border-radius:4px; font-weight:700; font-size:0.85rem; }
  .grade-a { background:var(--green); color:#000; }
  .grade-b { background:var(--yellow); color:#000; }
  .grade-c { background:var(--orange); color:#fff; }
  .grade-d { background:var(--red); color:#fff; }
  a { color:var(--accent); }
  .footer { text-align:center; color:var(--text2); font-size:0.8rem; margin-top:3rem; padding-top:1.5rem; border-top:1px solid var(--surface2); }
</style>
</head>
<body>
<div class="container">

  <h1>AI Evaluation Framework</h1>
  <p class="subtitle">Evaluate, compare, and track AI system prompts</p>
  <div style="display:flex;gap:1rem;justify-content:center;margin-bottom:1.5rem;flex-wrap:wrap">
    <span id="headerTarget" style="background:var(--surface);padding:0.4rem 1rem;border-radius:8px;font-size:0.85rem">
      <span style="color:var(--text2)">Target:</span> <strong>{{ config.TARGET_MODEL }}</strong> <span style="color:var(--text2)">({{ config.TARGET_PROVIDER }})</span>
    </span>
    <span style="background:var(--surface);padding:0.4rem 1rem;border-radius:8px;font-size:0.85rem">
      <span style="color:var(--text2)">Judge:</span> <strong>{{ config.get_judge_config()['model'] }}</strong> <span style="color:var(--text2)">({{ config.get_judge_config()['provider'] }})</span>
    </span>
    <span style="background:{{'var(--green)' if config.MODE == 'live' else 'var(--yellow)'}};color:#000;padding:0.4rem 1rem;border-radius:8px;font-size:0.85rem;font-weight:600">
      {{ config.MODE.upper() }}
    </span>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="switchTab('eval')">Run Evaluation</div>
    <div class="tab" onclick="switchTab('compare')">A/B Comparison</div>
    <div class="tab" onclick="switchTab('redteam')">Red Team</div>
    <div class="tab" onclick="switchTab('generate')">Generate Tests</div>
  </div>

  <!-- ═══ EVALUATION TAB ═══ -->
  <div class="tab-content active" id="tab-eval">
    <div class="panel">
      <div class="panel-title">Single Evaluation</div>
      <div class="form-row">
        <div class="form-group">
          <label>Role</label>
          <select id="evalRole">
            {% for r in roles %}
            <option value="{{ r.slug }}">{{ r.name }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="form-group">
          <label>Model</label>
          <select id="evalModel">
            <option value="">Default ({{ config.TARGET_MODEL }})</option>
            <option value="gpt-4o">gpt-4o</option>
            <option value="gpt-4o-mini">gpt-4o-mini</option>
            <option value="gpt-4.1">gpt-4.1</option>
            <option value="gpt-4.1-mini">gpt-4.1-mini</option>
            <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
            <option value="claude-opus-4-20250514">Claude Opus 4</option>
            <option value="custom">Custom...</option>
          </select>
          <input type="text" id="evalModelCustom" placeholder="Enter model name" style="display:none;margin-top:0.3rem">
        </div>
        <div class="form-group">
          <label>System Prompt</label>
          <select id="evalPrompt">
            <option value="local">Local (from codebase)</option>
            <option value="none">None (test deployed model)</option>
          </select>
        </div>
        <div class="form-group" style="flex:0">
          <label>&nbsp;</label>
          <button class="btn btn-primary" id="btnEval" onclick="runEval()">Run Evaluation</button>
        </div>
      </div>
      <div class="progress-area" id="evalProgress">
        <div class="progress-bar-wrap"><div class="progress-bar" id="evalBar" style="width:0%"></div></div>
        <div class="progress-text" id="evalText">Starting...</div>
      </div>
      <div class="result-flash" id="evalResult"></div>
    </div>
  </div>

  <!-- ═══ COMPARISON TAB ═══ -->
  <div class="tab-content" id="tab-compare">
    <div class="panel">
      <div class="panel-title">A/B Comparison — Compare different models, prompts, or both</div>
      <div class="form-row" style="margin-bottom:1rem">
        <div class="form-group" style="max-width:280px">
          <label>Role (same test suite for both)</label>
          <select id="cmpRole">
            {% for r in roles %}
            <option value="{{ r.slug }}" data-weak="{{ r.has_weak }}">{{ r.name }}</option>
            {% endfor %}
          </select>
        </div>
      </div>
      <div class="ab-grid">
        <div class="ab-card run-a">
          <h4>Run A</h4>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Model</label>
            <select id="cmpModelA">
              <option value="">Default ({{ config.TARGET_MODEL }})</option>
              <option value="gpt-4o">gpt-4o</option>
              <option value="gpt-4o-mini">gpt-4o-mini</option>
              <option value="gpt-4.1">gpt-4.1</option>
              <option value="gpt-4.1-mini">gpt-4.1-mini</option>
              <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
              <option value="claude-opus-4-20250514">Claude Opus 4</option>
              <option value="custom">Custom...</option>
            </select>
            <input type="text" id="cmpModelACustom" placeholder="Enter model name" style="display:none;margin-top:0.3rem">
          </div>
          <div class="form-group">
            <label>System Prompt</label>
            <select id="cmpPromptA">
              <option value="local">Local (full prompt)</option>
              <option value="weak">Weak baseline (v1)</option>
              <option value="none">None (deployed model)</option>
            </select>
          </div>
        </div>
        <div class="ab-vs">VS</div>
        <div class="ab-card run-b">
          <h4>Run B</h4>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Model</label>
            <select id="cmpModelB">
              <option value="">Default ({{ config.TARGET_MODEL }})</option>
              <option value="gpt-4o">gpt-4o</option>
              <option value="gpt-4o-mini">gpt-4o-mini</option>
              <option value="gpt-4.1">gpt-4.1</option>
              <option value="gpt-4.1-mini">gpt-4.1-mini</option>
              <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
              <option value="claude-opus-4-20250514">Claude Opus 4</option>
              <option value="custom">Custom...</option>
            </select>
            <input type="text" id="cmpModelBCustom" placeholder="Enter model name" style="display:none;margin-top:0.3rem">
          </div>
          <div class="form-group">
            <label>System Prompt</label>
            <select id="cmpPromptB">
              <option value="local">Local (full prompt)</option>
              <option value="weak">Weak baseline (v1)</option>
              <option value="none">None (deployed model)</option>
            </select>
          </div>
        </div>
      </div>
      <div style="text-align:center;margin-top:1rem">
        <button class="btn btn-purple" id="btnCompare" onclick="runComparison()">Run A/B Comparison</button>
      </div>
      <div class="progress-area" id="cmpProgress">
        <div class="progress-bar-wrap"><div class="progress-bar" id="cmpBar" style="width:0%"></div></div>
        <div class="progress-text" id="cmpText">Starting...</div>
      </div>
      <div class="result-flash" id="cmpResult"></div>
    </div>
  </div>

  <!-- ═══ RED TEAM TAB ═══ -->
  <div class="tab-content" id="tab-redteam">
    <div class="panel">
      <div class="panel-title">Red Team — Adversarial Security Testing</div>
      <p style="color:var(--text2);margin-bottom:1rem;font-size:0.9rem">
        Tests AI assistant resistance to prompt injection, PHI leakage attempts, encoding attacks, and bias probing.
        Per DCRI TEAM-004: <em>"Execute prompt injection test suite; verify zero PHI leakage."</em>
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>Role to Attack</label>
          <select id="rtRole">
            {% for r in roles %}
            <option value="{{ r.slug }}">{{ r.name }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="form-group">
          <label>Model</label>
          <select id="rtModel">
            <option value="">Default ({{ config.TARGET_MODEL }})</option>
            <option value="gpt-4o">gpt-4o</option>
            <option value="gpt-4o-mini">gpt-4o-mini</option>
            <option value="gpt-4.1">gpt-4.1</option>
            <option value="gpt-4.1-mini">gpt-4.1-mini</option>
            <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
            <option value="claude-opus-4-20250514">Claude Opus 4</option>
            <option value="custom">Custom...</option>
          </select>
          <input type="text" id="rtModelCustom" placeholder="Enter model name" style="display:none;margin-top:0.3rem">
        </div>
        <div class="form-group">
          <label>System Prompt</label>
          <select id="rtPrompt">
            <option value="local">Local (from codebase)</option>
            <option value="none">None (test deployed model)</option>
          </select>
        </div>
        <div class="form-group" style="flex:0">
          <label>&nbsp;</label>
          <button class="btn" style="background:var(--red);color:#fff" id="btnRedTeam" onclick="runRedTeam()">Run Red Team Assessment</button>
        </div>
      </div>
      <div class="progress-area" id="rtProgress">
        <div class="progress-bar-wrap"><div class="progress-bar" id="rtBar" style="width:0%"></div></div>
        <div class="progress-text" id="rtText">Running adversarial attacks...</div>
      </div>
      <div class="result-flash" id="rtResult"></div>
    </div>
  </div>

  <!-- ═══ GENERATE TESTS TAB ═══ -->
  <div class="tab-content" id="tab-generate">
    <div class="panel">
      <div class="panel-title">Generate Synthetic Test Cases</div>
      <p style="color:var(--text2);margin-bottom:1rem;font-size:0.9rem">
        Uses DeepEval Synthesizer to auto-generate test cases from a role's system prompt.
        Generated tests include questions, expected outputs, and draft criteria.
        <strong>Review and edit before using in evaluations.</strong>
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>Role</label>
          <select id="genRole">
            {% for r in roles %}
            <option value="{{ r.slug }}">{{ r.name }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="form-group" style="max-width:120px">
          <label>Count</label>
          <select id="genCount">
            <option value="5">5</option>
            <option value="10" selected>10</option>
            <option value="15">15</option>
            <option value="20">20</option>
          </select>
        </div>
        <div class="form-group" style="flex:0">
          <label>&nbsp;</label>
          <button class="btn btn-primary" id="btnGenerate" onclick="runGenerate()">Generate Test Cases</button>
        </div>
      </div>
      <div class="progress-area" id="genProgress">
        <div class="progress-bar-wrap"><div class="progress-bar" id="genBar" style="width:0%"></div></div>
        <div class="progress-text" id="genText">Generating...</div>
      </div>
      <div class="result-flash" id="genResult"></div>
      <div id="genTestCases" style="display:none;margin-top:1rem">
        <h3 style="color:var(--accent);margin-bottom:0.75rem">Generated Test Cases <span id="genTestCount"></span></h3>
        <div id="genTestList"></div>
        <div style="margin-top:1rem;display:flex;gap:0.5rem">
          <button class="btn" style="background:var(--surface2);color:var(--text)" onclick="downloadGenerated()">Download JSON</button>
          <button class="btn btn-primary" onclick="saveAsTestSuite()">Save as Test Suite</button>
          <button class="btn btn-purple" onclick="runEvalOnGenerated()">Run Evaluation on These</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ HISTORY ═══ -->
  <h2>Evaluation History</h2>
  <div style="display:flex;gap:1rem;align-items:center;margin-bottom:1rem">
    <select id="historyFilter" onchange="filterHistory()" style="background:var(--bg);color:var(--text);padding:0.4rem 0.8rem;border-radius:6px;border:1px solid var(--surface2)">
      <option value="">All Roles</option>
      {% for r in roles %}
      <option value="{{ r.slug }}">{{ r.name }}</option>
      {% endfor %}
    </select>
    <button class="btn" style="background:var(--surface2);color:var(--text);font-size:0.85rem;padding:0.4rem 1rem" onclick="exportCSV()">Export to CSV</button>
  </div>
  <table class="history-table">
    <thead>
      <tr>
        <th>#</th><th>Timestamp</th><th>Role</th><th>Model</th><th>Judge</th><th>Grade</th>
        <th>Score</th><th>Tests</th><th>Latency</th><th>Tokens</th><th>Cost</th>
        <th>Type</th><th>Report</th>
      </tr>
    </thead>
    <tbody id="historyBody">
      {% for run in history %}
      <tr data-role="{{ run.role }}">
        <td>{{ run.id }}</td>
        <td>{{ run.timestamp[:16] }}</td>
        <td style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{{ run.role }}">{{ run.role }}</td>
        <td>{{ run.model or 'demo' }}</td>
        <td>{{ run.judge_model or '-' }}</td>
        <td><span class="grade-badge grade-{{ run.grade[0].lower() if run.grade else 'd' }}">{{ run.grade }}</span></td>
        <td>{{ run.overall_pct }}%</td>
        <td>{{ run.num_tests }}</td>
        <td>{{ '%.1f' % run.avg_latency if run.avg_latency else '-' }}s</td>
        <td>{{ '{:,}'.format(run.total_tokens) if run.total_tokens else '-' }}</td>
        <td>{{ '$%.4f' % run.estimated_cost if run.estimated_cost else '-' }}</td>
        <td>{{ run.run_type }}</td>
        <td>{% if run.report_path %}<a href="/reports/{{ run.report_path.split('/')[-1].split('\\')[-1] }}" target="_blank">View</a>{% else %}-{% endif %}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% if not history %}
  <p style="color:var(--text2);text-align:center;padding:2rem">No evaluation runs yet. Run your first evaluation above.</p>
  {% endif %}

  <div class="footer">
    <p>AI Evaluation Framework — DCRI Clinical Trials Data Management</p>
  </div>
</div>

<script>
// Tabs
function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector(`.tab-content#tab-${tab}`).classList.add('active');
  event.target.classList.add('active');
  setTimeout(updateHeaderTarget, 50);
}

// Custom model inputs + update header
const defaultModel = '{{ config.TARGET_MODEL }}';
const defaultProvider = '{{ config.TARGET_PROVIDER }}';

document.querySelectorAll('select[id*=Model]').forEach(sel => {
  sel.addEventListener('change', () => {
    const custom = document.getElementById(sel.id + 'Custom');
    if (custom) custom.style.display = sel.value === 'custom' ? 'block' : 'none';
    updateHeaderTarget();
  });
});

function updateHeaderTarget() {
  // Show the currently selected model in the active tab
  const activeTab = document.querySelector('.tab-content.active');
  if (!activeTab) return;
  const modelSel = activeTab.querySelector('select[id*=Model]');
  if (!modelSel) return;
  const model = getModel(modelSel.id);
  const display = model || defaultModel;
  document.getElementById('headerTarget').innerHTML =
    `<span style="color:var(--text2)">Target:</span> <strong>${display}</strong> <span style="color:var(--text2)">(${defaultProvider})</span>`;
}

function getModel(selectId) {
  const sel = document.getElementById(selectId);
  if (sel.value === 'custom') {
    return document.getElementById(selectId + 'Custom').value;
  }
  return sel.value;
}

// Run evaluation
function runEval() {
  const role = document.getElementById('evalRole').value;
  const model = getModel('evalModel');
  const prompt = document.getElementById('evalPrompt').value;
  document.getElementById('btnEval').disabled = true;
  showProgress('eval');

  fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, run_type: 'evaluation', model, prompt_source: prompt})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'eval'));
}

// Run comparison
let _generatedTests = [];

function runGenerate() {
  const role = document.getElementById('genRole').value;
  const count = document.getElementById('genCount').value;
  document.getElementById('btnGenerate').disabled = true;
  document.getElementById('genTestCases').style.display = 'none';
  showProgress('gen');
  document.getElementById('genBar').style.width = '50%';
  document.getElementById('genText').textContent = `Generating ${count} test cases for ${role}...`;

  fetch('/api/generate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, count})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'gen'));
}

function downloadGenerated() {
  if (!_generatedTests.length) return;
  const blob = new Blob([JSON.stringify(_generatedTests, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `generated_tests_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function saveAsTestSuite() {
  if (!_generatedTests.length) return;
  const role = document.getElementById('genRole').value;
  fetch('/api/save-test-suite', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, test_cases: _generatedTests, merge: false})
  }).then(r => r.json()).then(d => {
    if (d.success) {
      alert('Test suite saved to: ' + d.path + '\n\nIt will appear in the Role dropdown after restarting the dashboard.');
    } else {
      alert('Error: ' + d.error);
    }
  });
}

function runEvalOnGenerated() {
  if (!_generatedTests.length) return;
  const role = document.getElementById('genRole').value;
  document.getElementById('genResult').className = 'result-flash active success';
  document.getElementById('genResult').innerHTML = '<strong>Running evaluation on generated tests...</strong>';

  fetch('/api/eval-generated', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, test_cases: _generatedTests})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'gen'));
}

function runRedTeam() {
  const role = document.getElementById('rtRole').value;
  const model = getModel('rtModel');
  const prompt = document.getElementById('rtPrompt').value;
  document.getElementById('btnRedTeam').disabled = true;
  showProgress('rt');
  document.getElementById('rtBar').style.width = '30%';

  fetch('/api/redteam', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, model, prompt_source: prompt})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'rt'));
}

function runComparison() {
  const role = document.getElementById('cmpRole').value;
  document.getElementById('btnCompare').disabled = true;
  showProgress('cmp');

  fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      role, run_type: 'comparison',
      run_a: { model: getModel('cmpModelA'), prompt_source: document.getElementById('cmpPromptA').value },
      run_b: { model: getModel('cmpModelB'), prompt_source: document.getElementById('cmpPromptB').value },
    })
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'cmp'));
}

function showProgress(prefix) {
  document.getElementById(prefix + 'Progress').classList.add('active');
  document.getElementById(prefix + 'Result').classList.remove('active');
  document.getElementById(prefix + 'Bar').style.width = '0%';
}

function pollJob(jobId, prefix) {
  const iv = setInterval(() => {
    fetch('/api/status/' + jobId).then(r => r.json()).then(job => {
      if (job.total > 0) {
        const pct = Math.round((job.progress / job.total) * 100);
        document.getElementById(prefix + 'Bar').style.width = pct + '%';
        document.getElementById(prefix + 'Text').textContent =
          `Testing ${job.current_test} (${job.progress}/${job.total})`;
      }
      if (job.status === 'done' || job.status === 'error') {
        clearInterval(iv);
        document.getElementById('btnEval').disabled = false;
        document.getElementById('btnCompare').disabled = false;
        document.getElementById(prefix + 'Progress').classList.remove('active');
        showResult(job, prefix);
        refreshHistory();
      }
    });
  }, 1500);
}

function showResult(job, prefix) {
  const flash = document.getElementById(prefix + 'Result');
  flash.classList.add('active');

  if (job.status === 'error') {
    flash.className = 'result-flash active error';
    flash.innerHTML = `<strong>Error:</strong> ${job.result.error}`;
    return;
  }

  flash.className = 'result-flash active success';
  const r = job.result;

  if (r.test_cases && r.count !== undefined && !r.total_attacks) {
    // Generate result
    _generatedTests = r.test_cases;
    flash.innerHTML = `<strong style="color:var(--green)">Generated ${r.count} test cases!</strong> Review below and download as JSON.`;
    const container = document.getElementById('genTestCases');
    container.style.display = 'block';
    document.getElementById('genTestCount').textContent = `(${r.count})`;
    const list = document.getElementById('genTestList');
    list.innerHTML = r.test_cases.map(tc => `
      <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:0.5rem;border-left:3px solid var(--accent)">
        <div style="display:flex;gap:0.75rem;align-items:center;margin-bottom:0.5rem">
          <span style="font-weight:700;color:var(--accent);font-family:monospace">${tc.id}</span>
          <span style="background:var(--surface2);padding:0.1rem 0.5rem;border-radius:4px;font-size:0.75rem">${tc.category}</span>
          <span style="color:var(--text2);font-size:0.75rem">${tc.criteria.length} criteria | weight: ${tc.weight}x</span>
          ${tc._needs_review ? '<span style="background:var(--orange);color:#000;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600">NEEDS REVIEW</span>' : ''}
        </div>
        <div style="font-size:0.9rem;margin-bottom:0.5rem"><strong>Q:</strong> ${tc.question}</div>
        <details>
          <summary style="cursor:pointer;color:var(--accent);font-size:0.8rem">View criteria${tc._expected_output ? ' & expected output' : ''}</summary>
          <ul style="margin:0.5rem 0 0 1rem;font-size:0.8rem;color:var(--text2)">
            ${tc.criteria.map(c => '<li>' + c + '</li>').join('')}
          </ul>
          ${tc._expected_output ? '<div style="background:var(--surface);padding:0.5rem;border-radius:6px;margin-top:0.5rem;font-size:0.8rem;max-height:200px;overflow-y:auto"><strong>Expected:</strong> ' + tc._expected_output.substring(0,500) + '</div>' : ''}
        </details>
      </div>`).join('');
  } else if (r.total_attacks !== undefined) {
    // Red team result
    const color = r.overall_pass_rate >= 90 ? 'var(--green)' : r.overall_pass_rate >= 70 ? 'var(--yellow)' : 'var(--red)';
    const vulns = Object.entries(r.overview || {}).map(([k,v]) =>
      `<span style="margin-right:1rem"><strong>${k}:</strong> <span style="color:${v.pass_rate>=90?'var(--green)':v.pass_rate>=70?'var(--yellow)':'var(--red)'}">${v.pass_rate}%</span> (${v.passed}/${v.total})</span>`
    ).join('');
    flash.innerHTML = `
      <div style="display:flex;align-items:center;gap:2rem;flex-wrap:wrap">
        <div style="text-align:center">
          <div style="font-size:2.5rem;font-weight:800;color:${color}">${r.overall_pass_rate}%</div>
          <div style="color:var(--text2)">Pass Rate</div>
          <div style="color:var(--text2);font-size:0.8rem">${r.total_attacks} attacks</div>
        </div>
        <div style="font-size:0.9rem">${vulns}</div>
        <a href="${r.report_url}" target="_blank" class="result-link">View Full Report &#8594;</a>
      </div>`;
  } else if (r.delta !== undefined) {
    const color = r.delta > 0 ? 'var(--green)' : 'var(--red)';
    flash.innerHTML = `
      <div style="display:flex;align-items:center;gap:2rem;flex-wrap:wrap">
        <div style="text-align:center">
          <div style="color:var(--orange);font-size:0.8rem;font-weight:600">Run A</div>
          <div style="color:var(--text2);font-size:0.7rem">${r.a_label}</div>
          <div class="result-grade" style="color:${r.a_score>=85?'var(--green)':r.a_score>=70?'var(--yellow)':'var(--red)'}">${r.a_grade}</div>
          <div>${r.a_score}%</div>
        </div>
        <div style="font-size:2rem;color:${color}">&#10132; ${r.delta > 0 ? '+' : ''}${r.delta}%</div>
        <div style="text-align:center">
          <div style="color:var(--accent);font-size:0.8rem;font-weight:600">Run B</div>
          <div style="color:var(--text2);font-size:0.7rem">${r.b_label}</div>
          <div class="result-grade" style="color:${r.b_score>=85?'var(--green)':r.b_score>=70?'var(--yellow)':'var(--red)'}">${r.b_grade}</div>
          <div>${r.b_score}%</div>
        </div>
        <a href="${r.report_url}" target="_blank" class="result-link">View Full Report &#8594;</a>
      </div>`;
  } else {
    const gc = r.grade.startsWith('A') ? 'var(--green)' : r.grade.startsWith('B') ? 'var(--yellow)' : 'var(--red)';
    const perf = r.perf || {};
    flash.innerHTML = `
      <div style="display:flex;align-items:center;gap:2rem;flex-wrap:wrap">
        <div style="text-align:center">
          <div class="result-grade" style="color:${gc}">${r.grade}</div>
          <div>${r.score}%</div>
        </div>
        ${perf.available ? `<div style="color:var(--text2);font-size:0.85rem">
          Latency: ${perf.avg_latency}s avg | ${perf.p95_latency}s p95<br>
          Tokens: ${(perf.total_tokens||0).toLocaleString()} | Cost: $${(perf.estimated_cost_usd||0).toFixed(4)}
        </div>` : ''}
        <a href="${r.report_url}" target="_blank" class="result-link">View Full Report &#8594;</a>
      </div>`;
  }
}

function refreshHistory() {
  fetch('/api/history').then(r => r.json()).then(runs => {
    document.getElementById('historyBody').innerHTML = runs.map(run => `
      <tr data-role="${run.role}">
        <td>${run.id}</td>
        <td>${(run.timestamp||'').substring(0,16)}</td>
        <td style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${run.role}">${run.role}</td>
        <td>${run.model || 'demo'}</td>
        <td>${run.judge_model || '-'}</td>
        <td><span class="grade-badge grade-${(run.grade||'d')[0].toLowerCase()}">${run.grade}</span></td>
        <td>${run.overall_pct}%</td>
        <td>${run.num_tests}</td>
        <td>${run.avg_latency ? run.avg_latency.toFixed(1) + 's' : '-'}</td>
        <td>${run.total_tokens ? run.total_tokens.toLocaleString() : '-'}</td>
        <td>${run.estimated_cost ? '$' + run.estimated_cost.toFixed(4) : '-'}</td>
        <td>${run.run_type}</td>
        <td>${run.report_path ? '<a href="/reports/' + run.report_path.split(/[/\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
      </tr>`).join('');
  });
}

function filterHistory() {
  const role = document.getElementById('historyFilter').value;
  document.querySelectorAll('#historyBody tr').forEach(r => {
    r.style.display = (!role || r.dataset.role === role) ? '' : 'none';
  });
}

function exportCSV() {
  fetch('/api/history').then(r => r.json()).then(runs => {
    const role = document.getElementById('historyFilter').value;
    const filtered = role ? runs.filter(r => r.role === role) : runs;

    const headers = ['ID','Timestamp','Role','Model','Judge Model','Grade','Score %','Tests','Criteria',
      'Avg Latency (s)','P95 Latency (s)','Total Tokens','Est Cost (USD)','Duration (s)','Type','Notes'];
    const rows = filtered.map(r => [
      r.id, r.timestamp, r.role, r.model||'demo', r.judge_model||'-', r.grade, r.overall_pct,
      r.num_tests, r.num_criteria, r.avg_latency||'', r.p95_latency||'',
      r.total_tokens||'', r.estimated_cost||'', r.total_elapsed||'',
      r.run_type, (r.notes||'').replace(/,/g,';')
    ]);

    let csv = headers.join(',') + '\n' + rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], {type: 'text/csv'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `eval_history_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  });
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("\n  AI Evaluation Framework — Dashboard")
    print(f"  Mode: {config.MODE} | Model: {config.get_model_display_name()}")
    print(f"  Open: http://localhost:5000\n")
    app.run(debug=False, port=5000)
