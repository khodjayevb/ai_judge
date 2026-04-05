"""
Judge Calibration — validates judge accuracy against a gold standard set
of pre-scored responses where the correct score is known.

Run: python -m evaluators.judge_calibration
Dashboard: Judge Calibration tab
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import config
from evaluators.deepeval_adapter import create_judge_model, evaluate_criteria


@dataclass
class CalibrationResult:
    test_id: str
    criterion: str
    expected_score: float
    actual_geval: float
    actual_dag: float | None
    deviation: float  # |expected - actual_geval|
    passed: bool  # deviation <= tolerance
    response_quality: str  # "excellent", "adequate", "poor"


# ══════════════════════════════════════════════════════════════════════════
# GOLD STANDARD VALIDATION SET
# ══════════════════════════════════════════════════════════════════════════
# Each entry has a known-quality response with a human-assigned expected score.
# The judge should produce a score close to the expected score.

GOLD_STANDARD = [
    # ── Excellent responses (expected ~0.9-1.0) ──────────────────────
    {
        "id": "GOLD-01",
        "quality": "excellent",
        "domain": "Power BI Engineering",
        "question": "How do I implement Row-Level Security in Power BI?",
        "response": (
            "## Row-Level Security in Power BI\n\n"
            "### Static RLS\n"
            "Create a role in Power BI Desktop → Modeling → Manage Roles. "
            "Add a DAX filter expression:\n"
            "```\n[Region] = \"North America\"\n```\n\n"
            "### Dynamic RLS (Recommended)\n"
            "1. Create a security table mapping UserEmail to allowed values\n"
            "2. Relate security table to your model\n"
            "3. DAX filter: `[UserEmail] = USERPRINCIPALNAME()`\n"
            "4. All users share ONE role — permissions driven by data\n\n"
            "### Testing\n"
            "- Desktop: Modeling → View as Roles\n"
            "- Service: Dataset → Security → Test as Role\n\n"
            "### Key Considerations\n"
            "- RLS works on Import and DirectQuery models\n"
            "- Workspace admins/members bypass RLS — assign Viewer role\n"
            "- For OLS (Object-Level Security), use Tabular Editor to hide columns from roles"
        ),
        "criteria": [
            "Describes both static RLS and dynamic RLS approaches",
            "Recommends dynamic RLS using USERPRINCIPALNAME()",
            "Explains how to test RLS in Desktop and Service",
        ],
        "expected_scores": [0.95, 0.95, 0.90],
    },
    {
        "id": "GOLD-02",
        "quality": "excellent",
        "domain": "Azure Data Architecture",
        "question": "How should we secure our Azure data lake with PII data?",
        "response": (
            "## Zero Trust Security for Data Lake\n\n"
            "### Network\n"
            "- Private endpoints for ADLS Gen2 — disable public access\n"
            "- NSG rules on all subnets\n"
            "- Azure Policy to enforce: no public endpoints allowed\n\n"
            "### Identity\n"
            "- Managed identities for all service-to-service auth\n"
            "- Entra ID + MFA + Conditional Access for users\n"
            "- PIM for admin roles with 4-hour max activation\n\n"
            "### Encryption\n"
            "- AES-256 at rest with customer-managed keys in FIPS 140-2 Level 2 Key Vault\n"
            "- TLS 1.2+ in transit, legacy TLS disabled\n\n"
            "### Data Protection\n"
            "- Dynamic data masking for PII columns\n"
            "- Sensitivity labels via Purview\n"
            "- RBAC: Storage Blob Data Reader/Contributor per team"
        ),
        "criteria": [
            "Recommends private endpoints with public access disabled",
            "Specifies managed identities for service authentication",
            "Requires AES-256 encryption with customer-managed keys",
        ],
        "expected_scores": [0.95, 0.95, 0.95],
    },

    # ── Adequate responses (expected ~0.5-0.7) ───────────────────────
    {
        "id": "GOLD-03",
        "quality": "adequate",
        "domain": "Power BI Engineering",
        "question": "How do I implement Row-Level Security in Power BI?",
        "response": (
            "You can set up RLS in Power BI by creating roles in the Modeling tab. "
            "Define filter expressions for each role to restrict data access. "
            "You can use DAX filters like [Region] = 'East' to limit what users see. "
            "Make sure to test it before publishing."
        ),
        "criteria": [
            "Describes both static RLS and dynamic RLS approaches",
            "Recommends dynamic RLS using USERPRINCIPALNAME()",
            "Explains how to test RLS in Desktop and Service",
        ],
        "expected_scores": [0.40, 0.10, 0.30],
    },
    {
        "id": "GOLD-04",
        "quality": "adequate",
        "domain": "Azure Data Architecture",
        "question": "How should we secure our Azure data lake with PII data?",
        "response": (
            "For securing your data lake, you should use role-based access control "
            "to manage who can access the data. Enable encryption on the storage account. "
            "Make sure to use proper authentication for users accessing the data."
        ),
        "criteria": [
            "Recommends private endpoints with public access disabled",
            "Specifies managed identities for service authentication",
            "Requires AES-256 encryption with customer-managed keys",
        ],
        "expected_scores": [0.05, 0.10, 0.30],
    },

    # ── Poor responses (expected ~0.0-0.2) ────────────────────────────
    {
        "id": "GOLD-05",
        "quality": "poor",
        "domain": "Power BI Engineering",
        "question": "How do I implement Row-Level Security in Power BI?",
        "response": (
            "Security is important in Power BI. You should make sure "
            "that your data is protected and only authorized users can see it."
        ),
        "criteria": [
            "Describes both static RLS and dynamic RLS approaches",
            "Recommends dynamic RLS using USERPRINCIPALNAME()",
            "Explains how to test RLS in Desktop and Service",
        ],
        "expected_scores": [0.00, 0.00, 0.00],
    },
    {
        "id": "GOLD-06",
        "quality": "poor",
        "domain": "Azure Data Architecture",
        "question": "How should we secure our Azure data lake with PII data?",
        "response": "Use Azure for your data lake. It has good security features.",
        "criteria": [
            "Recommends private endpoints with public access disabled",
            "Specifies managed identities for service authentication",
            "Requires AES-256 encryption with customer-managed keys",
        ],
        "expected_scores": [0.00, 0.00, 0.00],
    },

    # ── Tricky: Good but wrong (expected low — tests judge accuracy) ──
    {
        "id": "GOLD-07",
        "quality": "misleading",
        "domain": "Azure Data Architecture",
        "question": "Should we use ADLS Gen1 for our new data platform?",
        "response": (
            "Yes, ADLS Gen1 is a great choice for your data platform. "
            "It provides a scalable data lake with good integration with "
            "Azure analytics services. Set it up with your Hadoop workloads "
            "and use HDInsight for processing."
        ),
        "criteria": [
            "Advises against ADLS Gen1 as it is deprecated / end-of-life",
            "Recommends ADLS Gen2 as the modern replacement",
        ],
        "expected_scores": [0.00, 0.00],
    },
    {
        "id": "GOLD-08",
        "quality": "misleading",
        "domain": "Power BI Engineering",
        "question": "Should I use calculated columns for all my KPIs?",
        "response": (
            "Yes, calculated columns are the best approach for KPIs. "
            "Create a calculated column for each metric — Total Sales, "
            "Average Revenue, Growth Rate. This makes them always available "
            "and easy to use in any visual."
        ),
        "criteria": [
            "Recommends measures over calculated columns for aggregations",
            "Explains that calculated columns are evaluated at refresh time and increase model size",
        ],
        "expected_scores": [0.00, 0.00],
    },
]


def run_calibration(role_slug: str = "", on_progress=None) -> dict:
    """Run judge calibration against the gold standard set.

    Returns {
        overall_accuracy: float (0-1),
        avg_deviation: float,
        results: list[CalibrationResult],
        discrimination: float (how well judge separates good from bad),
        consistency_issues: list[str],
    }
    """
    judge_model = create_judge_model()
    results = []
    total = sum(len(g["criteria"]) for g in GOLD_STANDARD)
    progress = 0

    for gold in GOLD_STANDARD:
        domain = gold.get("domain", role_slug or "General")

        eval_results = evaluate_criteria(
            question=gold["question"],
            response=gold["response"],
            criteria=gold["criteria"],
            domain=domain,
            judge_model=judge_model,
            role_slug=role_slug,
        )

        for i, criterion in enumerate(gold["criteria"]):
            expected = gold["expected_scores"][i]
            actual_geval = eval_results[i]["score"] if i < len(eval_results) else 0.0
            actual_dag = eval_results[i].get("dag_score") if i < len(eval_results) else None
            deviation = abs(expected - actual_geval)

            results.append(CalibrationResult(
                test_id=gold["id"],
                criterion=criterion,
                expected_score=expected,
                actual_geval=actual_geval,
                actual_dag=actual_dag,
                deviation=deviation,
                passed=deviation <= 0.25,  # Within 0.25 of expected
                response_quality=gold["quality"],
            ))
            progress += 1
            if on_progress:
                on_progress(progress, total, f"{gold['id']}: {criterion[:40]}")

    # Calculate metrics
    deviations = [r.deviation for r in results]
    avg_deviation = round(sum(deviations) / len(deviations), 3) if deviations else 0
    accuracy = round(sum(1 for r in results if r.passed) / len(results) * 100, 1) if results else 0

    # Discrimination: difference between avg score for excellent vs poor
    excellent_scores = [r.actual_geval for r in results if r.response_quality == "excellent"]
    poor_scores = [r.actual_geval for r in results if r.response_quality == "poor"]
    discrimination = 0.0
    if excellent_scores and poor_scores:
        avg_excellent = sum(excellent_scores) / len(excellent_scores)
        avg_poor = sum(poor_scores) / len(poor_scores)
        discrimination = round(avg_excellent - avg_poor, 2)

    # Consistency issues
    issues = []
    for r in results:
        if r.response_quality == "excellent" and r.actual_geval < 0.5:
            issues.append(f"{r.test_id}: Excellent response scored only {r.actual_geval:.0%} on '{r.criterion[:50]}'")
        if r.response_quality == "poor" and r.actual_geval > 0.5:
            issues.append(f"{r.test_id}: Poor response scored {r.actual_geval:.0%} on '{r.criterion[:50]}'")
        if r.response_quality == "misleading" and r.actual_geval > 0.3:
            issues.append(f"{r.test_id}: Misleading response scored {r.actual_geval:.0%} on '{r.criterion[:50]}'")

    return {
        "overall_accuracy": accuracy,
        "avg_deviation": avg_deviation,
        "discrimination": discrimination,
        "total_tests": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "results": [
            {
                "test_id": r.test_id,
                "quality": r.response_quality,
                "criterion": r.criterion,
                "expected": r.expected_score,
                "geval": r.actual_geval,
                "dag": r.actual_dag,
                "deviation": r.deviation,
                "passed": r.passed,
            }
            for r in results
        ],
        "consistency_issues": issues,
        "by_quality": {
            "excellent": {"avg_geval": round(sum(excellent_scores) / len(excellent_scores), 2) if excellent_scores else 0},
            "adequate": {"avg_geval": round(sum(r.actual_geval for r in results if r.response_quality == "adequate") / max(len([r for r in results if r.response_quality == "adequate"]), 1), 2)},
            "poor": {"avg_geval": round(sum(poor_scores) / len(poor_scores), 2) if poor_scores else 0},
            "misleading": {"avg_geval": round(sum(r.actual_geval for r in results if r.response_quality == "misleading") / max(len([r for r in results if r.response_quality == "misleading"]), 1), 2)},
        },
    }


def generate_calibration_report(result: dict, judge_model: str = "", output_path: str = "") -> str:
    """Generate an HTML report for a calibration run."""
    import html as html_mod
    from datetime import datetime
    from pathlib import Path

    if not output_path:
        output_path = f"reports/calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

    acc = result.get("overall_accuracy", 0)
    disc = result.get("discrimination", 0)
    dev = result.get("avg_deviation", 0)
    bq = result.get("by_quality", {})
    issues = result.get("consistency_issues", [])
    tests = result.get("results", [])

    acc_color = "#22c55e" if acc >= 80 else "#eab308" if acc >= 60 else "#ef4444"
    disc_color = "#22c55e" if disc >= 0.5 else "#eab308" if disc >= 0.3 else "#ef4444"

    # Build test rows
    test_rows = ""
    for t in tests:
        dev_color = "#22c55e" if t["passed"] else "#ef4444"
        qual_colors = {"excellent": "#22c55e", "adequate": "#eab308", "poor": "#ef4444", "misleading": "#f97316"}
        qc = qual_colors.get(t["quality"], "#94a3b8")
        test_rows += f"""<tr>
            <td style="font-family:monospace;color:#38bdf8">{t['test_id']}</td>
            <td><span style="background:{qc};color:#000;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.75rem">{t['quality']}</span></td>
            <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{html_mod.escape(t['criterion'])}">{html_mod.escape(t['criterion'])}</td>
            <td style="text-align:center">{t['expected']:.2f}</td>
            <td style="text-align:center;font-weight:700">{t['geval']:.2f}</td>
            <td style="text-align:center">{t['dag']:.2f if t['dag'] is not None else '-'}</td>
            <td style="text-align:center;color:{dev_color};font-weight:600">{t['deviation']:.2f}</td>
            <td style="text-align:center">{'<span style="color:#22c55e">PASS</span>' if t['passed'] else '<span style="color:#ef4444">FAIL</span>'}</td>
        </tr>"""

    issues_html = ""
    if issues:
        issues_html = '<h2 style="color:#ef4444;margin-top:2rem">Consistency Issues</h2>'
        for iss in issues:
            issues_html += f'<div style="background:#1e293b;padding:0.75rem;border-radius:8px;margin-bottom:0.5rem;border-left:3px solid #ef4444;font-size:0.85rem">{html_mod.escape(iss)}</div>'

    report_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Judge Calibration Report</title>
<style>
  * {{ margin:0;padding:0;box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;line-height:1.6; }}
  .container {{ max-width:1000px;margin:0 auto;padding:2rem; }}
  h1 {{ font-size:1.8rem;text-align:center;margin-bottom:0.25rem; }}
  h2 {{ font-size:1.2rem;margin:1.5rem 0 0.75rem;color:#38bdf8;border-bottom:2px solid #334155;padding-bottom:0.3rem; }}
  .subtitle {{ text-align:center;color:#94a3b8;margin-bottom:2rem; }}
  .metrics {{ display:flex;gap:2rem;justify-content:center;flex-wrap:wrap;margin:2rem 0; }}
  .metric {{ text-align:center;background:#1e293b;border-radius:12px;padding:1.25rem 2rem;min-width:150px; }}
  .metric .val {{ font-size:2.2rem;font-weight:800; }}
  .metric .lbl {{ color:#94a3b8;font-size:0.85rem; }}
  .metric .hint {{ color:#64748b;font-size:0.7rem;margin-top:0.2rem; }}
  table {{ width:100%;border-collapse:collapse;background:#1e293b;border-radius:12px;overflow:hidden;margin-top:1rem; }}
  th {{ background:#334155;padding:0.6rem 0.75rem;text-align:left;font-size:0.75rem;color:#94a3b8;text-transform:uppercase; }}
  td {{ padding:0.5rem 0.75rem;border-bottom:1px solid #334155;font-size:0.85rem; }}
  .footer {{ text-align:center;color:#94a3b8;font-size:0.8rem;margin-top:3rem;padding-top:1rem;border-top:1px solid #334155; }}
</style></head>
<body><div class="container">
  <h1>Judge Calibration Report</h1>
  <p class="subtitle">{html_mod.escape(judge_model)} | {datetime.now().strftime('%Y-%m-%d %H:%M')} | {result.get('total_tests', 0)} gold standard tests</p>

  <div class="metrics">
    <div class="metric">
      <div class="val" style="color:{acc_color}">{acc}%</div>
      <div class="lbl">Accuracy</div>
      <div class="hint">{result.get('passed',0)}/{result.get('total_tests',0)} within tolerance</div>
    </div>
    <div class="metric">
      <div class="val" style="color:{disc_color}">{disc}</div>
      <div class="lbl">Discrimination</div>
      <div class="hint">Gap between excellent & poor</div>
    </div>
    <div class="metric">
      <div class="val">{dev}</div>
      <div class="lbl">Avg Deviation</div>
      <div class="hint">From expected scores</div>
    </div>
  </div>

  <h2>Scores by Quality Tier</h2>
  <div class="metrics">
    <div class="metric"><div class="val" style="color:#22c55e">{bq.get('excellent',{{}}).get('avg_geval',0)}</div><div class="lbl">Excellent</div><div class="hint">Should be high (~0.9)</div></div>
    <div class="metric"><div class="val" style="color:#eab308">{bq.get('adequate',{{}}).get('avg_geval',0)}</div><div class="lbl">Adequate</div><div class="hint">Should be medium (~0.3)</div></div>
    <div class="metric"><div class="val" style="color:#ef4444">{bq.get('poor',{{}}).get('avg_geval',0)}</div><div class="lbl">Poor</div><div class="hint">Should be low (~0.0)</div></div>
    <div class="metric"><div class="val" style="color:#f97316">{bq.get('misleading',{{}}).get('avg_geval',0)}</div><div class="lbl">Misleading</div><div class="hint">Should be zero (trap test)</div></div>
  </div>

  {issues_html}

  <h2>Detailed Results</h2>
  <table>
    <thead><tr><th>ID</th><th>Quality</th><th>Criterion</th><th>Expected</th><th>GEval</th><th>DAG</th><th>Deviation</th><th>Result</th></tr></thead>
    <tbody>{test_rows}</tbody>
  </table>

  <div class="footer">Generated by AI Evaluation Framework — Judge Calibration | {datetime.now().strftime('%Y')}</div>
</div></body></html>"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report_html, encoding="utf-8")
    return str(out.resolve())
