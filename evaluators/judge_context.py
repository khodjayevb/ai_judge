"""
Judge Context — loads reference documents and scoring rubrics to make
the judge model domain-aware and objective.

Reference docs are loaded from docs/{role_slug}/ and injected into every
GEval evaluation call so the judge scores against your actual standards.
"""

from __future__ import annotations

from pathlib import Path

# Cache loaded contexts per role
_context_cache: dict[str, str] = {}


def load_judge_context(role_slug: str) -> str:
    """Load reference documents for the judge from docs/{role_slug}/.

    Returns a combined text block of all .md and .txt files in the role's
    docs folder. This is injected into the GEval criteria prompt so the
    judge scores against your organization's actual standards.
    """
    if role_slug in _context_cache:
        return _context_cache[role_slug]

    docs_dir = Path(f"docs/{role_slug}")
    parts = []

    if docs_dir.exists():
        for f in sorted(docs_dir.glob("*")):
            if f.suffix in (".md", ".txt"):
                content = f.read_text(encoding="utf-8", errors="replace")
                parts.append(f"### {f.name}\n{content}")

    # Also check for role-specific files in docs/ root
    docs_root = Path("docs")
    if docs_root.exists():
        for f in docs_root.glob(f"{role_slug}*"):
            if f.suffix in (".md", ".txt") and f.name not in [p.split("\n")[0] for p in parts]:
                content = f.read_text(encoding="utf-8", errors="replace")
                parts.append(f"### {f.name}\n{content}")

    context = "\n\n".join(parts)
    _context_cache[role_slug] = context
    return context


# ── Scoring Rubric ────────────────────────────────────────────────────

SCORING_RUBRIC = """
SCORING RUBRIC — Use this rubric to assign scores consistently:

Score 1.0 (Excellent):
- Criterion is fully addressed with specific, correct details
- Names exact technologies, standards, versions, or configurations
- Provides actionable guidance (steps, commands, architecture decisions)
- Demonstrates depth beyond surface-level knowledge
- Example: "Use AES-256 with customer-managed keys in FIPS 140-2 Level 2 HSM-backed Key Vault"

Score 0.8 (Good):
- Criterion addressed with mostly specific details
- Correct direction but may miss one specific element
- Provides guidance that a practitioner could act on
- Example: "Use customer-managed keys in Azure Key Vault for encryption at rest"

Score 0.6 (Adequate):
- Criterion mentioned with some relevant detail
- General direction is correct but lacks specificity
- Missing important qualifiers or specific configurations
- Example: "Use Azure Key Vault for key management"

Score 0.4 (Weak):
- Criterion barely addressed or only implied
- Vague statement without specific guidance
- Missing critical details that a practitioner would need
- Example: "Encryption should be used"

Score 0.2 (Poor):
- Criterion mentioned in passing or tangentially
- No useful detail or actionable guidance
- May be misleading or incomplete
- Example: "Security is important"

Score 0.0 (Not Addressed):
- Criterion not mentioned at all in the response
- Or the response contradicts the criterion
"""


def build_judge_prompt(criterion: str, domain: str, role_slug: str = "") -> str:
    """Build a comprehensive judge prompt with context and rubric.

    This replaces the simple "Evaluate whether the response addresses: {criterion}"
    with a detailed prompt that includes:
    1. The scoring rubric (what each score level means)
    2. Reference standards from your organization's documents
    3. The specific criterion to evaluate
    """
    ref_context = load_judge_context(role_slug) if role_slug else ""

    parts = [
        f"You are an expert evaluator for a {domain} AI assistant.",
        "",
        SCORING_RUBRIC,
    ]

    if ref_context:
        parts.extend([
            "",
            "REFERENCE STANDARDS — The response should align with these organizational standards:",
            "---",
            ref_context[:6000],  # Cap to avoid token limits
            "---",
            "",
        ])

    parts.extend([
        f"CRITERION TO EVALUATE: {criterion}",
        "",
        "Score the response on a scale of 0.0 to 1.0 based on how well it addresses this criterion.",
        "Consider the scoring rubric above and the reference standards (if provided).",
        "A response that aligns with the reference standards should score higher than generic advice.",
    ])

    return "\n".join(parts)
