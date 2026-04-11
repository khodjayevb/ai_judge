#!/usr/bin/env python3
"""
AI Evaluation Framework — Web Dashboard
Run: python app.py
Open: http://localhost:5000
"""

import sys
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from flask import Flask, render_template, request, jsonify, send_from_directory

import config
from prompts.registry import list_roles, get_prompt, get_test_suite, get_weak_variant, role_info
from evaluators.scorer import run_evaluation
from evaluators.recommender import generate_recommendations
from reports.html_report import generate_html_report
from reports.comparison_report import generate_comparison_report
from results_db import log_run, get_runs

app = Flask(__name__)

_jobs: dict[str, dict] = {}


def _average_reports(reports: list) -> object:
    """Average multiple evaluation reports into one.
    Uses the last report as the base structure, but averages all scores."""
    from evaluators.scorer import EvalReport, TestResult, CriterionResult, ResponseMetrics

    base = reports[-1]  # Use last report's structure (responses, etc.)
    n = len(reports)

    # Average each test result's criteria scores
    for t_idx, test_result in enumerate(base.test_results):
        for c_idx, criterion in enumerate(test_result.criteria_results):
            # Average GEval scores
            scores = [r.test_results[t_idx].criteria_results[c_idx].score for r in reports
                      if t_idx < len(r.test_results) and c_idx < len(r.test_results[t_idx].criteria_results)]
            criterion.score = round(sum(scores) / len(scores), 2) if scores else criterion.score

            # Average DAG scores
            dag_scores = [r.test_results[t_idx].criteria_results[c_idx].dag_score for r in reports
                          if t_idx < len(r.test_results) and c_idx < len(r.test_results[t_idx].criteria_results)
                          and r.test_results[t_idx].criteria_results[c_idx].dag_score is not None]
            criterion.dag_score = round(sum(dag_scores) / len(dag_scores), 2) if dag_scores else criterion.dag_score

        # Average safety scores
        if test_result.safety:
            for metric_name in test_result.safety:
                safety_scores = [r.test_results[t_idx].safety.get(metric_name, {}).get("score", 0) for r in reports
                                 if t_idx < len(r.test_results) and metric_name in r.test_results[t_idx].safety]
                if safety_scores:
                    avg = round(sum(safety_scores) / len(safety_scores), 2)
                    test_result.safety[metric_name]["score"] = avg
                    test_result.safety[metric_name]["passed"] = avg <= 0.5

    # Average latency
    for t_idx, test_result in enumerate(base.test_results):
        latencies = [r.test_results[t_idx].metrics.latency_seconds for r in reports
                     if t_idx < len(r.test_results)]
        test_result.metrics.latency_seconds = round(sum(latencies) / len(latencies), 2) if latencies else 0

    # Sum elapsed
    base.total_elapsed = round(sum(r.total_elapsed for r in reports), 2)

    # Mark as averaged
    base.prompt_version = f"{base.prompt_version} (avg of {n} runs)"

    return base


def _make_eval_runner(role, model_override, prompt_source, job_id, num_runs=1):
    """Create evaluation run(s) with optional model/prompt overrides.
    When num_runs > 1, runs multiple evaluations and averages the scores."""
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
            _jobs[job_id]["total"] = len(TEST_CASES) * num_runs

            all_reports = []
            for run_i in range(num_runs):
                run_label = f"Run {run_i+1}/{num_runs}: " if num_runs > 1 else ""

                def on_progress(current, total, test_id, _ri=run_i, _rl=run_label):
                    _jobs[job_id]["progress"] = _ri * len(TEST_CASES) + current
                    _jobs[job_id]["current_test"] = f"{_rl}{test_id}"

                r = run_evaluation(
                    system_prompt=SYSTEM_PROMPT, test_cases=TEST_CASES,
                    prompt_name=META["name"], prompt_version=META["version"],
                    domain=META["domain"], role_slug=role, on_progress=on_progress,
                )
                all_reports.append(r)

            # If multi-run, average the scores into the final report
            if num_runs > 1:
                report = _average_reports(all_reports)
            else:
                report = all_reports[0]

            recs = generate_recommendations(report)
            used_model = model_override or config.get_model_display_name()

            if prompt_source == "none":
                report_prompt = "(No system prompt sent — testing deployed model)"
            else:
                report_prompt = SYSTEM_PROMPT

            judge_cfg = config.get_judge_config()
            _judge_name = f"{judge_cfg['model']} ({judge_cfg['provider']})"

            from evaluators.judge_context import get_judge_context_info
            report_path = generate_html_report(
                report, recs,
                output_path=f"reports/eval_{role}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                system_prompt=report_prompt,
                model_name=used_model,
                judge_model_name=_judge_name,
                mode=config.MODE,
                judge_context_info=get_judge_context_info(role),
            )

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
                "grade": report.consolidated_grade,
                "score": report.consolidated_pct,
                "report_url": f"/reports/{Path(report_path).name}",
                "categories": report.category_scores(),
                "perf": report.perf_summary(),
                "num_runs": num_runs,
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
    return render_template("dashboard.html", roles=roles, history=history, config=config)


@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.json
    role = data.get("role", config.EVAL_ROLE)
    run_type = data.get("run_type", "evaluation")
    model = data.get("model", "")
    prompt_source = data.get("prompt_source", "local")
    num_runs = int(data.get("runs", 1))

    job_id = f"{run_type}_{role}_{len(_jobs)}"
    _jobs[job_id] = {"status": "running", "progress": 0, "total": 0, "current_test": "", "result": None}

    if run_type == "evaluation":
        thread = threading.Thread(target=_make_eval_runner(role, model, prompt_source, job_id, num_runs=num_runs))
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
                output_path=f"reports/compare_{role}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
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
                "report_url": f"/reports/{Path(report_path).name}",
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


@app.route("/api/improve-prompt", methods=["POST"])
def api_improve_prompt():
    data = request.json
    role = data.get("role", config.EVAL_ROLE)
    job_id = f"improve_{role}_{len(_jobs)}"
    _jobs[job_id] = {"status": "running", "progress": 0, "total": 1, "current_test": "Generating improved prompt...", "result": None}

    def _run():
        try:
            from evaluators.prompt_improver import generate_improved_prompt
            from evaluators.scorer import run_evaluation
            from evaluators.recommender import generate_recommendations
            from evaluators.llm_client import _client_cache

            SYSTEM_PROMPT, META = get_prompt(role)
            TEST_CASES = get_test_suite(role)
            _jobs[job_id]["total"] = len(TEST_CASES)

            def on_progress(current, total, test_id):
                _jobs[job_id]["progress"] = current
                _jobs[job_id]["current_test"] = f"Evaluating: {test_id} ({current}/{total})"

            # Run evaluation to get current scores
            report = run_evaluation(
                system_prompt=SYSTEM_PROMPT, test_cases=TEST_CASES,
                prompt_name=META["name"], prompt_version=META["version"],
                domain=META["domain"], role_slug=role, on_progress=on_progress,
            )
            recs = generate_recommendations(report)

            # Generate improved prompt
            _jobs[job_id]["current_test"] = "Generating improved prompt..."
            result = generate_improved_prompt(SYSTEM_PROMPT, report, recs)

            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["progress"] = 1
            _jobs[job_id]["result"] = result
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["result"] = {"error": str(e)}

    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/calibrate", methods=["POST"])
def api_calibrate():
    data = request.json or {}
    role = data.get("role", "")
    job_id = f"calibrate_{len(_jobs)}"
    _jobs[job_id] = {"status": "running", "progress": 0, "total": 1, "current_test": "Starting...", "result": None}

    def _run():
        try:
            from evaluators.judge_calibration import run_calibration

            def on_progress(current, total, label):
                _jobs[job_id]["progress"] = current
                _jobs[job_id]["total"] = total
                _jobs[job_id]["current_test"] = label

            result = run_calibration(role_slug=role, on_progress=on_progress)

            # Generate report
            from evaluators.judge_calibration import generate_calibration_report
            judge_cfg = config.get_judge_config()
            _judge_name = f"{judge_cfg['model']} ({judge_cfg['provider']})"
            report_path = generate_calibration_report(result, judge_model=_judge_name)
            result["report_url"] = f"/reports/{Path(report_path).name}"

            # Log to calibration history
            from results_db import log_calibration
            cal_id = log_calibration(result, judge_model=_judge_name, report_path=report_path)
            result["cal_id"] = cal_id

            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = result
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["result"] = {"error": str(e)}

    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/calibration-history")
def api_calibration_history():
    from results_db import get_calibration_runs
    return jsonify(get_calibration_runs())


@app.route("/api/settings")
def api_get_settings():
    """Get current .env settings."""
    env_path = Path(".env")
    settings = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                settings[key.strip()] = value.strip()

    # Load per-role assistant mappings from a separate file
    mapping_path = Path("role_assistants.json")
    role_assistants = {}
    if mapping_path.exists():
        import json as _json
        role_assistants = _json.loads(mapping_path.read_text(encoding="utf-8"))

    return jsonify({"settings": settings, "role_assistants": role_assistants})


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    """Save settings to .env and role assistant mappings."""
    data = request.json
    settings = data.get("settings", {})
    role_assistants = data.get("role_assistants", {})

    # Write .env
    env_lines = [
        "# ============================================================================",
        "# AI Evaluation Framework — BYOK Configuration",
        "# ============================================================================",
        "",
        "EVAL_MODE=live",
        f"EVAL_ROLE={settings.get('EVAL_ROLE', 'azure_data_engineer')}",
        "",
        f"TARGET_PROVIDER={settings.get('TARGET_PROVIDER', 'azure')}",
        f"TARGET_API_KEY={settings.get('TARGET_API_KEY', '')}",
        f"TARGET_MODEL={settings.get('TARGET_MODEL', 'gpt-4o')}",
        f"TARGET_BASE_URL={settings.get('TARGET_BASE_URL', '')}",
        f"TARGET_API_VERSION={settings.get('TARGET_API_VERSION', '2024-08-01-preview')}",
        f"TARGET_DEPLOYMENT={settings.get('TARGET_DEPLOYMENT', '')}",
        f"TARGET_SYSTEM_PROMPT={settings.get('TARGET_SYSTEM_PROMPT', 'local')}",
        "",
        f"JUDGE_PROVIDER={settings.get('JUDGE_PROVIDER', '')}",
        f"JUDGE_API_KEY={settings.get('JUDGE_API_KEY', '')}",
        f"JUDGE_MODEL={settings.get('JUDGE_MODEL', '')}",
        f"JUDGE_BASE_URL={settings.get('JUDGE_BASE_URL', '')}",
        f"JUDGE_DEPLOYMENT={settings.get('JUDGE_DEPLOYMENT', '')}",
        "",
    ]
    Path(".env").write_text("\n".join(env_lines), encoding="utf-8")

    # Write role-assistant mappings
    import json as _json
    Path("role_assistants.json").write_text(
        _json.dumps(role_assistants, indent=2), encoding="utf-8"
    )

    return jsonify({"success": True, "message": "Settings saved. Restart dashboard to apply."})


@app.route("/api/role/<slug>")
def api_get_role(slug):
    """Get full details for a role: prompt, test cases, context."""
    try:
        from prompts.registry import get_prompt, get_test_suite
        from evaluators.judge_context import load_judge_context, get_judge_context_info
        prompt, meta = get_prompt(slug)
        tests = get_test_suite(slug)
        ctx_info = get_judge_context_info(slug)
        ctx_text = load_judge_context(slug)
        return jsonify({
            "slug": slug, "meta": meta, "prompt": prompt,
            "tests": tests, "test_count": len(tests),
            "context_info": ctx_info, "context_text": ctx_text[:5000] if ctx_text else "",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/role/create", methods=["POST"])
def api_create_role():
    """Create a new role with prompt, test cases, and optional context."""
    data = request.json
    slug = data.get("slug", "").strip().lower().replace(" ", "_").replace("-", "_")
    name = data.get("name", "").strip()
    domain = data.get("domain", "").strip()
    prompt_text = data.get("prompt", "").strip()
    tests = data.get("tests", [])
    context_text = data.get("context", "").strip()

    if not slug or not name or not prompt_text:
        return jsonify({"error": "slug, name, and prompt are required"}), 400

    # Check if role already exists
    prompt_path = Path(f"prompts/{slug}.py")
    if prompt_path.exists():
        return jsonify({"error": f"Role '{slug}' already exists"}), 400

    try:
        # Create prompt file
        prompt_content = f'"""\nSystem prompt for {name}.\n"""\n\n'
        prompt_content += f'SYSTEM_PROMPT = """{prompt_text}"""\n\n'
        prompt_content += f'PROMPT_METADATA = {{\n'
        prompt_content += f'    "name": "{name}",\n'
        prompt_content += f'    "version": "1.0.0",\n'
        prompt_content += f'    "author": "AI Evaluation Framework",\n'
        prompt_content += f'    "domain": "{domain}",\n'
        prompt_content += f'    "target_model": "gpt-4o",\n'
        prompt_content += f'}}\n'
        prompt_path.write_text(prompt_content, encoding="utf-8")

        # Create test suite if provided
        test_path = Path(f"test_suites/{slug}_tests.py")
        if tests:
            import json as _json
            test_content = f'"""\nTest suite for {name}.\n"""\n\n'
            test_content += f'TEST_CASES = {_json.dumps(tests, indent=4, ensure_ascii=False)}\n\n'
            test_content += 'CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))\n'
            test_path.write_text(test_content, encoding="utf-8")
        else:
            # Create empty test suite
            test_content = f'"""\nTest suite for {name}.\n"""\n\nTEST_CASES = []\n\nCATEGORIES = []\n'
            test_path.write_text(test_content, encoding="utf-8")

        # Create context doc if provided
        if context_text:
            ctx_dir = Path(f"docs/{slug}")
            ctx_dir.mkdir(parents=True, exist_ok=True)
            (ctx_dir / "standards.md").write_text(context_text, encoding="utf-8")

        # Clear registry cache
        from prompts.registry import _PROMPTS_DIR
        import importlib
        # Force re-import on next access

        # Save initial version
        from results_db import save_role_version
        import json as _json2
        save_role_version(
            role_slug=slug, prompt_text=prompt_text,
            test_cases_json=_json2.dumps(tests) if tests else "",
            context_text=context_text, version="1.0.0",
            author="UI", change_note="Initial creation",
        )

        return jsonify({"success": True, "slug": slug, "files_created": {
            "prompt": str(prompt_path),
            "tests": str(test_path),
            "context": str(Path(f"docs/{slug}/standards.md")) if context_text else None,
        }})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/role/update", methods=["POST"])
def api_update_role():
    """Update an existing role's prompt, tests, or context."""
    data = request.json
    slug = data.get("slug", "")
    updates = {}

    # Update prompt if provided
    if "prompt" in data and data["prompt"].strip():
        prompt_path = Path(f"prompts/{slug}.py")
        if prompt_path.exists():
            # Read existing to preserve metadata
            content = prompt_path.read_text(encoding="utf-8")
            # Replace just the SYSTEM_PROMPT string
            import re
            new_prompt = data["prompt"].strip()
            new_content = re.sub(
                r'SYSTEM_PROMPT = """.*?"""',
                f'SYSTEM_PROMPT = """{new_prompt}"""',
                content, flags=re.DOTALL
            )
            prompt_path.write_text(new_content, encoding="utf-8")
            updates["prompt"] = "updated"

    # Update context if provided
    if "context" in data and data["context"].strip():
        ctx_dir = Path(f"docs/{slug}")
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "standards.md").write_text(data["context"].strip(), encoding="utf-8")
        # Clear context cache
        from evaluators.judge_context import _context_cache, _context_meta
        _context_cache.pop(slug, None)
        _context_meta.pop(slug, None)
        updates["context"] = "updated"

    # Save version snapshot
    if updates:
        from results_db import save_role_version
        change_note = data.get("change_note", "Updated via UI")
        save_role_version(
            role_slug=slug,
            prompt_text=data.get("prompt", ""),
            context_text=data.get("context", ""),
            version=data.get("version", ""),
            author="UI",
            change_note=change_note,
        )
        updates["version_saved"] = True

    return jsonify({"success": True, "updates": updates})


@app.route("/api/test-connection", methods=["POST"])
def api_test_connection():
    """Test API connection to the provider."""
    data = request.json
    provider = data.get("provider", "azure")
    base_url = data.get("base_url", "")
    api_key = data.get("api_key", "")
    model = data.get("model", "")
    api_version = data.get("api_version", "2024-08-01-preview")

    try:
        if provider == "azure":
            from openai import AzureOpenAI
            client = AzureOpenAI(azure_endpoint=base_url, api_key=api_key, api_version=api_version)
            r = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": "Say OK"}],
                max_completion_tokens=5,
            )
            return jsonify({"success": True, "model": r.model, "message": "Connected successfully"})
        elif provider == "azure_assistant":
            from openai import AzureOpenAI
            client = AzureOpenAI(azure_endpoint=base_url, api_key=api_key, api_version=api_version)
            # List assistants to verify connection
            assistants = client.beta.assistants.list(limit=5)
            names = [a.name or a.id for a in assistants.data]
            return jsonify({"success": True, "assistants": names, "message": f"Connected — {len(names)} assistant(s) found"})
        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            r = client.chat.completions.create(
                model=model or "gpt-4o-mini", messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5,
            )
            return jsonify({"success": True, "model": r.model, "message": "Connected successfully"})
        else:
            return jsonify({"success": False, "message": f"Test not implemented for provider: {provider}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)[:300]})


@app.route("/api/test-assistant", methods=["POST"])
def api_test_assistant():
    """Test a specific Foundry Assistant by ID."""
    data = request.json
    assistant_id = data.get("assistant_id", "")
    base_url = data.get("base_url", config.get_target_config()["base_url"])
    api_key = data.get("api_key", config.get_target_config()["api_key"])
    api_version = data.get("api_version", config.get_target_config()["api_version"])

    if not assistant_id:
        return jsonify({"success": False, "message": "No assistant ID provided"})

    try:
        from openai import AzureOpenAI
        import time as _time
        client = AzureOpenAI(azure_endpoint=base_url, api_key=api_key, api_version=api_version)

        # Create thread, send test message, run assistant
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content="Say OK in one word.")
        run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=assistant_id)

        # Poll (max 30 seconds)
        for _ in range(30):
            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run.status not in ("queued", "in_progress"):
                break
            _time.sleep(1)

        if run.status == "completed":
            msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
            response = ""
            if msgs.data:
                for block in msgs.data[0].content:
                    if hasattr(block, "text"):
                        response += block.text.value
            try:
                client.beta.threads.delete(thread.id)
            except Exception:
                pass
            return jsonify({"success": True, "response": response[:100], "message": "Assistant responded successfully"})
        else:
            return jsonify({"success": False, "message": f"Run status: {run.status}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)[:300]})


@app.route("/api/role/versions/<slug>")
def api_role_versions(slug):
    from results_db import get_role_versions
    return jsonify(get_role_versions(slug))


@app.route("/api/role/version/<int:version_id>")
def api_role_version_detail(version_id):
    from results_db import get_role_version_detail
    v = get_role_version_detail(version_id)
    if not v:
        return jsonify({"error": "Version not found"}), 404
    return jsonify(v)


@app.route("/api/role/upload-context/<slug>", methods=["POST"])
def api_upload_context(slug):
    """Upload context files directly to docs/{slug}/."""
    if 'files' not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    ctx_dir = Path(f"docs/{slug}")
    ctx_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for f in request.files.getlist('files'):
        if f.filename and f.filename.endswith(('.md', '.txt', '.markdown')):
            dest = ctx_dir / f.filename
            f.save(str(dest))
            uploaded.append(f.filename)

    # Clear context cache
    from evaluators.judge_context import _context_cache, _context_meta
    _context_cache.pop(slug, None)
    _context_meta.pop(slug, None)

    return jsonify({"success": True, "uploaded": uploaded, "path": str(ctx_dir)})


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
                output_path=f"reports/eval_gen_{role}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                system_prompt=SYSTEM_PROMPT,
                model_name=config.get_model_display_name(),
                judge_model_name=f"{judge_cfg['model']} ({judge_cfg['provider']})",
                mode=config.MODE,
            )

            # Log to history
            run_id = log_run(
                report=report, role=role,
                model=config.get_model_display_name(),
                judge_model=f"{judge_cfg['model']} ({judge_cfg['provider']})",
                provider=config.TARGET_PROVIDER,
                mode=config.MODE,
                report_path=report_path,
                run_type="eval_generated",
                notes=f"{len(test_cases)} generated/manual test cases",
            )

            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = {
                "run_id": run_id,
                "grade": report.consolidated_grade,
                "score": report.consolidated_pct,
                "report_url": f"/reports/{Path(report_path).name}",
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
                output_path=f"reports/redteam_{role}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
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
                "report_url": f"/reports/{Path(report_path).name}",
            }
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["result"] = {"error": str(e)}

    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()
    return jsonify({"job_id": job_id})





if __name__ == "__main__":
    print("\n  AI Evaluation Framework — Dashboard")
    print(f"  Mode: {config.MODE} | Model: {config.get_model_display_name()}")
    print(f"  Open: http://localhost:5000\n")
    app.run(debug=False, port=5000)
