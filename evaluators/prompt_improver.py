"""
Prompt Auto-Improver — analyzes evaluation results and generates
an improved system prompt addressing the weak areas.

Flow:
1. Takes evaluation report with scores and recommendations
2. Identifies weak criteria (< 0.7 GEval or failed DAG dimensions)
3. Generates a targeted improvement to the system prompt
4. Returns the improved prompt for immediate A/B comparison
"""

from __future__ import annotations

import config
from evaluators.llm_client import _create_client


IMPROVEMENT_PROMPT = """You are a system prompt engineer. Your job is to improve an AI assistant's system prompt based on evaluation results.

## Current System Prompt
{current_prompt}

## Evaluation Results
Overall Score: {overall_score}%
Grade: {grade}

## Weak Areas (criteria that scored below 70%)
{weak_areas}

## Recommendations
{recommendations}

## Your Task
Generate an IMPROVED version of the system prompt that addresses the weak areas.

Rules:
1. Keep everything that's working well — don't remove existing good instructions
2. ADD specific instructions to address each weak area
3. Add examples or response patterns for criteria that scored poorly
4. Strengthen guardrails if guardrail tests scored low
5. Add "always ask clarifying questions" if ambiguity handling scored low
6. Be specific — "always mention X" is better than "be more thorough"
7. Keep the same overall structure and persona

Return ONLY the improved system prompt text. No explanation, no markdown fences, no commentary.
"""


def generate_improved_prompt(
    current_prompt: str,
    report,
    recommendations: list,
) -> dict:
    """Generate an improved system prompt based on evaluation results.

    Returns {
        improved_prompt: str,
        changes_summary: str,
        weak_areas_addressed: list[str],
    }
    """
    # Build weak areas text
    weak_areas = []
    for r in report.test_results:
        for c in r.criteria_results:
            if c.score < 0.7:
                dag_info = ""
                if c.dag_dimensions:
                    failed_dims = [d for d, v in c.dag_dimensions.items() if not v["passed"]]
                    if failed_dims:
                        dag_info = f" (Failed DAG dimensions: {', '.join(failed_dims)})"
                weak_areas.append(
                    f"- [{r.test_id}] {c.text} — GEval: {c.score:.0%}{dag_info}"
                )

    if not weak_areas:
        weak_areas = ["No criteria scored below 70% — prompt is performing well."]

    # Build recommendations text
    rec_texts = []
    for rec in recommendations[:8]:
        rec_texts.append(f"- [{rec.priority}] {rec.title}: {rec.prompt_suggestion}")

    # Generate improved prompt using the judge model (stronger model)
    judge_cfg = config.get_judge_config()
    client_fn = _create_client(judge_cfg)

    prompt = IMPROVEMENT_PROMPT.format(
        current_prompt=current_prompt[:6000],
        overall_score=report.overall_pct,
        grade=report.grade,
        weak_areas="\n".join(weak_areas),
        recommendations="\n".join(rec_texts) if rec_texts else "No specific recommendations.",
    )

    text, metrics = client_fn(
        "You are a system prompt engineer. Return only the improved prompt text.",
        prompt,
        temperature=0.4,
    )

    # Generate a summary of changes
    summary_prompt = f"""Compare these two system prompts and list the key changes in 3-5 bullet points.

ORIGINAL (first 2000 chars):
{current_prompt[:2000]}

IMPROVED (first 2000 chars):
{text[:2000]}

Return only bullet points, no introduction."""

    summary_text, _ = client_fn(
        "You are a technical writer. Be concise.",
        summary_prompt,
        temperature=0.2,
    )

    return {
        "improved_prompt": text,
        "changes_summary": summary_text,
        "weak_areas_addressed": [w.split("] ")[1].split(" —")[0] if "] " in w else w for w in weak_areas if w.startswith("-")],
        "original_score": report.overall_pct,
        "original_grade": report.grade,
        "generation_tokens": metrics.output_tokens,
    }
