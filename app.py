#!/usr/bin/env python3
"""
AI Evaluation Framework — Web Dashboard
Run: python app.py
Open: http://localhost:5000
"""

import sys
import json
import threading
from datetime import datetime
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
    return render_template_string(DASHBOARD_HTML, roles=roles, history=history, config=config)


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
    job_id = f"calibrate_{len(_jobs)}"
    _jobs[job_id] = {"status": "running", "progress": 0, "total": 1, "current_test": "Starting...", "result": None}

    def _run():
        try:
            from evaluators.judge_calibration import run_calibration

            def on_progress(current, total, label):
                _jobs[job_id]["progress"] = current
                _jobs[job_id]["total"] = total
                _jobs[job_id]["current_test"] = label

            result = run_calibration(on_progress=on_progress)

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


# ══════════════════════════════════════════════════════════════════════════

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Evaluation Framework</title>
<style>
  :root, [data-theme="dark"] {
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #e2e8f0; --text2: #94a3b8; --accent: #38bdf8;
    --green: #22c55e; --yellow: #eab308; --red: #ef4444;
    --orange: #f97316; --purple: #a78bfa;
  }
  [data-theme="light"] {
    --bg: #f8fafc; --surface: #ffffff; --surface2: #e2e8f0;
    --text: #1e293b; --text2: #475569; --accent: #0284c7;
    --green: #16a34a; --yellow: #ca8a04; --red: #dc2626;
    --orange: #ea580c; --purple: #7c3aed;
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

  <!-- Header Bar -->
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem">
    <h1 style="margin:0;font-size:1.5rem">AI Evaluation Framework</h1>
    <div style="display:flex;gap:0.5rem;align-items:center">
      <span style="background:var(--green);color:#000;padding:0.3rem 0.7rem;border-radius:6px;font-size:0.8rem;font-weight:600">LIVE</span>
      <button onclick="toggleTheme()" style="background:var(--surface);border:1px solid var(--surface2);border-radius:8px;padding:0.4rem 0.7rem;cursor:pointer;color:var(--text);font-size:0.85rem" title="Toggle light/dark theme" id="themeBtn">☀️ Light</button>
      <button onclick="toggleSettings()" style="background:var(--surface);border:1px solid var(--surface2);border-radius:8px;padding:0.4rem 0.7rem;cursor:pointer;color:var(--text);font-size:0.85rem" title="Settings">⚙️ Settings</button>
    </div>
  </div>

  <!-- Settings Modal -->
  <div id="settingsModal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:1000;overflow-y:auto">
    <div style="max-width:900px;margin:2rem auto;background:var(--bg);border-radius:16px;padding:2rem;border:1px solid var(--surface2)">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem">
        <h2 style="color:var(--accent);margin:0;border:none">Settings</h2>
        <button onclick="toggleSettings()" style="background:var(--surface2);border:none;border-radius:8px;padding:0.4rem 0.8rem;cursor:pointer;color:var(--text);font-size:1rem">✕ Close</button>
      </div>

      <!-- Section 1: Connection -->
      <div style="background:var(--surface);border-radius:8px;padding:1.25rem;margin-bottom:1rem">
        <h4 style="color:var(--accent);margin-bottom:0.75rem">Connection</h4>
        <div class="form-row">
          <div class="form-group">
            <label>Provider</label>
            <select id="setTargetProvider">
              <option value="azure">Azure OpenAI</option>
              <option value="azure_assistant">Azure Foundry Assistant</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic / Claude</option>
              <option value="google">Google Gemini</option>
              <option value="ollama">Ollama (local)</option>
            </select>
          </div>
          <div class="form-group">
            <label>Base URL</label>
            <input type="text" id="setTargetURL" placeholder="https://your-resource.openai.azure.com">
          </div>
          <div class="form-group">
            <label>API Key</label>
            <input type="password" id="setTargetKey" placeholder="API key">
          </div>
          <div class="form-group" style="flex:0">
            <label>&nbsp;</label>
            <button class="btn" style="background:var(--green);color:#000;white-space:nowrap" onclick="testConnection()">Test Connection</button>
          </div>
        </div>
        <div id="connectionStatus" style="font-size:0.85rem;margin-top:0.3rem"></div>
      </div>

      <!-- Section 2: Model Defaults -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem">
        <div style="background:var(--surface);border-radius:8px;padding:1.25rem">
          <h4 style="color:var(--accent);margin-bottom:0.75rem">Default Target Model</h4>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Model / Deployment</label>
            <input type="text" id="setTargetModel" placeholder="e.g., gpt-4o, gpt-4.1">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Temperature</label>
              <input type="number" id="setTemperature" value="0.3" min="0" max="1" step="0.1" style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.4rem;width:80px">
            </div>
            <div class="form-group">
              <label>Top P</label>
              <input type="number" id="setTopP" value="0.95" min="0" max="1" step="0.05" style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.4rem;width:80px">
            </div>
            <div class="form-group">
              <label>API Version</label>
              <input type="text" id="setTargetVersion" placeholder="2024-08-01-preview" style="max-width:180px">
            </div>
          </div>
        </div>
        <div style="background:var(--surface);border-radius:8px;padding:1.25rem">
          <h4 style="color:var(--purple);margin-bottom:0.75rem">Judge Model</h4>
          <p style="color:var(--text2);font-size:0.8rem;margin-bottom:0.5rem">Should be stronger than target. Leave empty = same as target.</p>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Model / Deployment</label>
            <input type="text" id="setJudgeModel" placeholder="e.g., gpt-5.4">
          </div>
          <div class="form-group">
            <label>Judge API Key (if different)</label>
            <input type="password" id="setJudgeKey" placeholder="(falls back to target key)">
          </div>
        </div>
      </div>

      <!-- Section 3: Per-Role Assistant Mapping -->
      <div style="background:var(--surface);border-radius:8px;padding:1.25rem;margin-bottom:1rem">
        <h4 style="color:var(--accent);margin-bottom:0.5rem">Per-Role Foundry Assistant Mapping</h4>
        <p style="color:var(--text2);font-size:0.8rem;margin-bottom:0.75rem">Optional — when provider is "Azure Foundry Assistant", each role uses its own assistant with baked-in prompt and settings.</p>
        <table class="history-table" style="font-size:0.85rem">
          <thead><tr><th>Role</th><th>Assistant ID</th><th>Status</th></tr></thead>
          <tbody>
            {% for r in roles %}
            <tr>
              <td style="color:var(--accent);font-weight:600">{{ r.slug }}</td>
              <td><input type="text" id="asst_{{ r.slug }}" placeholder="asst_abc123..." style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:4px;padding:0.3rem 0.5rem;width:100%;font-size:0.85rem;font-family:monospace"></td>
              <td id="asst_status_{{ r.slug }}" style="font-size:0.8rem;color:var(--text2)">—</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        <button class="btn" style="background:var(--surface2);color:var(--text);font-size:0.8rem;margin-top:0.5rem" onclick="testAllAssistants()">Test All Assistants</button>
      </div>

      <div style="display:flex;gap:0.5rem">
        <button class="btn btn-primary" onclick="saveSettings()">Save Settings</button>
        <button class="btn" style="background:var(--surface2);color:var(--text)" onclick="loadSettings()">Reload</button>
      </div>
      <div class="result-flash" id="settingsResult" style="margin-top:0.75rem"></div>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="switchTab('eval')">Run Evaluation</div>
    <div class="tab" onclick="switchTab('compare')">A/B Comparison</div>
    <div class="tab" onclick="switchTab('redteam')">Red Team</div>
    <div class="tab" onclick="switchTab('generate')">Generate Tests</div>
    <div class="tab" onclick="switchTab('calibrate')">Judge Calibration</div>
    <div class="tab" onclick="switchTab('manage')">Manage Roles</div>
    <div class="tab" onclick="switchTab('docs')">Docs</div>
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
          <select id="evalPrompt" onchange="toggleCustomPrompt('evalCustomPrompt', this.value)">
            <option value="local">Local (from codebase)</option>
            <option value="none">None — no prompt sent (Foundry Assistants only)</option>
            <option value="custom">Custom (paste your own)</option>
          </select>
          <textarea id="evalCustomPrompt" placeholder="Paste your system prompt here..." style="display:none;margin-top:0.3rem;background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.5rem;font-size:0.8rem;font-family:monospace;min-height:80px;width:100%;resize:vertical"></textarea>
        </div>
        <div class="form-group" style="max-width:80px">
          <label>Runs</label>
          <select id="evalRuns">
            <option value="1" selected>1x</option>
            <option value="2">2x</option>
            <option value="3">3x (avg)</option>
            <option value="5">5x (avg)</option>
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
      <h3 style="margin-top:1.5rem;color:var(--accent)">Evaluation History</h3>
      <div style="display:flex;gap:0.5rem;margin-bottom:0.5rem">
        <button class="btn" style="background:var(--surface2);color:var(--text);font-size:0.75rem;padding:0.3rem 0.6rem" onclick="exportCSV('evaluation')">Export CSV</button>
      </div>
      <div id="evalHistory" style="max-height:300px;overflow-y:auto"></div>
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
            <select id="cmpPromptA" onchange="toggleCustomPrompt('cmpCustomPromptA', this.value)">
              <option value="local">Local (full prompt)</option>
              <option value="weak">Weak baseline (v1)</option>
              <option value="none">None — no prompt sent (Foundry Assistants only)</option>
              <option value="custom">Custom (paste your own)</option>
            </select>
            <textarea id="cmpCustomPromptA" placeholder="Paste system prompt for Run A..." style="display:none;margin-top:0.3rem;background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.5rem;font-size:0.8rem;font-family:monospace;min-height:60px;width:100%;resize:vertical"></textarea>
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
            <select id="cmpPromptB" onchange="toggleCustomPrompt('cmpCustomPromptB', this.value)">
              <option value="local">Local (full prompt)</option>
              <option value="weak">Weak baseline (v1)</option>
              <option value="none">None — no prompt sent (Foundry Assistants only)</option>
              <option value="custom">Custom (paste your own)</option>
            </select>
            <textarea id="cmpCustomPromptB" placeholder="Paste system prompt for Run B..." style="display:none;margin-top:0.3rem;background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.5rem;font-size:0.8rem;font-family:monospace;min-height:60px;width:100%;resize:vertical"></textarea>
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
      <h3 style="margin-top:1.5rem;color:var(--accent)">Comparison History</h3>
      <div id="cmpHistory" style="max-height:300px;overflow-y:auto"></div>
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
          <select id="rtPrompt" onchange="toggleCustomPrompt('rtCustomPrompt', this.value)">
            <option value="local">Local (from codebase)</option>
            <option value="none">None — no prompt sent (Foundry Assistants only)</option>
            <option value="custom">Custom (paste your own)</option>
          </select>
          <textarea id="rtCustomPrompt" placeholder="Paste system prompt to test..." style="display:none;margin-top:0.3rem;background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.5rem;font-size:0.8rem;font-family:monospace;min-height:60px;width:100%;resize:vertical"></textarea>
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
      <h3 style="margin-top:1.5rem;color:var(--accent)">Red Team History</h3>
      <div id="rtHistory" style="max-height:300px;overflow-y:auto"></div>
    </div>
  </div>

  <!-- ═══ GENERATE TESTS TAB ═══ -->
  <div class="tab-content" id="tab-generate">
    <div class="panel">
      <div class="panel-title">Generate Synthetic Test Cases</div>
      <p style="color:var(--text2);margin-bottom:1rem;font-size:0.9rem">
        Generates test cases from reference documents and/or role system prompts.<br>
        <strong>Best results:</strong> Add reference docs (standards, guides, best practices) to <code>docs/{'{role_slug}'}/</code> folder.
        Without docs, falls back to the system prompt.
        <strong>Review generated tests before using in evaluations.</strong>
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

      <hr style="border:1px solid var(--surface2);margin:1.5rem 0">
      <div class="panel-title" style="font-size:1rem">Add Manual Test Case</div>
      <p style="color:var(--text2);margin-bottom:0.75rem;font-size:0.85rem">Create a test case by hand and add it to the generated list above.</p>
      <div class="form-row">
        <div class="form-group">
          <label>Test ID</label>
          <input type="text" id="manualId" placeholder="e.g., PERF-01" style="max-width:150px">
        </div>
        <div class="form-group">
          <label>Category</label>
          <input type="text" id="manualCategory" placeholder="e.g., Performance">
        </div>
        <div class="form-group" style="max-width:100px">
          <label>Weight (1-3)</label>
          <select id="manualWeight">
            <option value="1">1</option>
            <option value="2" selected>2</option>
            <option value="3">3</option>
          </select>
        </div>
      </div>
      <div class="form-group" style="margin-bottom:0.5rem">
        <label>Question</label>
        <textarea id="manualQuestion" placeholder="The user question to test..." style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.5rem;font-size:0.85rem;min-height:50px;width:100%;resize:vertical"></textarea>
      </div>
      <div class="form-group" style="margin-bottom:0.5rem">
        <label>Criteria (one per line, up to 5)</label>
        <textarea id="manualCriteria" placeholder="Recommends star schema for data modeling&#10;Mentions Kimball methodology&#10;Addresses fact vs dimension table design&#10;Considers performance implications&#10;Provides specific Power BI guidance" style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.5rem;font-size:0.85rem;min-height:80px;width:100%;resize:vertical"></textarea>
      </div>
      <div class="form-group" style="margin-bottom:0.75rem">
        <label>Context / Ground Truth (optional, one per line)</label>
        <textarea id="manualContext" placeholder="Factual statements for hallucination detection..." style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.5rem;font-size:0.85rem;min-height:40px;width:100%;resize:vertical"></textarea>
      </div>
      <button class="btn" style="background:var(--surface2);color:var(--text)" onclick="addManualTestCase()">Add Test Case</button>
      <h3 style="margin-top:1.5rem;color:var(--accent)">Generated Test Evaluation History</h3>
      <p style="color:var(--text2);font-size:0.8rem;margin-bottom:0.5rem">Evaluations run on generated/manual test cases</p>
      <div id="genHistory" style="max-height:300px;overflow-y:auto"></div>
    </div>
  </div>

  <!-- ═══ JUDGE CALIBRATION TAB ═══ -->
  <div class="tab-content" id="tab-calibrate">
    <div class="panel">
      <div class="panel-title">Judge Calibration — Gold Standard Validation</div>
      <p style="color:var(--text2);margin-bottom:1rem;font-size:0.9rem">
        Tests whether your judge model scores accurately against pre-scored gold standard responses.
        Includes excellent, adequate, poor, and deliberately misleading responses with known expected scores.
      </p>
      <button class="btn btn-primary" id="btnCalibrate" onclick="runCalibration()">Run Calibration Test</button>
      <div class="progress-area" id="calProgress">
        <div class="progress-bar-wrap"><div class="progress-bar" id="calBar" style="width:0%"></div></div>
        <div class="progress-text" id="calText">Calibrating...</div>
      </div>
      <div class="result-flash" id="calResult"></div>
      <h3 style="margin-top:1.5rem;color:var(--accent)">Calibration History</h3>
      <p style="color:var(--text2);font-size:0.8rem;margin-bottom:0.5rem">Run calibration multiple times to track judge consistency over time.</p>
      <div id="calHistory" style="max-height:300px;overflow-y:auto"></div>
    </div>
  </div>

  <!-- Old Settings tab removed — now in header modal -->
  <div style="display:none"><!-- placeholder to keep structure -->
  <div><!-- inner -->

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem">
        <!-- Target Model -->
        <div style="background:var(--bg);border-radius:8px;padding:1.25rem">
          <h4 style="color:var(--accent);margin-bottom:0.75rem">Target Model</h4>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Provider</label>
            <select id="setTargetProvider">
              <option value="azure">Azure OpenAI</option>
              <option value="azure_assistant">Azure Foundry Assistant</option>
              <option value="azure_foundry">Azure AI Foundry</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic / Claude</option>
              <option value="google">Google Gemini</option>
              <option value="ollama">Ollama (local)</option>
            </select>
          </div>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>API Key</label>
            <input type="password" id="setTargetKey" placeholder="API key">
          </div>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Model / Deployment</label>
            <input type="text" id="setTargetModel" placeholder="e.g., gpt-4o, gpt-4.1">
          </div>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Base URL</label>
            <input type="text" id="setTargetURL" placeholder="https://your-resource.openai.azure.com">
          </div>
          <div class="form-group">
            <label>API Version</label>
            <input type="text" id="setTargetVersion" placeholder="2024-08-01-preview">
          </div>
        </div>

        <!-- Judge Model -->
        <div style="background:var(--bg);border-radius:8px;padding:1.25rem">
          <h4 style="color:var(--purple);margin-bottom:0.75rem">Judge Model</h4>
          <p style="color:var(--text2);font-size:0.8rem;margin-bottom:0.5rem">Leave empty to use same as target.</p>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Provider</label>
            <select id="setJudgeProvider">
              <option value="">(same as target)</option>
              <option value="azure">Azure OpenAI</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic / Claude</option>
              <option value="google">Google Gemini</option>
            </select>
          </div>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>API Key</label>
            <input type="password" id="setJudgeKey" placeholder="(falls back to target)">
          </div>
          <div class="form-group" style="margin-bottom:0.5rem">
            <label>Model / Deployment</label>
            <input type="text" id="setJudgeModel" placeholder="e.g., gpt-5.4">
          </div>
          <div class="form-group">
            <label>Base URL</label>
            <input type="text" id="setJudgeURL" placeholder="(falls back to target)">
          </div>
        </div>
      </div>

      <!-- Per-Role Assistant Mapping -->
      <h4 style="color:var(--accent);margin-top:1.5rem;margin-bottom:0.5rem">Per-Role Foundry Assistant Mapping</h4>
      <p style="color:var(--text2);font-size:0.8rem;margin-bottom:0.75rem">
        Map each role to a Foundry Assistant ID. When provider is <code>azure_assistant</code>, the framework calls the assistant by ID instead of Chat Completions.
      </p>
      <table class="history-table" style="font-size:0.85rem" id="assistantMappingTable">
        <thead><tr><th>Role</th><th>Assistant ID</th><th>Description</th></tr></thead>
        <tbody>
          {% for r in roles %}
          <tr>
            <td style="color:var(--accent);font-weight:600">{{ r.slug }}</td>
            <td><input type="text" id="asst_{{ r.slug }}" placeholder="asst_abc123..." style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:4px;padding:0.3rem 0.5rem;width:100%;font-size:0.85rem;font-family:monospace"></td>
            <td style="color:var(--text2);font-size:0.8rem">{{ r.name }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>

      <div style="display:flex;gap:0.5rem;margin-top:1rem">
        <button class="btn btn-primary" onclick="saveSettings()">Save Settings</button>
        <button class="btn" style="background:var(--surface2);color:var(--text)" onclick="loadSettings()">Reload from .env</button>
      </div>
      <div class="result-flash" id="settingsResult" style="margin-top:0.75rem"></div>
    </div>
  </div>

  <!-- ═══ MANAGE ROLES TAB ═══ -->
  <div class="tab-content" id="tab-manage">
    <div class="panel">
      <div class="panel-title">Manage Roles</div>
      <p style="color:var(--text2);font-size:0.85rem;margin-bottom:1rem">
        Roles are stored as files in the codebase: <code>prompts/{slug}.py</code>, <code>test_suites/{slug}_tests.py</code>, <code>docs/{slug}/</code>.
        Changes made here directly update these files. Use <code>git diff</code> to review changes before committing.
      </p>

      <!-- Existing roles -->
      <h3 style="color:var(--accent);margin-bottom:0.75rem">Existing Roles</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:0.75rem;margin-bottom:1.5rem">
        {% for r in roles %}
        <div style="background:var(--bg);border-radius:8px;padding:1rem;border-left:3px solid var(--accent);cursor:pointer" onclick="loadRole('{{ r.slug }}')">
          <div style="font-weight:700;color:var(--accent)">{{ r.name }}</div>
          <div style="font-size:0.8rem;color:var(--text2)">{{ r.domain }} | v{{ r.version }}</div>
          <div style="font-size:0.75rem;color:var(--text2);margin-top:0.3rem">
            Tests: {{ 'Yes' if r.has_tests else 'No' }} |
            A/B: {{ 'Yes' if r.has_weak_variant else 'No' }} |
            Click to edit
          </div>
        </div>
        {% endfor %}
      </div>

      <hr style="border:1px solid var(--surface2);margin:1.5rem 0">

      <!-- Create / Edit Role -->
      <h3 style="color:var(--accent);margin-bottom:0.75rem" id="roleFormTitle">Create New Role</h3>
      <div class="form-row">
        <div class="form-group">
          <label>Role Slug (lowercase, no spaces)</label>
          <input type="text" id="mgrSlug" placeholder="e.g., data_scientist">
        </div>
        <div class="form-group">
          <label>Display Name</label>
          <input type="text" id="mgrName" placeholder="e.g., Data Scientist Assistant">
        </div>
        <div class="form-group">
          <label>Domain</label>
          <input type="text" id="mgrDomain" placeholder="e.g., Data Science & ML">
        </div>
      </div>

      <div class="form-group" style="margin-bottom:0.75rem">
        <label>System Prompt</label>
        <textarea id="mgrPrompt" placeholder="You are an expert... (write the full system prompt)" style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.75rem;font-size:0.85rem;font-family:monospace;min-height:200px;width:100%;resize:vertical"></textarea>
      </div>

      <div class="form-group" style="margin-bottom:0.75rem">
        <label>Judge Context / Reference Standards (optional — used for domain-aware scoring)</label>
        <div style="display:flex;gap:0.5rem;margin-bottom:0.3rem">
          <label style="background:var(--surface2);padding:0.3rem 0.8rem;border-radius:6px;cursor:pointer;font-size:0.8rem;color:var(--accent)">
            Upload .md / .txt files
            <input type="file" id="mgrContextFiles" multiple accept=".md,.txt,.markdown" style="display:none" onchange="handleContextUpload(this)">
          </label>
          <span id="mgrContextFileStatus" style="color:var(--text2);font-size:0.8rem;align-self:center"></span>
        </div>
        <textarea id="mgrContext" placeholder="Paste your organization's standards, best practices, and guidelines here. Or use the upload button above to load from .md/.txt files." style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.75rem;font-size:0.85rem;min-height:120px;width:100%;resize:vertical"></textarea>
      </div>

      <div class="form-group" style="margin-bottom:0.75rem">
        <label>System Prompt — Upload from file (optional)</label>
        <div style="display:flex;gap:0.5rem">
          <label style="background:var(--surface2);padding:0.3rem 0.8rem;border-radius:6px;cursor:pointer;font-size:0.8rem;color:var(--accent)">
            Upload .md / .txt file
            <input type="file" id="mgrPromptFile" accept=".md,.txt,.markdown" style="display:none" onchange="handlePromptUpload(this)">
          </label>
          <span id="mgrPromptFileStatus" style="color:var(--text2);font-size:0.8rem;align-self:center"></span>
        </div>
      </div>

      <details style="margin-bottom:0.75rem">
        <summary style="cursor:pointer;color:var(--accent);font-size:0.9rem">Add Test Cases (JSON format)</summary>
        <div style="display:flex;gap:0.5rem;margin:0.5rem 0">
          <label style="background:var(--surface2);padding:0.3rem 0.8rem;border-radius:6px;cursor:pointer;font-size:0.8rem;color:var(--accent)">
            Upload .json file
            <input type="file" id="mgrTestsFile" accept=".json" style="display:none" onchange="handleTestsUpload(this)">
          </label>
          <span id="mgrTestsFileStatus" style="color:var(--text2);font-size:0.8rem;align-self:center"></span>
        </div>
        <textarea id="mgrTests" placeholder='[{"id":"TEST-01","category":"General","question":"...","criteria":["...","..."],"weight":2}]' style="background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.75rem;font-size:0.8rem;font-family:monospace;min-height:120px;width:100%;resize:vertical"></textarea>
        <p style="color:var(--text2);font-size:0.75rem;margin-top:0.3rem">Tip: Use the Generate Tests tab to create test cases, download as JSON, then upload here.</p>
      </details>

      <div id="changeNoteRow" style="display:none;margin-bottom:0.5rem">
        <div class="form-group">
          <label>Change Note (what did you change and why?)</label>
          <input type="text" id="mgrChangeNote" placeholder="e.g., Added DAX performance guidelines, strengthened RLS instructions">
        </div>
      </div>
      <div style="display:flex;gap:0.5rem">
        <button class="btn btn-primary" id="mgrCreateBtn" onclick="createRole()">Create Role</button>
        <button class="btn" id="mgrUpdateBtn" style="background:var(--purple);color:#fff;display:none" onclick="updateRole()">Update Role</button>
        <button class="btn" style="background:var(--surface2);color:var(--text)" onclick="clearRoleForm()">Clear Form</button>
      </div>
      <div class="result-flash" id="mgrResult" style="margin-top:0.75rem"></div>

      <!-- Version History -->
      <div id="versionSection" style="display:none;margin-top:1.5rem">
        <h3 style="color:var(--accent);margin-bottom:0.5rem">Version History</h3>
        <div id="versionList"></div>
        <div id="versionDiff" style="display:none;margin-top:1rem">
          <h4 style="color:var(--purple);margin-bottom:0.5rem">Version Comparison</h4>
          <div id="versionDiffContent"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ DOCS TAB ═══ -->
  <div class="tab-content" id="tab-docs">
    <div class="panel" style="padding:2rem">

      <h2 style="color:var(--accent);margin-top:0;border:none">AI Evaluation Framework — Documentation</h2>

      <!-- Quick Nav -->
      <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1.5rem">
        <a href="#doc-overview" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--accent);text-decoration:none;font-size:0.8rem">Overview</a>
        <a href="#doc-concepts" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--accent);text-decoration:none;font-size:0.8rem">Key Concepts</a>
        <a href="#doc-scoring" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--accent);text-decoration:none;font-size:0.8rem">Scoring System</a>
        <a href="#doc-tabs" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--accent);text-decoration:none;font-size:0.8rem">Tab Guide</a>
        <a href="#doc-config" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--accent);text-decoration:none;font-size:0.8rem">Configuration</a>
        <a href="#doc-roles" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--accent);text-decoration:none;font-size:0.8rem">Roles</a>
        <a href="#doc-glossary" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--accent);text-decoration:none;font-size:0.8rem">Glossary</a>
        <a href="#doc-code" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--accent);text-decoration:none;font-size:0.8rem">Code Examples</a>
        <a href="#doc-features" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--purple);text-decoration:none;font-size:0.8rem">Features</a>
        <a href="#doc-faq" style="padding:0.3rem 0.7rem;background:var(--surface2);border-radius:6px;color:var(--accent);text-decoration:none;font-size:0.8rem">FAQ</a>
      </div>

      <!-- Overview -->
      <h3 id="doc-overview" style="color:var(--accent);margin-top:1.5rem">Overview</h3>
      <p style="color:var(--text2);line-height:1.8;margin-bottom:1rem">
        This framework evaluates how well AI assistants perform by testing them against domain-specific criteria.
        It sends questions to a <strong>target model</strong>, then uses a separate <strong>judge model</strong> to score the responses
        using two complementary methods: <a href="https://deepeval.com/docs/metrics-llm-evals" target="_blank" style="color:var(--accent)"><strong>GEval</strong></a> (nuanced, LLM-based) and
        <a href="https://deepeval.com/docs/metrics-dag" target="_blank" style="color:var(--accent)"><strong>DAG</strong></a> (deterministic, decision-tree based).
        Safety metrics check every response for <a href="https://deepeval.com/docs/metrics-bias" target="_blank" style="color:var(--accent)">bias</a>,
        <a href="https://deepeval.com/docs/metrics-toxicity" target="_blank" style="color:var(--accent)">toxicity</a>,
        <a href="https://deepeval.com/docs/metrics-pii-leakage" target="_blank" style="color:var(--accent)">PII leakage</a>, and
        <a href="https://deepeval.com/docs/metrics-hallucination" target="_blank" style="color:var(--accent)">hallucination</a>.
        Built on <a href="https://deepeval.com" target="_blank" style="color:var(--accent)"><strong>DeepEval</strong></a> — the open-source LLM evaluation framework.
        Red teaming powered by <a href="https://www.trydeepteam.com" target="_blank" style="color:var(--accent)"><strong>DeepTeam</strong></a>.
      </p>
      <div style="background:var(--bg);border-radius:8px;padding:1rem;font-size:0.85rem;font-family:monospace;color:var(--text2);margin-bottom:1rem">
        Question → Target Model → Response → Judge Model → Scores (GEval + DAG + Safety) → Report
      </div>

      <!-- Key Concepts -->
      <h3 id="doc-concepts" style="color:var(--accent);margin-top:2rem">Key Concepts</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:0.75rem">

        <div style="background:var(--bg);border-radius:8px;padding:1rem;border-left:3px solid var(--accent)">
          <h4 style="color:var(--accent);margin-bottom:0.3rem">Target Model</h4>
          <p style="color:var(--text2);font-size:0.85rem">The AI model being evaluated. This is the model whose system prompt you're testing. It receives questions and generates responses.</p>
          <p style="color:var(--text2);font-size:0.8rem;margin-top:0.3rem"><em>Example: GPT-4o generating Power BI advice</em></p>
        </div>

        <div style="background:var(--bg);border-radius:8px;padding:1rem;border-left:3px solid var(--purple)">
          <h4 style="color:var(--purple);margin-bottom:0.3rem">Judge Model</h4>
          <p style="color:var(--text2);font-size:0.85rem">A separate (ideally stronger) model that scores the target's responses. Should be different from the target to avoid self-grading bias.</p>
          <p style="color:var(--text2);font-size:0.8rem;margin-top:0.3rem"><em>Example: GPT-5.4 scoring GPT-4o's responses</em></p>
        </div>

        <div style="background:var(--bg);border-radius:8px;padding:1rem;border-left:3px solid var(--green)">
          <h4 style="color:var(--green);margin-bottom:0.3rem">System Prompt</h4>
          <p style="color:var(--text2);font-size:0.85rem">Instructions given to the target model defining its role, knowledge, constraints, and response style. This is what you're optimizing.</p>
          <p style="color:var(--text2);font-size:0.8rem;margin-top:0.3rem"><em>Sources: Local (codebase), None (deployed model), Custom (paste your own)</em></p>
        </div>

        <div style="background:var(--bg);border-radius:8px;padding:1rem;border-left:3px solid var(--yellow)">
          <h4 style="color:var(--yellow);margin-bottom:0.3rem">Test Suite</h4>
          <p style="color:var(--text2);font-size:0.85rem">A set of questions + evaluation criteria for a specific role. Each test has a question, 5 criteria (what a good answer must include), and a weight (1-3x importance).</p>
          <p style="color:var(--text2);font-size:0.8rem;margin-top:0.3rem"><em>Located in: test_suites/{role}_tests.py</em></p>
        </div>

        <div style="background:var(--bg);border-radius:8px;padding:1rem;border-left:3px solid var(--orange)">
          <h4 style="color:var(--orange);margin-bottom:0.3rem">Judge Context</h4>
          <p style="color:var(--text2);font-size:0.85rem">Reference documents fed to the judge so it scores against your organization's standards, not generic knowledge. Loaded from docs/{role}/.</p>
          <p style="color:var(--text2);font-size:0.8rem;margin-top:0.3rem"><em>Example: Your Power BI standards doc with specific DAX patterns and security rules</em></p>
        </div>

        <div style="background:var(--bg);border-radius:8px;padding:1rem;border-left:3px solid var(--red)">
          <h4 style="color:var(--red);margin-bottom:0.3rem">Gold Standard</h4>
          <p style="color:var(--text2);font-size:0.85rem">Pre-scored responses used to validate judge accuracy. Includes excellent, adequate, poor, and misleading responses with known expected scores.</p>
          <p style="color:var(--text2);font-size:0.8rem;margin-top:0.3rem"><em>Used by: Judge Calibration tab</em></p>
        </div>
      </div>

      <!-- Scoring System -->
      <h3 id="doc-scoring" style="color:var(--accent);margin-top:2rem">Scoring System</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;margin-top:0.75rem">
        <div style="background:var(--bg);border-radius:8px;padding:1rem">
          <h4 style="color:var(--accent);margin-bottom:0.5rem">GEval Score</h4>
          <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">LLM-as-judge with chain-of-thought reasoning. The judge model reads the response and scores each criterion 0.0–1.0.</p>
          <p style="color:var(--text2);font-size:0.8rem"><strong>Pros:</strong> Nuanced, catches subtlety<br><strong>Cons:</strong> Non-deterministic (may vary between runs)</p>
        </div>
        <div style="background:var(--bg);border-radius:8px;padding:1rem">
          <h4 style="color:var(--purple);margin-bottom:0.5rem">DAG Score</h4>
          <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Deterministic decision tree. Each criterion checked across 4 dimensions: Addressed, Specificity, Actionability, Accuracy.</p>
          <p style="color:var(--text2);font-size:0.8rem"><strong>Pros:</strong> Reproducible, pinpoints which dimension failed<br><strong>Cons:</strong> Less nuanced than GEval</p>
        </div>
        <div style="background:var(--bg);border-radius:8px;padding:1rem">
          <h4 style="color:var(--green);margin-bottom:0.5rem">Combined Score</h4>
          <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem"><strong>60% GEval + 40% DAG</strong>. Balances nuance with reproducibility. Grade is based on this combined score.</p>
          <table style="font-size:0.75rem;color:var(--text2);margin-top:0.3rem">
            <tr><td>A+ 95%+</td><td>A 90%</td><td>A- 85%</td></tr>
            <tr><td>B+ 80%</td><td>B 75%</td><td>B- 70%</td></tr>
            <tr><td>C+ 65%</td><td>C 60%</td><td>D &lt;60%</td></tr>
          </table>
        </div>
      </div>

      <h4 style="color:var(--text);margin-top:1rem">DAG Dimensions (per criterion)</h4>
      <table class="history-table" style="font-size:0.85rem;margin-top:0.5rem">
        <thead><tr><th>Dimension</th><th>What it checks</th><th>Weight</th><th>Example pass</th><th>Example fail</th></tr></thead>
        <tbody>
          <tr><td style="color:var(--accent);font-weight:600">Addressed</td><td>Is the criterion mentioned at all?</td><td>3x</td><td>"Use private endpoints for ADLS"</td><td>No mention of endpoints</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Specificity</td><td>Named services, versions, concrete values?</td><td>3x</td><td>"AES-256 with CMK in FIPS 140-2 Key Vault"</td><td>"Use encryption"</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Actionability</td><td>Steps, commands, architecture decisions?</td><td>2x</td><td>"1. Create role 2. Add DAX filter 3. Test"</td><td>"Set up security"</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Accuracy</td><td>Technically correct, no errors?</td><td>2x</td><td>Correct DAX syntax</td><td>Non-existent function name</td></tr>
        </tbody>
      </table>

      <h4 style="color:var(--text);margin-top:1rem">Scoring Rubric (used by judge)</h4>
      <table class="history-table" style="font-size:0.85rem;margin-top:0.5rem">
        <thead><tr><th>Score</th><th>Level</th><th>Description</th><th>Example</th></tr></thead>
        <tbody>
          <tr><td style="color:var(--green);font-weight:700">1.0</td><td>Excellent</td><td>Specific details, exact technologies, actionable</td><td>"AES-256 with CMK in FIPS 140-2 Level 2 HSM-backed Key Vault"</td></tr>
          <tr><td style="color:var(--green)">0.8</td><td>Good</td><td>Mostly specific, correct direction, minor gap</td><td>"Customer-managed keys in Azure Key Vault"</td></tr>
          <tr><td style="color:var(--yellow)">0.6</td><td>Adequate</td><td>Mentioned with some detail, lacks specificity</td><td>"Use Azure Key Vault for key management"</td></tr>
          <tr><td style="color:var(--orange)">0.4</td><td>Weak</td><td>Vague, missing critical details</td><td>"Encryption should be used"</td></tr>
          <tr><td style="color:var(--red)">0.2</td><td>Poor</td><td>Mentioned in passing, no useful guidance</td><td>"Security is important"</td></tr>
          <tr><td style="color:var(--red);font-weight:700">0.0</td><td>Not Addressed</td><td>Not mentioned or contradicts</td><td>Topic completely absent</td></tr>
        </tbody>
      </table>

      <!-- Tab Guide -->
      <h3 id="doc-tabs" style="color:var(--accent);margin-top:2rem">Tab Guide</h3>
      <table class="history-table" style="font-size:0.85rem;margin-top:0.5rem">
        <thead><tr><th>Tab</th><th>Purpose</th><th>When to use</th></tr></thead>
        <tbody>
          <tr><td style="color:var(--accent);font-weight:600">Run Evaluation</td><td>Score a system prompt against test criteria</td><td>Testing a new/updated prompt, comparing models, tracking quality over time</td></tr>
          <tr><td style="color:var(--purple);font-weight:600">A/B Comparison</td><td>Compare two configurations side by side</td><td>Weak vs strong prompt, GPT-4o vs GPT-4.1, local vs deployed prompt</td></tr>
          <tr><td style="color:var(--red);font-weight:600">Red Team</td><td>Adversarial security testing</td><td>Testing resistance to prompt injection, bias probing, PII extraction</td></tr>
          <tr><td style="color:var(--green);font-weight:600">Generate Tests</td><td>Create new test cases from reference docs or manually</td><td>Expanding test coverage, creating domain-specific tests</td></tr>
          <tr><td style="color:var(--yellow);font-weight:600">Judge Calibration</td><td>Validate judge accuracy with gold standard</td><td>After changing judge model, adding reference docs, or updating rubric</td></tr>
          <tr><td style="color:var(--text2);font-weight:600">Docs</td><td>This page — documentation and reference</td><td>Onboarding new team members, understanding concepts</td></tr>
        </tbody>
      </table>

      <!-- Configuration -->
      <h3 id="doc-config" style="color:var(--accent);margin-top:2rem">Configuration (.env)</h3>
      <table class="history-table" style="font-size:0.85rem;margin-top:0.5rem">
        <thead><tr><th>Variable</th><th>Description</th><th>Example</th></tr></thead>
        <tbody>
          <tr><td style="font-family:monospace;color:var(--accent)">EVAL_MODE</td><td><strong>demo</strong>: uses pre-generated responses, no API keys needed — for showcasing and testing the framework without costs.<br><strong>live</strong>: makes real API calls to your configured model — responses are generated by the actual LLM and scored by the judge model. Shown as <span style="background:var(--green);color:#000;padding:0.1rem 0.3rem;border-radius:3px;font-size:0.75rem;font-weight:600">LIVE</span> or <span style="background:var(--yellow);color:#000;padding:0.1rem 0.3rem;border-radius:3px;font-size:0.75rem;font-weight:600">DEMO</span> badge in the header.</td><td>live</td></tr>
          <tr><td style="font-family:monospace;color:var(--accent)">TARGET_PROVIDER</td><td>LLM provider for the model being tested</td><td>azure, openai, anthropic, google, ollama</td></tr>
          <tr><td style="font-family:monospace;color:var(--accent)">TARGET_MODEL</td><td>Model name / deployment</td><td>gpt-4o, gpt-4.1, claude-sonnet-4</td></tr>
          <tr><td style="font-family:monospace;color:var(--accent)">TARGET_BASE_URL</td><td>API endpoint</td><td>https://your-resource.openai.azure.com</td></tr>
          <tr><td style="font-family:monospace;color:var(--accent)">TARGET_API_KEY</td><td>API key for target model</td><td>(set in .env, never commit)</td></tr>
          <tr><td style="font-family:monospace;color:var(--accent)">JUDGE_PROVIDER</td><td>Provider for the judge model (falls back to target)</td><td>azure</td></tr>
          <tr><td style="font-family:monospace;color:var(--accent)">JUDGE_MODEL</td><td>Judge model name</td><td>gpt-5.4</td></tr>
          <tr><td style="font-family:monospace;color:var(--accent)">TARGET_SYSTEM_PROMPT</td><td>Prompt source: local, none, custom:..., file:path</td><td>local</td></tr>
          <tr><td style="font-family:monospace;color:var(--accent)">EVAL_ROLE</td><td>Default role for evaluation</td><td>power_bi_engineer</td></tr>
        </tbody>
      </table>

      <!-- Roles -->
      <h3 id="doc-roles" style="color:var(--accent);margin-top:2rem">Available Roles</h3>
      <table class="history-table" style="font-size:0.85rem;margin-top:0.5rem">
        <thead><tr><th>Role</th><th>Domain</th><th>Tests</th><th>Judge Context</th><th>Key files</th></tr></thead>
        <tbody>
          {% for r in roles %}
          <tr>
            <td style="color:var(--accent);font-weight:600">{{ r.slug }}</td>
            <td>{{ r.domain }}</td>
            <td>{{ 'Yes' if r.has_tests else 'No' }}</td>
            <td>{{ 'Yes' if r.has_tests else '-' }}</td>
            <td style="font-size:0.75rem;font-family:monospace">prompts/{{ r.slug }}.py, test_suites/{{ r.slug }}_tests.py</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>

      <!-- Glossary -->
      <h3 id="doc-glossary" style="color:var(--accent);margin-top:2rem">Glossary</h3>
      <table class="history-table" style="font-size:0.85rem;margin-top:0.5rem">
        <thead><tr><th style="width:180px">Term</th><th>Definition</th></tr></thead>
        <tbody>
          <tr><td style="color:var(--accent);font-weight:600">GEval</td><td>DeepEval's LLM-as-judge metric. Uses chain-of-thought reasoning to score responses. Non-deterministic — scores may vary between runs.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">DAG Metric</td><td>Deep Acyclic Graph — deterministic decision tree scoring. Same response always gets the same score. Evaluates 4 dimensions per criterion.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">DeepEval</td><td>Open-source LLM evaluation framework. Provides GEval, safety metrics, hallucination detection, and test infrastructure.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">DeepTeam</td><td>Adversarial testing framework. Generates prompt injection, encoding attacks, and bias probes to test AI safety.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">BYOK</td><td>Bring Your Own Key — the framework works with any LLM provider (OpenAI, Azure, Anthropic, Google, Ollama).</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Scoring Rubric</td><td>A 6-level guide (1.0 to 0.0) injected into every judge prompt defining what each score level looks like.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Judge Context</td><td>Reference documents (docs/{role}/) injected into judge prompts so it scores against your standards, not generic knowledge.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Hallucination</td><td>When the model fabricates facts, invents regulation citations, or contradicts the provided ground truth context.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">PII Leakage</td><td>Model response contains real personally identifiable information. Illustrative examples (john@contoso.com) are not flagged.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Red Teaming</td><td>Adversarial testing — deliberately trying to make the AI misbehave (leak data, show bias, bypass guardrails).</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Gold Standard</td><td>Pre-scored test responses (excellent/adequate/poor/misleading) used to validate judge accuracy in the Calibration tab.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Consolidated Score</td><td>60% GEval + 40% DAG. The grade (A+ through D) is based on this combined score.</td></tr>
          <tr><td style="color:var(--accent);font-weight:600">Multi-Run Averaging</td><td>Running the same evaluation N times and averaging scores to reduce variance from non-deterministic responses.</td></tr>
        </tbody>
      </table>

      <!-- Code Examples -->
      <h3 id="doc-code" style="color:var(--accent);margin-top:2rem">Code Examples</h3>

      <h4 style="color:var(--text);margin-top:1rem">Adding a new role</h4>
      <pre style="background:var(--bg);padding:1rem;border-radius:8px;font-size:0.8rem;overflow-x:auto;color:var(--text2)"><code># 1. Create prompts/my_role.py
SYSTEM_PROMPT = "You are an expert..."
PROMPT_METADATA = {"name": "My Role", "version": "1.0.0",
    "domain": "My Domain", "author": "...", "target_model": "gpt-4o"}

# 2. Create test_suites/my_role_tests.py
TEST_CASES = [{"id": "TEST-01", "category": "...",
    "question": "...", "criteria": ["...", "..."], "weight": 2}]
CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))

# 3. (Optional) Add reference docs: docs/my_role/standards.md
# 4. The registry auto-discovers it — no other changes needed</code></pre>

      <h4 style="color:var(--text);margin-top:1rem">Adding judge context (reference docs)</h4>
      <pre style="background:var(--bg);padding:1rem;border-radius:8px;font-size:0.8rem;overflow-x:auto;color:var(--text2)"><code># Create docs/{role_slug}/ folder with .md or .txt files
# Example: docs/power_bi_engineer/power_bi_standards.md
# These are automatically loaded and injected into every judge prompt
# The judge then scores against YOUR standards, not generic knowledge</code></pre>

      <h4 style="color:var(--text);margin-top:1rem">CLI usage</h4>
      <pre style="background:var(--bg);padding:1rem;border-radius:8px;font-size:0.8rem;overflow-x:auto;color:var(--text2)"><code># List all roles
python run_evaluation.py --list-roles

# Run evaluation
python run_evaluation.py --role power_bi_engineer

# Run A/B comparison
python run_comparison.py --role azure_data_architect

# Generate test cases from reference docs
python generate_tests.py --role power_bi_engineer --count 10

# Start web dashboard
python app.py</code></pre>

      <!-- FAQ -->
      <!-- Features -->
      <h3 id="doc-features" style="color:var(--purple);margin-top:2rem">Features Guide</h3>

      <h4 style="color:var(--text);margin-top:1rem">Manage Roles</h4>
      <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:1rem">
        <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Create, edit, and manage AI assistant roles entirely from the UI. No need to edit code files manually.</p>
        <table class="history-table" style="font-size:0.8rem;margin-top:0.5rem">
          <thead><tr><th>Action</th><th>How</th><th>What happens</th></tr></thead>
          <tbody>
            <tr><td style="color:var(--accent)">Create Role</td><td>Fill in slug, name, domain, prompt → Create</td><td>Creates <code>prompts/{slug}.py</code>, <code>test_suites/{slug}_tests.py</code>, <code>docs/{slug}/</code></td></tr>
            <tr><td style="color:var(--accent)">Edit Role</td><td>Click role card → edit fields → Update</td><td>Modifies the Python file directly + saves version snapshot</td></tr>
            <tr><td style="color:var(--accent)">Upload Files</td><td>Use upload buttons for prompt (.md/.txt), context (multiple .md/.txt), tests (.json)</td><td>File content loaded into form fields for review before saving</td></tr>
            <tr><td style="color:var(--accent)">Custom Prompt</td><td>Select "Custom (paste your own)" in evaluation dropdown</td><td>Sends your pasted text as the system prompt without modifying files</td></tr>
          </tbody>
        </table>
        <p style="color:var(--text2);font-size:0.8rem;margin-top:0.5rem"><strong>Note:</strong> Changes are written to codebase files. Use <code>git diff</code> to review before committing.</p>
      </div>

      <h4 style="color:var(--text);margin-top:1rem">Version Control</h4>
      <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:1rem">
        <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Every role change is versioned automatically. Track what changed, when, and why.</p>
        <table class="history-table" style="font-size:0.8rem;margin-top:0.5rem">
          <thead><tr><th>Feature</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td style="color:var(--accent)">Auto-versioning</td><td>Every create/update saves a snapshot with timestamp, content hash, and change note</td></tr>
            <tr><td style="color:var(--accent)">Change Notes</td><td>Required on update — describe what you changed and why (e.g., "Added DAX performance guidelines")</td></tr>
            <tr><td style="color:var(--accent)">View Version</td><td>See the full prompt and context for any past version</td></tr>
            <tr><td style="color:var(--accent)">Side-by-Side Diff</td><td>Compare two versions side-by-side — previous (red) vs current (green) for both prompt and context</td></tr>
            <tr><td style="color:var(--accent)">Restore Version</td><td>Load any past version into the form and re-save to roll back changes</td></tr>
            <tr><td style="color:var(--accent)">Content Hashes</td><td>Quick visual indicator of whether prompt/tests/context changed between versions</td></tr>
          </tbody>
        </table>
      </div>

      <h4 style="color:var(--text);margin-top:1rem">Auto-Improve Prompt</h4>
      <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:1rem">
        <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Automatically generates an improved system prompt based on evaluation weaknesses.</p>
        <ol style="color:var(--text2);font-size:0.85rem;padding-left:1.2rem;line-height:1.8">
          <li>Run an evaluation → see results with score and weak areas</li>
          <li>Click <strong style="color:var(--purple)">"Auto-Improve Prompt"</strong> button in the results</li>
          <li>System analyzes criteria that scored below 70% and failed DAG dimensions</li>
          <li>Judge model generates an improved prompt addressing the weak areas</li>
          <li>Review the changes summary and the full improved prompt</li>
          <li>Click <strong>"Evaluate This Prompt"</strong> to test the improvement immediately</li>
          <li>Click <strong>"Copy to Clipboard"</strong> to save the improved prompt</li>
        </ol>
        <p style="color:var(--text2);font-size:0.8rem;margin-top:0.5rem"><strong>Tip:</strong> The improver keeps everything that's working well and only adds targeted instructions for weak areas.</p>
      </div>

      <h4 style="color:var(--text);margin-top:1rem">Multi-Run Averaging</h4>
      <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:1rem">
        <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Reduce score variance by running the same evaluation multiple times and averaging.</p>
        <table class="history-table" style="font-size:0.8rem;margin-top:0.5rem">
          <thead><tr><th>Runs</th><th>Use case</th><th>Time</th></tr></thead>
          <tbody>
            <tr><td>1x</td><td>Quick check, development iteration</td><td>~5 min</td></tr>
            <tr><td>2x</td><td>Better signal, moderate confidence</td><td>~10 min</td></tr>
            <tr><td>3x (avg)</td><td>Recommended for tracking — good balance of speed and reliability</td><td>~15 min</td></tr>
            <tr><td>5x (avg)</td><td>Highest confidence — use for final benchmarks or comparisons</td><td>~25 min</td></tr>
          </tbody>
        </table>
        <p style="color:var(--text2);font-size:0.8rem;margin-top:0.5rem"><strong>Why it matters:</strong> Single runs can vary 5-10% due to non-deterministic model responses. Averaging 3x reduces this to ~2-3% variance.</p>
      </div>

      <h4 style="color:var(--text);margin-top:1rem">Judge Calibration</h4>
      <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:1rem">
        <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Validates that your judge model scores accurately using a gold standard test set.</p>
        <table class="history-table" style="font-size:0.8rem;margin-top:0.5rem">
          <thead><tr><th>Gold Standard Type</th><th>Count</th><th>Purpose</th></tr></thead>
          <tbody>
            <tr><td style="color:var(--green)">Excellent responses</td><td>2</td><td>Detailed, specific, correct — should score ~0.9</td></tr>
            <tr><td style="color:var(--yellow)">Adequate responses</td><td>2</td><td>Mentioned but vague — should score ~0.3</td></tr>
            <tr><td style="color:var(--red)">Poor responses</td><td>2</td><td>Generic, useless — should score ~0.0</td></tr>
            <tr><td style="color:var(--orange)">Misleading responses</td><td>2</td><td>Confidently wrong (recommends deprecated tech) — should score 0.0</td></tr>
          </tbody>
        </table>
        <p style="color:var(--text2);font-size:0.85rem;margin-top:0.5rem"><strong>Key metrics:</strong></p>
        <ul style="color:var(--text2);font-size:0.85rem;padding-left:1.2rem">
          <li><strong>Accuracy:</strong> % of scores within 0.25 of expected — target &gt; 80%</li>
          <li><strong>Discrimination:</strong> gap between excellent and poor avg scores — target &gt; 0.5</li>
          <li><strong>Consistency Issues:</strong> cases where excellent scored low or poor scored high</li>
        </ul>
        <p style="color:var(--text2);font-size:0.8rem;margin-top:0.5rem"><strong>When to run:</strong> After changing judge model, adding reference docs, or updating the scoring rubric.</p>
      </div>

      <h4 style="color:var(--text);margin-top:1rem">Domain-Aware Judge</h4>
      <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:1rem">
        <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Two mechanisms make the judge score against your standards, not generic knowledge:</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:0.5rem">
          <div style="border:1px solid var(--surface2);border-radius:6px;padding:0.75rem">
            <h5 style="color:var(--accent);margin-bottom:0.3rem">Judge Context Injection</h5>
            <p style="color:var(--text2);font-size:0.8rem">Reference docs from <code>docs/{role}/</code> are injected into every GEval prompt. The judge sees your org's standards and scores accordingly.</p>
            <p style="color:var(--text2);font-size:0.8rem;margin-top:0.3rem"><em>Example: A response saying "use encryption" scores lower than "use AES-256 with CMK in FIPS 140-2 Key Vault" because the judge knows your standard requires the latter.</em></p>
          </div>
          <div style="border:1px solid var(--surface2);border-radius:6px;padding:0.75rem">
            <h5 style="color:var(--accent);margin-bottom:0.3rem">Scoring Rubric</h5>
            <p style="color:var(--text2);font-size:0.8rem">A 6-level rubric (1.0 Excellent → 0.0 Not Addressed) is included in every judge prompt, with concrete examples for each level.</p>
            <p style="color:var(--text2);font-size:0.8rem;margin-top:0.3rem"><em>The judge applies the same scoring standard to every criterion, regardless of topic.</em></p>
          </div>
        </div>
        <p style="color:var(--text2);font-size:0.8rem;margin-top:0.5rem"><strong>Status in reports:</strong> Check "Evaluation Setup" section → Judge Context shows ACTIVE/NONE with doc names and char count.</p>
      </div>

      <h4 style="color:var(--text);margin-top:1rem">Safety Metrics</h4>
      <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:1rem">
        <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Every model response is automatically checked for safety issues:</p>
        <table class="history-table" style="font-size:0.8rem;margin-top:0.5rem">
          <thead><tr><th>Metric</th><th>What it detects</th><th>Scoring</th></tr></thead>
          <tbody>
            <tr><td style="color:var(--accent)">Bias</td><td>Gender, racial, political, religious bias</td><td>0.0 = no bias, 1.0 = fully biased</td></tr>
            <tr><td style="color:var(--accent)">Toxicity</td><td>Personal attacks, hate speech, dismissive language</td><td>0.0 = professional, 1.0 = toxic</td></tr>
            <tr><td style="color:var(--accent)">PII Leakage</td><td>Real PII/PHI in responses (not illustrative examples)</td><td>0.0 = safe, 1.0 = PII found</td></tr>
            <tr><td style="color:var(--accent)">Hallucination</td><td>Fabricated facts contradicting ground truth context</td><td>0.0 = faithful, 1.0 = hallucinated</td></tr>
          </tbody>
        </table>
        <p style="color:var(--text2);font-size:0.8rem;margin-top:0.5rem"><strong>Pass threshold:</strong> score &le; 0.5. Responses above 0.5 are flagged with full details in the report.</p>
        <p style="color:var(--text2);font-size:0.8rem"><strong>PII note:</strong> Illustrative examples (john@contoso.com in tutorials, column names like 'Email') are NOT flagged — only real PII that could identify an actual person.</p>
      </div>

      <h3 id="doc-faq" style="color:var(--accent);margin-top:2rem">FAQ</h3>

      <details style="margin-bottom:0.75rem">
        <summary style="cursor:pointer;color:var(--text);font-weight:600;font-size:0.9rem">Why do scores vary between runs?</summary>
        <p style="color:var(--text2);font-size:0.85rem;padding:0.5rem 0 0 1rem">The target model doesn't give identical responses every time (temperature > 0). GEval scoring is also non-deterministic. Use <strong>multi-run averaging (3x)</strong> to get more stable scores. DAG scores are deterministic per response — variance comes from different responses, not different scoring.</p>
      </details>

      <details style="margin-bottom:0.75rem">
        <summary style="cursor:pointer;color:var(--text);font-weight:600;font-size:0.9rem">Why is DAG score lower than GEval?</summary>
        <p style="color:var(--text2);font-size:0.85rem;padding:0.5rem 0 0 1rem">DAG uses a strict binary decision tree (Addressed? Specific? Actionable? Accurate?). GEval is more forgiving — it gives partial credit for vague but directionally correct answers. The gap tells you how much "soft credit" GEval is giving vs the strict standard.</p>
      </details>

      <details style="margin-bottom:0.75rem">
        <summary style="cursor:pointer;color:var(--text);font-weight:600;font-size:0.9rem">What should I use as the judge model?</summary>
        <p style="color:var(--text2);font-size:0.85rem;padding:0.5rem 0 0 1rem">Use a <strong>different, stronger model</strong> than the target. If testing GPT-4o, judge with GPT-5.4 or Claude. Never use the same model as both target and judge (self-grading bias). Run <strong>Judge Calibration</strong> to verify accuracy.</p>
      </details>

      <details style="margin-bottom:0.75rem">
        <summary style="cursor:pointer;color:var(--text);font-weight:600;font-size:0.9rem">How do I improve a low score?</summary>
        <p style="color:var(--text2);font-size:0.85rem;padding:0.5rem 0 0 1rem">1. Check which criteria scored low in the report. 2. Look at DAG dimensions — did Specificity or Actionability fail? 3. Add targeted instructions to the system prompt (e.g., "always mention specific Azure SKUs"). 4. Use <strong>Auto-Improve Prompt</strong> to generate an improved version automatically. 5. Re-evaluate to verify improvement.</p>
      </details>

      <details style="margin-bottom:0.75rem">
        <summary style="cursor:pointer;color:var(--text);font-weight:600;font-size:0.9rem">Why does Judge Context matter?</summary>
        <p style="color:var(--text2);font-size:0.85rem;padding:0.5rem 0 0 1rem">Without context, the judge uses generic knowledge. With your reference docs, it scores against <strong>your organization's standards</strong>. A generic "use encryption" gets a lower score when the judge knows your standard requires "AES-256 with CMK in FIPS 140-2 Level 2 HSM-backed Key Vault."</p>
      </details>

      <details style="margin-bottom:0.75rem">
        <summary style="cursor:pointer;color:var(--text);font-weight:600;font-size:0.9rem">When should I use each System Prompt option?</summary>
        <div style="color:var(--text2);font-size:0.85rem;padding:0.5rem 0 0 1rem">
          <p><strong style="color:var(--accent)">Local (from codebase)</strong> — Sends the prompt from <code>prompts/{role}.py</code>. Use this for prompt development and iteration. Most common choice.</p>
          <p style="margin-top:0.5rem"><strong style="color:var(--accent)">Custom (paste your own)</strong> — Paste any prompt text directly. Use this to test a specific version without modifying code files.</p>
          <p style="margin-top:0.5rem"><strong style="color:var(--accent)">None — no prompt sent</strong> — Sends NO system message to the API. <strong>Only works with Azure AI Foundry Assistants</strong> where the prompt is baked into the assistant definition.</p>
          <p style="margin-top:0.5rem;color:var(--yellow)"><strong>Important:</strong> Standard Azure OpenAI deployments do NOT retain system prompts via API. The system message you configure in Azure OpenAI Studio Playground is only used in the Playground UI — API calls always require the prompt to be passed explicitly. Use "Local" or "Custom" for standard deployments.</p>
        </div>
      </details>

      <details style="margin-bottom:0.75rem">
        <summary style="cursor:pointer;color:var(--text);font-weight:600;font-size:0.9rem">How do I add a new role?</summary>
        <p style="color:var(--text2);font-size:0.85rem;padding:0.5rem 0 0 1rem">Create two files: <code>prompts/my_role.py</code> (with SYSTEM_PROMPT and PROMPT_METADATA) and <code>test_suites/my_role_tests.py</code> (with TEST_CASES). Optionally add reference docs in <code>docs/my_role/</code>. The registry auto-discovers new roles — no other changes needed.</p>
      </details>

    </div>
  </div>

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
  refreshHistory();
}

// Load history on page load
document.addEventListener('DOMContentLoaded', () => refreshHistory());

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
  // No-op — header no longer shows target/judge (moved to Settings)
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
  const prompt = getPromptValue('evalPrompt', 'evalCustomPrompt');
  const runs = parseInt(document.getElementById('evalRuns').value);
  document.getElementById('btnEval').disabled = true;
  showProgress('eval');
  if (runs > 1) {
    document.getElementById('evalText').textContent = `Running ${runs}x evaluations for averaging...`;
  }

  fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, run_type: 'evaluation', model, prompt_source: prompt, runs})
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

function toggleCustomPrompt(textareaId, value) {
  const ta = document.getElementById(textareaId);
  if (ta) ta.style.display = value === 'custom' ? 'block' : 'none';
}

function getPromptValue(selectId, textareaId) {
  const sel = document.getElementById(selectId);
  if (sel.value === 'custom') {
    return 'custom:' + document.getElementById(textareaId).value;
  }
  return sel.value;
}

// ── Theme ──
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  document.getElementById('themeBtn').textContent = next === 'dark' ? '☀️ Light' : '🌙 Dark';
}

// Apply saved theme on load
(function() {
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  const btn = document.getElementById('themeBtn');
  if (btn) btn.textContent = saved === 'dark' ? '☀️ Light' : '🌙 Dark';
})();

function toggleSettings() {
  const modal = document.getElementById('settingsModal');
  if (modal.style.display === 'none' || !modal.style.display) {
    modal.style.display = 'block';
    loadSettings();
  } else {
    modal.style.display = 'none';
  }
}

// ── Settings ──
function loadSettings() {
  fetch('/api/settings').then(r => r.json()).then(data => {
    const s = data.settings || {};
    document.getElementById('setTargetProvider').value = s.TARGET_PROVIDER || 'azure';
    document.getElementById('setTargetKey').value = s.TARGET_API_KEY || '';
    document.getElementById('setTargetModel').value = s.TARGET_MODEL || s.TARGET_DEPLOYMENT || '';
    document.getElementById('setTargetURL').value = s.TARGET_BASE_URL || '';
    document.getElementById('setTargetVersion').value = s.TARGET_API_VERSION || '2024-08-01-preview';
    document.getElementById('setJudgeProvider').value = s.JUDGE_PROVIDER || '';
    document.getElementById('setJudgeKey').value = s.JUDGE_API_KEY || '';
    document.getElementById('setJudgeModel').value = s.JUDGE_MODEL || s.JUDGE_DEPLOYMENT || '';
    document.getElementById('setJudgeURL').value = s.JUDGE_BASE_URL || '';

    // Load assistant mappings
    const ra = data.role_assistants || {};
    for (const [slug, id] of Object.entries(ra)) {
      const el = document.getElementById('asst_' + slug);
      if (el) el.value = id;
    }
  });
}

function saveSettings() {
  const settings = {
    // EVAL_MODE removed — always live
    TARGET_PROVIDER: document.getElementById('setTargetProvider').value,
    TARGET_API_KEY: document.getElementById('setTargetKey').value,
    TARGET_MODEL: document.getElementById('setTargetModel').value,
    TARGET_DEPLOYMENT: document.getElementById('setTargetModel').value,
    TARGET_BASE_URL: document.getElementById('setTargetURL').value,
    TARGET_API_VERSION: document.getElementById('setTargetVersion').value,
    JUDGE_PROVIDER: document.getElementById('setJudgeProvider').value,
    JUDGE_API_KEY: document.getElementById('setJudgeKey').value,
    JUDGE_MODEL: document.getElementById('setJudgeModel').value,
    JUDGE_DEPLOYMENT: document.getElementById('setJudgeModel').value,
    JUDGE_BASE_URL: document.getElementById('setJudgeURL').value,
  };

  // Collect assistant mappings (skip status elements)
  const role_assistants = {};
  document.querySelectorAll('input[id^="asst_"]').forEach(el => {
    if (el.id.startsWith('asst_status_')) return;
    const slug = el.id.replace('asst_', '');
    if (el.value && el.value.trim()) role_assistants[slug] = el.value.trim();
  });

  fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({settings, role_assistants})
  }).then(r => r.json()).then(d => {
    const flash = document.getElementById('settingsResult');
    flash.classList.add('active');
    if (d.success) {
      flash.className = 'result-flash active success';
      flash.innerHTML = '<strong>Settings saved!</strong> Restart the dashboard to apply changes.';
    } else {
      flash.className = 'result-flash active error';
      flash.innerHTML = '<strong>Error:</strong> ' + (d.error || d.message);
    }
  });
}

function testConnection() {
  const status = document.getElementById('connectionStatus');
  status.innerHTML = '<span style="color:var(--yellow)">Testing connection...</span>';

  fetch('/api/test-connection', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      provider: document.getElementById('setTargetProvider').value,
      base_url: document.getElementById('setTargetURL').value,
      api_key: document.getElementById('setTargetKey').value,
      model: document.getElementById('setTargetModel').value,
      api_version: document.getElementById('setTargetVersion').value,
    })
  }).then(r => r.json()).then(d => {
    if (d.success) {
      status.innerHTML = '<span style="color:var(--green);font-weight:600">&#10004; ' + d.message + '</span>';
    } else {
      status.innerHTML = '<span style="color:var(--red)">&#10008; ' + d.message + '</span>';
    }
  }).catch(e => {
    status.innerHTML = '<span style="color:var(--red)">&#10008; Error: ' + e.message + '</span>';
  });
}

function testAllAssistants() {
  document.querySelectorAll('[id^="asst_status_"]').forEach(el => el.textContent = '...');

  document.querySelectorAll('[id^="asst_"]').forEach(el => {
    if (el.id.startsWith('asst_status_')) return;
    const slug = el.id.replace('asst_', '');
    const assistantId = el.value.trim();
    const statusEl = document.getElementById('asst_status_' + slug);
    if (!assistantId) { statusEl.textContent = '—'; return; }

    statusEl.innerHTML = '<span style="color:var(--yellow)">Testing...</span>';
    fetch('/api/test-assistant', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({assistant_id: assistantId})
    }).then(r => r.json()).then(d => {
      if (d.success) {
        statusEl.innerHTML = '<span style="color:var(--green)">&#10004; OK</span>';
      } else {
        statusEl.innerHTML = '<span style="color:var(--red)">&#10008; ' + (d.message||'').substring(0,50) + '</span>';
      }
    }).catch(() => {
      statusEl.innerHTML = '<span style="color:var(--red)">&#10008; Error</span>';
    });
  });
}

// Load settings on tab switch
document.addEventListener('DOMContentLoaded', () => { setTimeout(loadSettings, 500); });

// ── File Upload Handlers ──
function handlePromptUpload(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById('mgrPrompt').value = e.target.result;
    document.getElementById('mgrPromptFileStatus').textContent = 'Loaded: ' + file.name + ' (' + e.target.result.length + ' chars)';
  };
  reader.readAsText(file);
}

function handleContextUpload(input) {
  const files = input.files;
  if (!files.length) return;
  let combined = '';
  let loaded = 0;
  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = (e) => {
      combined += '\\n\\n--- ' + file.name + ' ---\\n' + e.target.result;
      loaded++;
      if (loaded === files.length) {
        document.getElementById('mgrContext').value = combined.trim();
        document.getElementById('mgrContextFileStatus').textContent = loaded + ' file(s) loaded (' + combined.length + ' chars)';
      }
    };
    reader.readAsText(file);
  });
}

function handleTestsUpload(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const tests = JSON.parse(e.target.result);
      document.getElementById('mgrTests').value = JSON.stringify(tests, null, 2);
      document.getElementById('mgrTestsFileStatus').textContent = 'Loaded: ' + file.name + ' (' + (Array.isArray(tests) ? tests.length + ' tests' : 'parsed') + ')';
    } catch(err) {
      document.getElementById('mgrTestsFileStatus').textContent = 'Error: ' + err.message;
    }
  };
  reader.readAsText(file);
}

// ── Manage Roles ──
let _editingRole = null;

function loadVersionHistory(slug) {
  fetch('/api/role/versions/' + slug).then(r => r.json()).then(versions => {
    const section = document.getElementById('versionSection');
    const list = document.getElementById('versionList');
    if (!versions.length) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    list.innerHTML = `<table class="history-table" style="font-size:0.8rem">
      <thead><tr><th>#</th><th>Timestamp</th><th>Version</th><th>Change Note</th><th>Prompt</th><th>Tests</th><th>Context</th><th>Actions</th></tr></thead>
      <tbody>${versions.map(v => `<tr>
        <td>${v.id}</td>
        <td style="white-space:nowrap">${(v.timestamp||'').substring(0,10)} ${(v.timestamp||'').substring(11,16)}</td>
        <td>${v.version || '-'}</td>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${v.change_note||''}">${v.change_note || '-'}</td>
        <td>${v.prompt_len ? v.prompt_len + ' chars <span style="color:var(--text2);font-size:0.7rem">(${v.prompt_hash})</span>' : '-'}</td>
        <td>${v.test_len ? v.test_len + ' chars' : '-'}</td>
        <td>${v.context_len ? v.context_len + ' chars' : '-'}</td>
        <td>
          <button class="btn" style="background:var(--surface2);color:var(--text);font-size:0.7rem;padding:0.2rem 0.4rem" onclick="viewVersion(${v.id})">View</button>
          <button class="btn" style="background:var(--surface2);color:var(--text);font-size:0.7rem;padding:0.2rem 0.4rem" onclick="restoreVersion(${v.id})">Restore</button>
          ${v.id > 1 ? '<button class="btn" style="background:var(--purple);color:#fff;font-size:0.7rem;padding:0.2rem 0.4rem" onclick="diffVersions(' + v.id + ')">Diff with prev</button>' : ''}
        </td>
      </tr>`).join('')}</tbody></table>`;
  });
}

function viewVersion(versionId) {
  fetch('/api/role/version/' + versionId).then(r => r.json()).then(v => {
    const diff = document.getElementById('versionDiff');
    diff.style.display = 'block';
    document.getElementById('versionDiffContent').innerHTML = `
      <div style="background:var(--bg);border-radius:8px;padding:1rem">
        <div style="margin-bottom:0.5rem"><strong>Version:</strong> ${v.version || '-'} | <strong>Date:</strong> ${(v.timestamp||'').substring(0,16)} | <strong>Note:</strong> ${v.change_note || '-'}</div>
        <details open><summary style="cursor:pointer;color:var(--accent);font-size:0.85rem">System Prompt (${(v.prompt_text||'').length} chars)</summary>
          <pre style="background:var(--surface);padding:0.75rem;border-radius:6px;margin-top:0.3rem;font-size:0.75rem;max-height:300px;overflow-y:auto;white-space:pre-wrap">${(v.prompt_text||'(empty)').replace(/</g,'&lt;')}</pre>
        </details>
        <details><summary style="cursor:pointer;color:var(--accent);font-size:0.85rem;margin-top:0.5rem">Context (${(v.context_text||'').length} chars)</summary>
          <pre style="background:var(--surface);padding:0.75rem;border-radius:6px;margin-top:0.3rem;font-size:0.75rem;max-height:200px;overflow-y:auto;white-space:pre-wrap">${(v.context_text||'(empty)').replace(/</g,'&lt;')}</pre>
        </details>
      </div>`;
  });
}

function restoreVersion(versionId) {
  if (!confirm('Restore this version? This will overwrite the current prompt and context.')) return;
  fetch('/api/role/version/' + versionId).then(r => r.json()).then(v => {
    document.getElementById('mgrPrompt').value = v.prompt_text || '';
    document.getElementById('mgrContext').value = v.context_text || '';
    if (v.test_cases) document.getElementById('mgrTests').value = v.test_cases;
    alert('Version loaded into form. Click "Update Role" to save.');
  });
}

function diffVersions(versionId) {
  // Load this version and the previous one
  fetch('/api/role/versions/' + _editingRole).then(r => r.json()).then(versions => {
    const idx = versions.findIndex(v => v.id === versionId);
    if (idx < 0 || idx >= versions.length - 1) { alert('No previous version to compare'); return; }
    const currentId = versionId;
    const prevId = versions[idx + 1].id;

    Promise.all([
      fetch('/api/role/version/' + prevId).then(r => r.json()),
      fetch('/api/role/version/' + currentId).then(r => r.json()),
    ]).then(([older, newer]) => {
      const diff = document.getElementById('versionDiff');
      diff.style.display = 'block';

      // Simple line-by-line diff
      const oldLines = (older.prompt_text||'').split('\\n');
      const newLines = (newer.prompt_text||'').split('\\n');
      let diffHtml = '';
      const maxLen = Math.max(oldLines.length, newLines.length);
      for (let i = 0; i < maxLen; i++) {
        const o = oldLines[i] || '';
        const n = newLines[i] || '';
        if (o === n) {
          diffHtml += `<div style="font-size:0.75rem;color:var(--text2);padding:0 0.5rem">${n.replace(/</g,'&lt;') || '&nbsp;'}</div>`;
        } else if (!o && n) {
          diffHtml += `<div style="font-size:0.75rem;background:rgba(34,197,94,0.15);color:var(--green);padding:0 0.5rem">+ ${n.replace(/</g,'&lt;')}</div>`;
        } else if (o && !n) {
          diffHtml += `<div style="font-size:0.75rem;background:rgba(239,68,68,0.15);color:var(--red);padding:0 0.5rem">- ${o.replace(/</g,'&lt;')}</div>`;
        } else {
          diffHtml += `<div style="font-size:0.75rem;background:rgba(239,68,68,0.1);color:var(--red);padding:0 0.5rem">- ${o.replace(/</g,'&lt;')}</div>`;
          diffHtml += `<div style="font-size:0.75rem;background:rgba(34,197,94,0.1);color:var(--green);padding:0 0.5rem">+ ${n.replace(/</g,'&lt;')}</div>`;
        }
      }

      document.getElementById('versionDiffContent').innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:0.5rem">
          <div style="font-size:0.85rem;color:var(--red);font-weight:600">Previous: v${older.id} (${(older.timestamp||'').substring(0,10)}) ${older.change_note ? '— ' + older.change_note : ''}</div>
          <div style="font-size:0.85rem;color:var(--green);font-weight:600">Current: v${newer.id} (${(newer.timestamp||'').substring(0,10)}) ${newer.change_note ? '— ' + newer.change_note : ''}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
          <div style="background:var(--bg);border-radius:8px;padding:0.75rem;max-height:500px;overflow-y:auto;font-family:monospace;font-size:0.75rem;white-space:pre-wrap;border:1px solid rgba(239,68,68,0.3)">${(older.prompt_text||'(empty)').replace(/</g,'&lt;')}</div>
          <div style="background:var(--bg);border-radius:8px;padding:0.75rem;max-height:500px;overflow-y:auto;font-family:monospace;font-size:0.75rem;white-space:pre-wrap;border:1px solid rgba(34,197,94,0.3)">${(newer.prompt_text||'(empty)').replace(/</g,'&lt;')}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:0.75rem">
          <div>
            <div style="font-size:0.8rem;color:var(--text2);margin-bottom:0.3rem">Previous Context (${(older.context_text||'').length} chars)</div>
            <div style="background:var(--bg);border-radius:8px;padding:0.75rem;max-height:200px;overflow-y:auto;font-size:0.75rem;white-space:pre-wrap;border:1px solid rgba(239,68,68,0.2)">${(older.context_text||'(none)').replace(/</g,'&lt;').substring(0,3000)}</div>
          </div>
          <div>
            <div style="font-size:0.8rem;color:var(--text2);margin-bottom:0.3rem">Current Context (${(newer.context_text||'').length} chars)</div>
            <div style="background:var(--bg);border-radius:8px;padding:0.75rem;max-height:200px;overflow-y:auto;font-size:0.75rem;white-space:pre-wrap;border:1px solid rgba(34,197,94,0.2)">${(newer.context_text||'(none)').replace(/</g,'&lt;').substring(0,3000)}</div>
          </div>
        </div>`;
    });
  });
}

function loadRole(slug) {
  fetch('/api/role/' + slug).then(r => r.json()).then(data => {
    if (data.error) { alert(data.error); return; }
    _editingRole = slug;
    document.getElementById('mgrSlug').value = slug;
    document.getElementById('mgrSlug').disabled = true;
    document.getElementById('mgrName').value = data.meta.name || '';
    document.getElementById('mgrDomain').value = data.meta.domain || '';
    document.getElementById('mgrPrompt').value = data.prompt || '';
    document.getElementById('mgrContext').value = data.context_text || '';
    document.getElementById('mgrTests').value = JSON.stringify(data.tests, null, 2);
    document.getElementById('roleFormTitle').textContent = 'Edit Role: ' + slug;
    document.getElementById('mgrCreateBtn').style.display = 'none';
    document.getElementById('mgrUpdateBtn').style.display = 'inline-block';
    document.getElementById('changeNoteRow').style.display = 'block';
    document.getElementById('mgrChangeNote').value = '';
    loadVersionHistory(slug);
  });
}

function clearRoleForm() {
  _editingRole = null;
  document.getElementById('mgrSlug').value = '';
  document.getElementById('mgrSlug').disabled = false;
  document.getElementById('mgrName').value = '';
  document.getElementById('mgrDomain').value = '';
  document.getElementById('mgrPrompt').value = '';
  document.getElementById('mgrContext').value = '';
  document.getElementById('mgrTests').value = '';
  document.getElementById('roleFormTitle').textContent = 'Create New Role';
  document.getElementById('mgrCreateBtn').style.display = 'inline-block';
  document.getElementById('mgrUpdateBtn').style.display = 'none';
  document.getElementById('changeNoteRow').style.display = 'none';
  document.getElementById('versionSection').style.display = 'none';
  document.getElementById('versionDiff').style.display = 'none';
  document.getElementById('mgrResult').classList.remove('active');
}

function createRole() {
  const slug = document.getElementById('mgrSlug').value.trim();
  const name = document.getElementById('mgrName').value.trim();
  const domain = document.getElementById('mgrDomain').value.trim();
  const prompt = document.getElementById('mgrPrompt').value.trim();
  const context = document.getElementById('mgrContext').value.trim();
  let tests = [];
  try {
    const raw = document.getElementById('mgrTests').value.trim();
    if (raw) tests = JSON.parse(raw);
  } catch(e) { alert('Invalid test JSON: ' + e.message); return; }

  if (!slug || !name || !prompt) { alert('Slug, Name, and System Prompt are required.'); return; }

  fetch('/api/role/create', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({slug, name, domain, prompt, context, tests})
  }).then(r => r.json()).then(d => {
    const flash = document.getElementById('mgrResult');
    if (d.success) {
      flash.className = 'result-flash active success';
      flash.innerHTML = '<strong>Role created!</strong> Restart the dashboard to see it in dropdowns. Files: ' + JSON.stringify(d.files_created);
    } else {
      flash.className = 'result-flash active error';
      flash.innerHTML = '<strong>Error:</strong> ' + d.error;
    }
  });
}

function updateRole() {
  if (!_editingRole) return;
  const prompt = document.getElementById('mgrPrompt').value.trim();
  const context = document.getElementById('mgrContext').value.trim();
  const change_note = document.getElementById('mgrChangeNote').value.trim();

  if (!change_note) { alert('Please add a change note describing what you changed.'); return; }

  fetch('/api/role/update', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({slug: _editingRole, prompt, context, change_note})
  }).then(r => r.json()).then(d => {
    const flash = document.getElementById('mgrResult');
    if (d.success) {
      flash.className = 'result-flash active success';
      flash.innerHTML = '<strong>Role updated!</strong> Changes: ' + JSON.stringify(d.updates) + '. Version saved. Restart dashboard to reload prompt changes.';
      loadVersionHistory(_editingRole);
      document.getElementById('mgrChangeNote').value = '';
    } else {
      flash.className = 'result-flash active error';
      flash.innerHTML = '<strong>Error:</strong> ' + (d.error || 'Unknown error');
    }
  });
}

function runCalibration() {
  document.getElementById('btnCalibrate').disabled = true;
  showProgress('cal');

  fetch('/api/calibrate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: '{}'
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'cal'));
}

function improvePrompt() {
  const role = document.getElementById('evalRole').value;
  showProgress('eval');
  document.getElementById('evalBar').style.width = '30%';
  document.getElementById('evalText').textContent = 'Analyzing weaknesses and generating improved prompt...';

  fetch('/api/improve-prompt', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role})
  }).then(r => r.json()).then(d => {
    const iv = setInterval(() => {
      fetch('/api/status/' + d.job_id).then(r => r.json()).then(job => {
        document.getElementById('evalText').textContent = job.current_test || 'Working...';
        if (job.status === 'done' || job.status === 'error') {
          clearInterval(iv);
          document.getElementById('evalProgress').classList.remove('active');
          document.getElementById('btnEval').disabled = false;
          showImprovedPrompt(job);
        }
      });
    }, 2000);
  });
}

function showImprovedPrompt(job) {
  const flash = document.getElementById('evalResult');
  flash.classList.add('active');

  if (job.status === 'error') {
    flash.className = 'result-flash active error';
    flash.innerHTML = `<strong>Error:</strong> ${job.result.error}`;
    return;
  }

  const r = job.result;
  flash.className = 'result-flash active success';
  flash.innerHTML = `
    <div>
      <h3 style="color:var(--purple);margin-bottom:0.5rem">Auto-Improved System Prompt</h3>
      <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.75rem">
        Based on evaluation score of ${r.original_score}% (${r.original_grade}), ${r.weak_areas_addressed.length} weak areas addressed.
      </p>
      <div style="margin-bottom:0.75rem">
        <strong style="font-size:0.85rem">Changes Made:</strong>
        <div style="background:var(--bg);padding:0.75rem;border-radius:6px;margin-top:0.3rem;font-size:0.8rem;white-space:pre-wrap;max-height:150px;overflow-y:auto">${r.changes_summary}</div>
      </div>
      <details>
        <summary style="cursor:pointer;color:var(--accent);font-size:0.85rem;margin-bottom:0.5rem">View improved prompt (${r.improved_prompt.length} chars)</summary>
        <textarea id="improvedPromptText" style="width:100%;min-height:200px;max-height:400px;background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.75rem;font-size:0.8rem;font-family:monospace;resize:vertical">${r.improved_prompt.replace(/</g,'&lt;')}</textarea>
      </details>
      <div style="display:flex;gap:0.5rem;margin-top:0.75rem">
        <button class="btn btn-primary" onclick="evalWithImprovedPrompt()">Evaluate This Prompt</button>
        <button class="btn" style="background:var(--surface2);color:var(--text)" onclick="copyImprovedPrompt()">Copy to Clipboard</button>
      </div>
    </div>`;
}

function evalWithImprovedPrompt() {
  const prompt = document.getElementById('improvedPromptText').value;
  document.getElementById('evalPrompt').value = 'custom';
  document.getElementById('evalCustomPrompt').style.display = 'block';
  document.getElementById('evalCustomPrompt').value = prompt;
  updateHeaderTarget();
  runEval();
}

function copyImprovedPrompt() {
  const text = document.getElementById('improvedPromptText').value;
  navigator.clipboard.writeText(text).then(() => alert('Copied to clipboard!'));
}

function addManualTestCase() {
  const id = document.getElementById('manualId').value.trim();
  const category = document.getElementById('manualCategory').value.trim();
  const question = document.getElementById('manualQuestion').value.trim();
  const criteriaText = document.getElementById('manualCriteria').value.trim();
  const contextText = document.getElementById('manualContext').value.trim();
  const weight = parseInt(document.getElementById('manualWeight').value);

  if (!id || !question || !criteriaText) {
    alert('Please fill in at least Test ID, Question, and Criteria.');
    return;
  }

  const criteria = criteriaText.split('\n').map(c => c.trim()).filter(c => c).slice(0, 5);
  const context = contextText ? contextText.split('\n').map(c => c.trim()).filter(c => c) : undefined;

  const tc = { id, category: category || 'General', question, criteria, weight, _generated: false, _needs_review: false };
  if (context && context.length) tc.context = context;

  _generatedTests.push(tc);

  // Show the test cases section and refresh display
  document.getElementById('genTestCases').style.display = 'block';
  document.getElementById('genTestCount').textContent = '(' + _generatedTests.length + ')';

  // Add to list
  const list = document.getElementById('genTestList');
  list.innerHTML += `
    <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:0.5rem;border-left:3px solid var(--green)">
      <div style="display:flex;gap:0.75rem;align-items:center;margin-bottom:0.5rem">
        <span style="font-weight:700;color:var(--green);font-family:monospace">${tc.id}</span>
        <span style="background:var(--surface2);padding:0.1rem 0.5rem;border-radius:4px;font-size:0.75rem">${tc.category}</span>
        <span style="color:var(--text2);font-size:0.75rem">${tc.criteria.length} criteria | weight: ${tc.weight}x</span>
        <span style="background:var(--green);color:#000;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600">MANUAL</span>
      </div>
      <div style="font-size:0.9rem"><strong>Q:</strong> ${tc.question}</div>
    </div>`;

  // Clear form
  document.getElementById('manualId').value = '';
  document.getElementById('manualQuestion').value = '';
  document.getElementById('manualCriteria').value = '';
  document.getElementById('manualContext').value = '';
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
  showProgress('gen');
  document.getElementById('genBar').style.width = '0%';
  document.getElementById('genText').textContent = 'Running evaluation on generated tests...';

  fetch('/api/eval-generated', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, test_cases: _generatedTests})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'gen'));
}

function runRedTeam() {
  const role = document.getElementById('rtRole').value;
  const model = getModel('rtModel');
  const prompt = getPromptValue('rtPrompt', 'rtCustomPrompt');
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
      run_a: { model: getModel('cmpModelA'), prompt_source: getPromptValue('cmpPromptA', 'cmpCustomPromptA') },
      run_b: { model: getModel('cmpModelB'), prompt_source: getPromptValue('cmpPromptB', 'cmpCustomPromptB') },
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

  if (r.overall_accuracy !== undefined) {
    // Calibration result
    const accColor = r.overall_accuracy >= 80 ? 'var(--green)' : r.overall_accuracy >= 60 ? 'var(--yellow)' : 'var(--red)';
    const discColor = r.discrimination >= 0.5 ? 'var(--green)' : r.discrimination >= 0.3 ? 'var(--yellow)' : 'var(--red)';
    const bq = r.by_quality || {};

    let issuesHtml = '';
    if (r.consistency_issues && r.consistency_issues.length) {
      issuesHtml = '<div style="margin-top:0.75rem"><strong style="color:var(--red);font-size:0.85rem">Issues Found:</strong>' +
        r.consistency_issues.map(i => `<div style="background:var(--bg);padding:0.4rem 0.6rem;border-radius:4px;margin-top:0.3rem;font-size:0.8rem;border-left:3px solid var(--red)">${i}</div>`).join('') + '</div>';
    }

    let detailRows = (r.results || []).map(t => {
      const devColor = t.passed ? 'var(--green)' : 'var(--red)';
      return `<tr>
        <td style="font-family:monospace;color:var(--accent)">${t.test_id}</td>
        <td><span style="background:var(--surface2);padding:0.1rem 0.4rem;border-radius:3px;font-size:0.7rem">${t.quality}</span></td>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${t.criterion}">${t.criterion}</td>
        <td style="text-align:center">${t.expected.toFixed(2)}</td>
        <td style="text-align:center;font-weight:600">${t.geval.toFixed(2)}</td>
        <td style="text-align:center">${t.dag !== null ? t.dag.toFixed(2) : '-'}</td>
        <td style="text-align:center;color:${devColor};font-weight:600">${t.deviation.toFixed(2)}</td>
        <td style="text-align:center">${t.passed ? '<span style="color:var(--green)">PASS</span>' : '<span style="color:var(--red)">FAIL</span>'}</td>
      </tr>`;
    }).join('');

    flash.innerHTML = `
      <div>
        <h3 style="color:var(--accent);margin-bottom:0.75rem">Judge Calibration Results</h3>
        <div style="display:flex;gap:1.5rem;flex-wrap:wrap;margin-bottom:1rem">
          <div style="text-align:center">
            <div style="font-size:2rem;font-weight:800;color:${accColor}">${r.overall_accuracy}%</div>
            <div style="color:var(--text2);font-size:0.8rem">Accuracy</div>
            <div style="color:var(--text2);font-size:0.7rem">${r.passed}/${r.total_tests} within tolerance</div>
          </div>
          <div style="text-align:center">
            <div style="font-size:2rem;font-weight:800;color:${discColor}">${r.discrimination}</div>
            <div style="color:var(--text2);font-size:0.8rem">Discrimination</div>
            <div style="color:var(--text2);font-size:0.7rem">Gap between excellent & poor</div>
          </div>
          <div style="text-align:center">
            <div style="font-size:2rem;font-weight:800">${r.avg_deviation}</div>
            <div style="color:var(--text2);font-size:0.8rem">Avg Deviation</div>
            <div style="color:var(--text2);font-size:0.7rem">From expected scores</div>
          </div>
          <div style="font-size:0.85rem;color:var(--text2)">
            <strong>Avg scores by quality:</strong><br>
            Excellent: ${(bq.excellent||{}).avg_geval||0}<br>
            Adequate: ${(bq.adequate||{}).avg_geval||0}<br>
            Poor: ${(bq.poor||{}).avg_geval||0}<br>
            Misleading: ${(bq.misleading||{}).avg_geval||0}
          </div>
        </div>
        ${issuesHtml}
        <details style="margin-top:0.75rem">
          <summary style="cursor:pointer;color:var(--accent);font-size:0.85rem">View all ${r.total_tests} test results</summary>
          <div style="overflow-x:auto;margin-top:0.5rem">
            <table class="history-table" style="font-size:0.8rem">
              <thead><tr><th>ID</th><th>Quality</th><th>Criterion</th><th>Expected</th><th>GEval</th><th>DAG</th><th>Deviation</th><th>Result</th></tr></thead>
              <tbody>${detailRows}</tbody>
            </table>
          </div>
        </details>
      </div>`;
  } else if (r.test_cases && r.count !== undefined && !r.total_attacks) {
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
          <div>${r.score}%${r.num_runs > 1 ? ' <span style="color:var(--text2);font-size:0.75rem">(avg of ' + r.num_runs + ' runs)</span>' : ''}</div>
        </div>
        ${perf.available ? `<div style="color:var(--text2);font-size:0.85rem">
          Latency: ${perf.avg_latency}s avg | ${perf.p95_latency}s p95<br>
          Tokens: ${(perf.total_tokens||0).toLocaleString()} | Cost: $${(perf.estimated_cost_usd||0).toFixed(4)}
        </div>` : ''}
        <a href="${r.report_url}" target="_blank" class="result-link">View Full Report &#8594;</a>
        <button class="btn" style="background:var(--purple);color:#fff;font-size:0.8rem;padding:0.4rem 0.8rem" onclick="improvePrompt()">Auto-Improve Prompt</button>
      </div>`;
  }
}

function refreshHistory() {
  fetch('/api/history').then(r => r.json()).then(runs => {
    // Evaluation history
    const evalRuns = runs.filter(r => r.run_type === 'evaluation');
    const evalEl = document.getElementById('evalHistory');
    if (evalEl) evalEl.innerHTML = evalRuns.length ? buildHistoryTable(evalRuns) : '<p style="color:var(--text2);font-size:0.85rem;padding:0.5rem">No evaluations yet.</p>';

    // Comparison history
    const cmpRuns = runs.filter(r => r.run_type && r.run_type.startsWith('comparison'));
    const cmpEl = document.getElementById('cmpHistory');
    if (cmpEl) cmpEl.innerHTML = cmpRuns.length ? buildComparisonTable(cmpRuns) : '<p style="color:var(--text2);font-size:0.85rem;padding:0.5rem">No comparisons yet.</p>';

    // Generated test evaluation history
    const genRuns = runs.filter(r => r.run_type === 'eval_generated');
    const genEl = document.getElementById('genHistory');
    if (genEl) genEl.innerHTML = genRuns.length ? buildGenEvalTable(genRuns) : '<p style="color:var(--text2);font-size:0.85rem;padding:0.5rem">No generated test evaluations yet.</p>';

    // Red team history
    const rtRuns = runs.filter(r => r.run_type === 'red_team');
    const rtEl = document.getElementById('rtHistory');
    if (rtEl) rtEl.innerHTML = rtRuns.length ? buildRedTeamTable(rtRuns) : '<p style="color:var(--text2);font-size:0.85rem;padding:0.5rem">No red team runs yet.</p>';

    // Calibration history (separate table)
    fetch('/api/calibration-history').then(r => r.json()).then(calRuns => {
      const calEl = document.getElementById('calHistory');
      if (calEl) calEl.innerHTML = calRuns.length ? buildCalibrationTable(calRuns) : '<p style="color:var(--text2);font-size:0.85rem;padding:0.5rem">No calibration runs yet.</p>';
    }).catch(() => {});
  });
}

function buildHistoryTable(runs) {
  // Evaluation tab: full scoring details
  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>#</th><th>Timestamp</th><th>Role</th><th>Model</th><th>Judge</th>
      <th>GEval</th><th>DAG</th><th>Combined</th><th>Grade</th>
      <th>Latency</th><th>Cost</th><th>Report</th>
    </tr></thead>
    <tbody>${runs.map(run => `<tr>
      <td>${run.id}</td>
      <td style="white-space:nowrap">${(run.timestamp||'').substring(0,10)} ${(run.timestamp||'').substring(11,16)}</td>
      <td style="max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${run.role}">${run.role}</td>
      <td>${run.model || 'demo'}</td>
      <td>${run.judge_model || '-'}</td>
      <td>${run.overall_pct}%</td>
      <td>${run.dag_pct ? run.dag_pct.toFixed(1) + '%' : '-'}</td>
      <td style="font-weight:700">${run.consolidated_pct ? run.consolidated_pct.toFixed(1) : run.overall_pct}%</td>
      <td><span class="grade-badge grade-${((run.consolidated_grade||run.grade||'d')[0]).toLowerCase()}">${run.consolidated_grade||run.grade}</span></td>
      <td>${run.avg_latency ? run.avg_latency.toFixed(1) + 's' : '-'}</td>
      <td>${run.estimated_cost ? '$' + run.estimated_cost.toFixed(4) : '-'}</td>
      <td>${run.report_path ? '<a href="/reports/' + run.report_path.split(/[/\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
    </tr>`).join('')}</tbody></table>`;
}

function buildComparisonTable(runs) {
  // Comparison tab: pair A/B runs together
  // Group by pairs (consecutive A+B with same timestamp prefix)
  const pairs = [];
  for (let i = 0; i < runs.length; i += 2) {
    const a = runs[i+1]; // A is logged first (lower ID)
    const b = runs[i];   // B is logged second (higher ID)
    if (a && b) pairs.push({a, b});
    else if (a) pairs.push({a, b: null});
  }

  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>Timestamp</th><th>Role</th>
      <th>Run A</th><th>A Score</th><th>A Grade</th>
      <th>Run B</th><th>B Score</th><th>B Grade</th>
      <th>Delta</th><th>Report</th>
    </tr></thead>
    <tbody>${pairs.map(p => {
      const a = p.a || {};
      const b = p.b || {};
      const aScore = a.consolidated_pct || a.overall_pct || 0;
      const bScore = b.consolidated_pct || b.overall_pct || 0;
      const delta = (bScore - aScore).toFixed(1);
      const deltaColor = delta > 0 ? 'var(--green)' : delta < 0 ? 'var(--red)' : 'var(--text2)';
      return `<tr>
        <td style="white-space:nowrap">${(a.timestamp||b.timestamp||'').substring(0,10)} ${(a.timestamp||b.timestamp||'').substring(11,16)}</td>
        <td>${a.role || b.role}</td>
        <td style="font-size:0.75rem">${a.notes || a.model || '-'}</td>
        <td>${aScore}%</td>
        <td><span class="grade-badge grade-${((a.consolidated_grade||a.grade||'d')[0]).toLowerCase()}">${a.consolidated_grade||a.grade||'-'}</span></td>
        <td style="font-size:0.75rem">${b.notes || b.model || '-'}</td>
        <td>${bScore}%</td>
        <td><span class="grade-badge grade-${((b.consolidated_grade||b.grade||'d')[0]).toLowerCase()}">${b.consolidated_grade||b.grade||'-'}</span></td>
        <td style="color:${deltaColor};font-weight:700">${delta > 0 ? '+' : ''}${delta}%</td>
        <td>${(b.report_path||a.report_path) ? '<a href="/reports/' + (b.report_path||a.report_path).split(/[/\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

function buildRedTeamTable(runs) {
  // Red Team tab: security-focused columns
  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>#</th><th>Timestamp</th><th>Role</th><th>Model</th>
      <th>Attacks</th><th>Pass Rate</th><th>Result</th><th>Report</th>
    </tr></thead>
    <tbody>${runs.map(run => {
      const pr = run.overall_pct || 0;
      const resultColor = pr >= 90 ? 'var(--green)' : pr >= 70 ? 'var(--yellow)' : 'var(--red)';
      return `<tr>
        <td>${run.id}</td>
        <td style="white-space:nowrap">${(run.timestamp||'').substring(0,10)} ${(run.timestamp||'').substring(11,16)}</td>
        <td>${run.role}</td>
        <td>${run.model || 'demo'}</td>
        <td>${run.num_tests || '-'}</td>
        <td style="font-weight:700;color:${resultColor}">${pr}%</td>
        <td><span class="grade-badge grade-${pr >= 90 ? 'a' : pr >= 70 ? 'b' : 'd'}">${pr >= 90 ? 'PASS' : pr >= 70 ? 'WARN' : 'FAIL'}</span></td>
        <td>${run.report_path ? '<a href="/reports/' + run.report_path.split(/[/\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

function buildCalibrationTable(runs) {
  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>#</th><th>Timestamp</th><th>Judge Model</th>
      <th>Accuracy</th><th>Discrimination</th><th>Avg Dev</th>
      <th>Excellent</th><th>Adequate</th><th>Poor</th><th>Misleading</th>
      <th>Pass/Fail</th><th>Issues</th><th>Report</th>
    </tr></thead>
    <tbody>${runs.map(run => {
      const accColor = run.accuracy >= 80 ? 'var(--green)' : run.accuracy >= 60 ? 'var(--yellow)' : 'var(--red)';
      const discColor = run.discrimination >= 0.5 ? 'var(--green)' : run.discrimination >= 0.3 ? 'var(--yellow)' : 'var(--red)';
      return `<tr>
        <td>${run.id}</td>
        <td style="white-space:nowrap">${(run.timestamp||'').substring(0,10)} ${(run.timestamp||'').substring(11,16)}</td>
        <td>${run.judge_model || '-'}</td>
        <td style="font-weight:700;color:${accColor}">${run.accuracy}%</td>
        <td style="font-weight:700;color:${discColor}">${run.discrimination}</td>
        <td>${run.avg_deviation}</td>
        <td style="color:var(--green)">${run.avg_excellent}</td>
        <td style="color:var(--yellow)">${run.avg_adequate}</td>
        <td style="color:var(--red)">${run.avg_poor}</td>
        <td style="color:var(--orange)">${run.avg_misleading}</td>
        <td>${run.passed}/${run.total_tests}</td>
        <td style="color:${run.issues_count > 0 ? 'var(--red)' : 'var(--green)'}">${run.issues_count}</td>
        <td>${run.report_path ? '<a href="/reports/' + run.report_path.split(/[/\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

function buildGenEvalTable(runs) {
  // Generate Tests tab: evaluations on generated/manual test cases
  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>#</th><th>Timestamp</th><th>Role</th><th>Model</th>
      <th>Tests</th><th>GEval</th><th>DAG</th><th>Combined</th><th>Grade</th>
      <th>Notes</th><th>Report</th>
    </tr></thead>
    <tbody>${runs.map(run => `<tr>
      <td>${run.id}</td>
      <td style="white-space:nowrap">${(run.timestamp||'').substring(0,10)} ${(run.timestamp||'').substring(11,16)}</td>
      <td>${run.role}</td>
      <td>${run.model || 'demo'}</td>
      <td>${run.num_tests}</td>
      <td>${run.overall_pct}%</td>
      <td>${run.dag_pct ? run.dag_pct.toFixed(1) + '%' : '-'}</td>
      <td style="font-weight:700">${run.consolidated_pct ? run.consolidated_pct.toFixed(1) : run.overall_pct}%</td>
      <td><span class="grade-badge grade-${((run.consolidated_grade||run.grade||'d')[0]).toLowerCase()}">${run.consolidated_grade||run.grade}</span></td>
      <td style="font-size:0.75rem;color:var(--text2)">${run.notes || '-'}</td>
      <td>${run.report_path ? '<a href="/reports/' + run.report_path.split(/[/\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
    </tr>`).join('')}</tbody></table>`;
}

function exportCSV(runType) {
  fetch('/api/history').then(r => r.json()).then(runs => {
    let filtered = runs;
    if (runType) filtered = runs.filter(r => r.run_type && r.run_type.startsWith(runType));

    const headers = ['ID','Timestamp','Role','Model','Judge Model','GEval %','DAG %','Combined %','Grade','Tests','Criteria',
      'Avg Latency (s)','P95 Latency (s)','Total Tokens','Est Cost (USD)','Duration (s)','Type','Notes'];
    const rows = filtered.map(r => [
      r.id, r.timestamp, r.role, r.model||'demo', r.judge_model||'-',
      r.overall_pct, r.dag_pct||'', r.consolidated_pct||r.overall_pct, r.consolidated_grade||r.grade,
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
