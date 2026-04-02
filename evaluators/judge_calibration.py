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
