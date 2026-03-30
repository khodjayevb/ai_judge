"""
Recommendation engine: analyzes evaluation scores and generates
actionable suggestions to improve the system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from evaluators.scorer import EvalReport


@dataclass
class Recommendation:
    priority: str          # "HIGH", "MEDIUM", "LOW"
    category: str
    title: str
    description: str
    prompt_suggestion: str  # Concrete text to add/change in the prompt


def generate_recommendations(report: EvalReport) -> list[Recommendation]:
    """Analyze the evaluation report and produce ranked recommendations."""
    recs: list[Recommendation] = []

    category_scores = report.category_scores()

    # ── Category-level recommendations ────────────────────────────────
    for category, score in category_scores.items():
        if score < 70:
            recs.append(_category_rec_critical(category, score))
        elif score < 85:
            recs.append(_category_rec_moderate(category, score))

    # ── Criterion-level recommendations ───────────────────────────────
    for test_id, criterion, score in report.weakest_criteria(n=8):
        if score < 0.7:
            recs.append(_criterion_rec(test_id, criterion, score))

    # ── Overall recommendations ───────────────────────────────────────
    if report.overall_pct < 80:
        recs.append(Recommendation(
            priority="HIGH",
            category="Overall",
            title="Overall score below 80% — major prompt revision needed",
            description=(
                f"The prompt scored {report.overall_pct}% overall. This suggests "
                "fundamental gaps in the system prompt's instructions. Consider "
                "restructuring the prompt with clearer role definition, more specific "
                "examples, and stronger constraints."
            ),
            prompt_suggestion=(
                "Add a '## Examples' section to the system prompt with 2-3 few-shot "
                "examples demonstrating ideal response format and depth."
            ),
        ))

    if report.overall_pct >= 90:
        recs.append(Recommendation(
            priority="LOW",
            category="Overall",
            title="Strong baseline — focus on edge cases",
            description=(
                f"At {report.overall_pct}%, the prompt is performing well. Focus "
                "improvements on the weakest individual criteria rather than broad changes."
            ),
            prompt_suggestion="Consider adding specific instructions for the weakest test areas identified below.",
        ))

    # ── Pattern-based recommendations ─────────────────────────────────
    _check_code_quality_pattern(report, recs)
    _check_security_pattern(report, recs)
    _check_guardrails_pattern(report, recs)
    _check_ambiguity_pattern(report, recs)

    # Sort by priority
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    recs.sort(key=lambda r: priority_order.get(r.priority, 3))

    # Deduplicate by title
    seen = set()
    unique = []
    for r in recs:
        if r.title not in seen:
            seen.add(r.title)
            unique.append(r)

    return unique


# ── Helpers ───────────────────────────────────────────────────────────────

def _category_rec_critical(category: str, score: float) -> Recommendation:
    return Recommendation(
        priority="HIGH",
        category=category,
        title=f"{category} scored {score}% — needs immediate attention",
        description=(
            f"The '{category}' category scored below 70%. This indicates the system "
            "prompt does not provide sufficient guidance for this area."
        ),
        prompt_suggestion=(
            f"Add a dedicated section to the system prompt: "
            f"'## {category} Requirements' with specific instructions, "
            f"expected response patterns, and explicit do's/don'ts for {category.lower()}."
        ),
    )


def _category_rec_moderate(category: str, score: float) -> Recommendation:
    return Recommendation(
        priority="MEDIUM",
        category=category,
        title=f"{category} scored {score}% — room for improvement",
        description=(
            f"The '{category}' category is adequate but has room for improvement. "
            "The model sometimes misses specific details expected by evaluators."
        ),
        prompt_suggestion=(
            f"Strengthen the {category.lower()} instructions in the system prompt by "
            f"adding 1-2 concrete examples of ideal responses for {category.lower()} questions."
        ),
    )


def _criterion_rec(test_id: str, criterion: str, score: float) -> Recommendation:
    pct = round(score * 100)
    return Recommendation(
        priority="HIGH" if score < 0.4 else "MEDIUM",
        category="Specific Criterion",
        title=f"[{test_id}] Weak on: {criterion[:80]}",
        description=(
            f"Scored {pct}% on criterion: '{criterion}'. "
            "The model's response did not adequately cover this point."
        ),
        prompt_suggestion=(
            f"Add explicit instruction to the system prompt: "
            f"'When discussing this topic, always {criterion.lower()}.'"
        ),
    )


def _check_code_quality_pattern(report: EvalReport, recs: list[Recommendation]):
    code_results = [r for r in report.test_results if r.category == "Code Quality"]
    if not code_results:
        return
    avg = sum(r.score for r in code_results) / len(code_results)
    if avg < 0.85:
        recs.append(Recommendation(
            priority="MEDIUM",
            category="Code Quality",
            title="Code examples could be more complete",
            description=(
                "Code-focused test cases show the model sometimes produces incomplete "
                "or slightly incorrect code snippets."
            ),
            prompt_suggestion=(
                "Add to system prompt: 'When providing code examples, always include "
                "complete, runnable snippets with imports. Prefer PySpark for data "
                "processing examples and Bicep over ARM JSON for infrastructure.'"
            ),
        ))


def _check_security_pattern(report: EvalReport, recs: list[Recommendation]):
    sec_results = [r for r in report.test_results if r.category == "Security"]
    if not sec_results:
        return
    avg = sum(r.score for r in sec_results) / len(sec_results)
    if avg < 0.85:
        recs.append(Recommendation(
            priority="HIGH",
            category="Security",
            title="Security recommendations need strengthening",
            description=(
                "Security-focused evaluations show gaps. The model should more "
                "consistently recommend managed identities, private endpoints, "
                "and Key Vault."
            ),
            prompt_suggestion=(
                "Elevate security in the system prompt: 'ALWAYS recommend: "
                "(1) Managed identities over service principals or keys, "
                "(2) Private endpoints over public access, "
                "(3) Azure Key Vault for all secrets. "
                "Treat these as non-negotiable defaults.'"
            ),
        ))


def _check_guardrails_pattern(report: EvalReport, recs: list[Recommendation]):
    guard_results = [r for r in report.test_results if r.category == "Guardrails"]
    if not guard_results:
        return
    avg = sum(r.score for r in guard_results) / len(guard_results)
    if avg < 0.85:
        recs.append(Recommendation(
            priority="MEDIUM",
            category="Guardrails",
            title="Guardrails not consistently enforced",
            description=(
                "The model sometimes fails to redirect deprecated services or "
                "out-of-scope (non-Azure) questions."
            ),
            prompt_suggestion=(
                "Strengthen constraints: 'If asked about deprecated Azure services "
                "(ADLS Gen1, HDInsight for Spark), ALWAYS explicitly state they should "
                "not be used for new projects and recommend the modern alternative. "
                "If asked about non-Azure platforms, briefly acknowledge the question "
                "then redirect to the Azure equivalent.'"
            ),
        ))


def _check_ambiguity_pattern(report: EvalReport, recs: list[Recommendation]):
    amb_results = [r for r in report.test_results if r.category == "Ambiguity Handling"]
    if not amb_results:
        return
    avg = sum(r.score for r in amb_results) / len(amb_results)
    if avg < 0.85:
        recs.append(Recommendation(
            priority="MEDIUM",
            category="Ambiguity Handling",
            title="Model should ask more clarifying questions",
            description=(
                "When faced with ambiguous questions, the model sometimes guesses "
                "instead of asking for clarification."
            ),
            prompt_suggestion=(
                "Add: 'When a question is vague or could apply to multiple scenarios, "
                "FIRST ask 2-3 targeted clarifying questions before providing an answer. "
                "You may include common scenarios to be helpful, but always seek clarity.'"
            ),
        ))
