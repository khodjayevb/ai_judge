#!/usr/bin/env python3
"""
Synthetic Test Case Generator — uses DeepEval Synthesizer to generate
test cases from documents, existing prompts, or custom contexts.

Usage:
    python generate_tests.py --role azure_data_architect                    # From role's system prompt
    python generate_tests.py --docs docs/my_standards.pdf docs/guide.md     # From documents
    python generate_tests.py --role azure_data_architect --count 20         # Generate 20 test cases
    python generate_tests.py --role azure_data_architect --output generated/tests.json

The generated test cases are saved as JSON and can be reviewed, edited,
then imported into test_suites/.
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def get_synthesizer_model():
    """Create a model for the Synthesizer from judge config (uses the stronger model)."""
    judge = config.get_judge_config()
    provider = judge["provider"]

    if provider in ("azure", "azure_foundry"):
        from deepeval.models import AzureOpenAIModel
        return AzureOpenAIModel(
            model=judge["model"],
            deployment_name=judge["deployment"],
            api_key=judge["api_key"],
            base_url=judge["base_url"],
            api_version=judge.get("api_version", "2024-08-01-preview"),
            temperature=0.7,
        )
    elif provider == "openai":
        import os
        os.environ["OPENAI_API_KEY"] = judge["api_key"]
        return judge["model"]
    elif provider == "anthropic":
        from deepeval.models import AnthropicModel
        return AnthropicModel(model=judge["model"], api_key=judge["api_key"], temperature=0.7)
    else:
        return judge["model"]


def generate_from_docs(doc_paths: list[str], count: int = 10) -> list[dict]:
    """Generate test cases from document files (.pdf, .md, .txt, .docx)."""
    from deepeval.synthesizer import Synthesizer, ContextConstructionConfig

    console.print(f"[cyan]Generating from {len(doc_paths)} documents...[/]")

    model = get_synthesizer_model()
    synthesizer = Synthesizer(model=model, async_mode=False)

    context_config = ContextConstructionConfig(
        chunk_size=1024,
        chunk_overlap=100,
        max_contexts_per_document=max(count // len(doc_paths), 3),
        context_quality_threshold=0.5,
    )

    goldens = synthesizer.generate_goldens_from_docs(
        document_paths=doc_paths,
        include_expected_output=True,
        max_goldens_per_context=2,
        context_construction_config=context_config,
    )

    return _goldens_to_test_cases(goldens)


def generate_from_prompt(role_slug: str, count: int = 10) -> list[dict]:
    """Generate test cases from a role's system prompt text."""
    from deepeval.synthesizer import Synthesizer
    from prompts.registry import get_prompt

    system_prompt, meta = get_prompt(role_slug)
    domain = meta.get("domain", "General")

    console.print(f"[cyan]Generating {count} test cases for role: {role_slug}[/]")
    console.print(f"[dim]Domain: {domain} | Prompt length: {len(system_prompt)} chars[/]")

    model = get_synthesizer_model()
    synthesizer = Synthesizer(model=model, async_mode=False)

    # Extract key topics from the prompt to create focused contexts
    contexts = _extract_contexts_from_prompt(system_prompt, domain)

    goldens = synthesizer.generate_goldens_from_contexts(
        contexts=contexts,
        include_expected_output=True,
        max_goldens_per_context=max(count // len(contexts), 2),
    )

    return _goldens_to_test_cases(goldens, domain=domain)


def _extract_contexts_from_prompt(prompt: str, domain: str) -> list[list[str]]:
    """Split a system prompt into meaningful contexts for test generation."""
    contexts = []
    current_section = []

    for line in prompt.split("\n"):
        line = line.strip()
        if line.startswith("## ") or line.startswith("- **"):
            if current_section:
                contexts.append(["\n".join(current_section)])
                current_section = []
        if line:
            current_section.append(line)

    if current_section:
        contexts.append(["\n".join(current_section)])

    # Ensure we have at least a few contexts
    if len(contexts) < 3:
        # Split by paragraph
        paragraphs = [p.strip() for p in prompt.split("\n\n") if p.strip()]
        contexts = [[p] for p in paragraphs[:10]]

    return contexts


def _goldens_to_test_cases(goldens, domain: str = "General") -> list[dict]:
    """Convert DeepEval Golden objects to our test case format."""
    test_cases = []
    categories_seen = {}

    for i, golden in enumerate(goldens):
        # Infer category from the question content
        category = _infer_category(golden.input)
        cat_count = categories_seen.get(category, 0) + 1
        categories_seen[category] = cat_count

        # Build a unique ID
        prefix = category[:4].upper().replace(" ", "")
        test_id = f"GEN-{prefix}-{cat_count:02d}"

        tc = {
            "id": test_id,
            "category": category,
            "question": golden.input,
            "criteria": [],
            "weight": 2,
            "_generated": True,
            "_needs_review": True,
        }

        # Generate criteria from expected output
        if golden.expected_output:
            tc["criteria"] = _extract_criteria(golden.expected_output)
            tc["_expected_output"] = golden.expected_output

        # Add context for hallucination detection
        if golden.context:
            tc["context"] = golden.context

        # Ensure we have at least 3 criteria
        while len(tc["criteria"]) < 3:
            tc["criteria"].append(f"[REVIEW NEEDED] Add criterion #{len(tc['criteria'])+1} for this question")

        # Cap at 5 criteria
        tc["criteria"] = tc["criteria"][:5]

        test_cases.append(tc)

    return test_cases


def _infer_category(question: str) -> str:
    """Infer a category from the question text."""
    q = question.lower()
    if any(w in q for w in ["security", "encrypt", "identity", "access control", "zero trust"]):
        return "Security"
    elif any(w in q for w in ["cost", "budget", "pricing", "finops", "spend"]):
        return "Cost Optimization"
    elif any(w in q for w in ["governance", "catalog", "lineage", "purview", "classify"]):
        return "Data Governance"
    elif any(w in q for w in ["migrate", "migration", "modernize", "teradata", "oracle"]):
        return "Migration"
    elif any(w in q for w in ["disaster", "recovery", "backup", "failover", "rpo", "rto"]):
        return "High Availability"
    elif any(w in q for w in ["architect", "design", "platform", "landing zone"]):
        return "Architecture"
    elif any(w in q for w in ["pipeline", "etl", "elt", "ingest", "transform"]):
        return "Data Pipeline"
    elif any(w in q for w in ["monitor", "alert", "log", "observ"]):
        return "Operations"
    elif any(w in q for w in ["fabric", "lakehouse", "onelake"]):
        return "Microsoft Fabric"
    elif any(w in q for w in ["databricks", "spark", "delta"]):
        return "Databricks"
    elif any(w in q for w in ["synapse", "sql pool"]):
        return "Synapse"
    else:
        return "General"


def _extract_criteria(expected_output: str) -> list[str]:
    """Extract evaluation criteria from an expected output."""
    criteria = []
    sentences = expected_output.replace("\n", " ").split(". ")

    for s in sentences:
        s = s.strip()
        if len(s) > 20 and len(s) < 200:
            # Convert statement to criterion
            criterion = f"Mentions or addresses: {s.rstrip('.')}"
            criteria.append(criterion)

    return criteria[:5]


def save_generated_tests(test_cases: list[dict], output_path: str):
    """Save generated test cases as JSON for review."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(test_cases, indent=2), encoding="utf-8")
    return str(out.resolve())


def display_results(test_cases: list[dict]):
    """Display generated test cases in a table."""
    table = Table(title=f"Generated Test Cases ({len(test_cases)})", border_style="cyan")
    table.add_column("ID", style="cyan bold", width=15)
    table.add_column("Category", width=18)
    table.add_column("Question", width=50)
    table.add_column("Criteria", justify="center", width=8)

    for tc in test_cases:
        table.add_row(
            tc["id"],
            tc["category"],
            tc["question"][:80] + ("..." if len(tc["question"]) > 80 else ""),
            str(len(tc["criteria"])),
        )

    console.print(table)
    console.print(f"\n[yellow]Note: Generated tests have _needs_review=True. "
                  f"Review and edit before adding to test_suites/.[/]")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate synthetic test cases")
    parser.add_argument("--role", help="Generate from a role's system prompt")
    parser.add_argument("--docs", nargs="+", help="Generate from document files (.pdf, .md, .txt, .docx)")
    parser.add_argument("--count", type=int, default=10, help="Number of test cases to generate (default: 10)")
    parser.add_argument("--output", default=None, help="Output JSON path (default: generated/{role}_tests.json)")
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.role and not args.docs:
        console.print("[red]Specify --role or --docs[/]")
        console.print("  python generate_tests.py --role azure_data_architect")
        console.print("  python generate_tests.py --docs docs/standards.pdf --count 20")
        return

    console.print(Panel.fit(
        "[bold cyan]Synthetic Test Case Generator[/]\n"
        f"[dim]Model: {config.get_judge_config()['model']} | Count: {args.count}[/]",
        border_style="cyan",
    ))

    if args.docs:
        test_cases = generate_from_docs(args.docs, count=args.count)
    else:
        test_cases = generate_from_prompt(args.role, count=args.count)

    display_results(test_cases)

    # Save
    output = args.output or f"generated/{args.role or 'docs'}_tests.json"
    path = save_generated_tests(test_cases, output)
    console.print(f"\n[bold green]Saved to:[/] {path}")
    console.print(f"[dim]Review, edit criteria, then import into test_suites/[/]")


if __name__ == "__main__":
    main()
