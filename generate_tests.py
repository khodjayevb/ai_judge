#!/usr/bin/env python3
"""
Fast Test Case Generator — uses a single LLM call to generate test cases
from a role's system prompt or document text.

Usage:
    python generate_tests.py --role azure_data_architect
    python generate_tests.py --role azure_data_architect --count 15
    python generate_tests.py --docs docs/standards.md --count 10
"""

import sys
import os
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

GENERATION_PROMPT = """You are a test case generator for AI assistant evaluation.

Given the following source material, generate {count} diverse test cases to evaluate
whether an AI assistant has genuine domain expertise — not just the ability to
repeat instructions.

Each test case must have:
- "id": unique ID like "GEN-SEC-01" (use category abbreviation)
- "category": one of the categories you identify from the content
- "question": a realistic user question that a practitioner would actually ask
- "criteria": exactly 5 specific, measurable evaluation criteria (what a correct answer MUST include)
- "weight": 1 (nice-to-have), 2 (important), or 3 (critical)
- "context": 1-3 ground truth statements from the source material (for hallucination detection)

Requirements for QUESTIONS:
- Ask practical "how do I", "what's the best approach", "design a solution" questions
- Include scenario-based questions with real constraints (team size, budget, compliance, scale)
- Include at least one question that asks about trade-offs between approaches
- Include at least one guardrail test (asking something clearly outside scope)
- Include at least one ambiguity test (vague question that should trigger clarification)
- Do NOT ask "what does the document say" — ask questions a real practitioner would ask

Requirements for CRITERIA:
- Must be specific and verifiable ("recommends private endpoints" not "mentions security")
- Should test for depth, not just keyword matching
- At least one criterion per test should check for trade-off awareness or nuance
- Reference specific technologies, standards, or best practices from the source

Requirements for CONTEXT (ground truth):
- Extract specific facts, numbers, standards, or best practices from the source
- These are used for hallucination detection — the model's answer must not contradict them

Return ONLY valid JSON array. No markdown fences, no explanation.

SOURCE MATERIAL:
{source}
"""


def generate_test_cases(source_text: str, count: int = 10) -> list[dict]:
    """Generate test cases using a single LLM call."""
    from evaluators.llm_client import _create_client

    # Use judge model (stronger) for generation
    judge_cfg = config.get_judge_config()
    client_fn = _create_client(judge_cfg)

    prompt = GENERATION_PROMPT.format(count=count, source=source_text[:8000])

    console.print(f"[cyan]Generating {count} test cases...[/]")
    text, metrics = client_fn(
        "You are a test case generator. Return only valid JSON.",
        prompt,
        temperature=0.7,
    )

    console.print(f"[dim]Response: {metrics.output_tokens} tokens in {metrics.latency_seconds:.1f}s[/]")

    # Parse JSON from response
    try:
        # Strip markdown fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        test_cases = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON array in response
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            test_cases = json.loads(text[start:end])
        else:
            raise ValueError(f"Could not parse JSON from response: {text[:200]}")

    # Validate and normalize
    for tc in test_cases:
        tc["_generated"] = True
        tc["_needs_review"] = True
        if "criteria" not in tc:
            tc["criteria"] = ["[REVIEW NEEDED] Add criteria"]
        if "weight" not in tc:
            tc["weight"] = 2
        if "context" in tc and isinstance(tc["context"], str):
            tc["context"] = [tc["context"]]

    return test_cases


def generate_from_role(role_slug: str, count: int = 10, doc_paths: list[str] = None) -> list[dict]:
    """Generate from reference documents + role context.

    If doc_paths provided, uses those as primary source.
    Otherwise, looks for docs/{role_slug}/ folder or falls back to system prompt.
    """
    from prompts.registry import get_prompt
    system_prompt, meta = get_prompt(role_slug)
    console.print(f"[bold]Role:[/] {meta['name']} | [bold]Domain:[/] {meta['domain']}")

    source_parts = []

    # 1. Look for reference docs
    if doc_paths:
        for p in doc_paths:
            path = Path(p)
            if path.exists():
                source_parts.append(f"--- {path.name} ---\n{path.read_text(encoding='utf-8', errors='replace')}")
                console.print(f"[dim]Loaded doc: {path.name}[/]")
    else:
        # Auto-discover docs/{role_slug}/ folder
        docs_dir = Path(f"docs/{role_slug}")
        if docs_dir.exists():
            for f in sorted(docs_dir.glob("*")):
                if f.suffix in (".md", ".txt", ".pdf", ".docx"):
                    source_parts.append(f"--- {f.name} ---\n{f.read_text(encoding='utf-8', errors='replace')}")
                    console.print(f"[dim]Loaded doc: {f.name}[/]")

        # Also check docs/ root for any matching files
        docs_root = Path("docs")
        if docs_root.exists():
            for f in docs_root.glob(f"{role_slug}*"):
                if f.suffix in (".md", ".txt") and f.name not in [p.split("---")[0].strip() for p in source_parts]:
                    source_parts.append(f"--- {f.name} ---\n{f.read_text(encoding='utf-8', errors='replace')}")
                    console.print(f"[dim]Loaded doc: {f.name}[/]")

    # 2. Add system prompt as context (not primary source)
    if source_parts:
        source = "\n\n".join(source_parts)
        source += f"\n\n--- SYSTEM PROMPT (for context on expected behavior) ---\n{system_prompt}"
        console.print(f"[green]Using {len(source_parts)} reference document(s) as primary source[/]")
    else:
        source = system_prompt
        console.print(f"[yellow]No reference docs found. Using system prompt only.[/]")
        console.print(f"[dim]Tip: Add docs to docs/{role_slug}/ for better test generation[/]")

    return generate_test_cases(source, count)


def generate_from_docs(doc_paths: list[str], count: int = 10) -> list[dict]:
    """Generate from document files."""
    combined = ""
    for path in doc_paths:
        p = Path(path)
        if not p.exists():
            console.print(f"[red]File not found: {path}[/]")
            continue
        content = p.read_text(encoding="utf-8", errors="replace")
        combined += f"\n\n--- {p.name} ---\n{content}"
        console.print(f"[dim]Loaded: {p.name} ({len(content)} chars)[/]")
    return generate_test_cases(combined, count)


def save_tests(test_cases: list[dict], output_path: str) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(test_cases, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out.resolve())


def display_results(test_cases: list[dict]):
    table = Table(title=f"Generated Test Cases ({len(test_cases)})", border_style="cyan")
    table.add_column("ID", style="cyan bold", width=15)
    table.add_column("Category", width=18)
    table.add_column("Question", width=55)
    table.add_column("Criteria", justify="center", width=8)
    table.add_column("Weight", justify="center", width=6)

    for tc in test_cases:
        table.add_row(
            tc.get("id", "?"),
            tc.get("category", "?"),
            tc.get("question", "?")[:80],
            str(len(tc.get("criteria", []))),
            str(tc.get("weight", 2)),
        )
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Generate test cases")
    parser.add_argument("--role", help="Generate from role's system prompt")
    parser.add_argument("--docs", nargs="+", help="Generate from document files")
    parser.add_argument("--count", type=int, default=10, help="Number of test cases (default: 10)")
    parser.add_argument("--output", help="Output JSON path")
    args = parser.parse_args()

    if not args.role and not args.docs:
        console.print("[red]Specify --role or --docs[/]")
        return

    console.print(Panel.fit(
        f"[bold cyan]Test Case Generator[/]\n"
        f"[dim]Judge model: {config.get_judge_config()['model']}[/]",
        border_style="cyan",
    ))

    if args.docs:
        test_cases = generate_from_docs(args.docs, args.count)
    else:
        test_cases = generate_from_role(args.role, args.count)

    display_results(test_cases)

    output = args.output or f"generated/{args.role or 'docs'}_tests.json"
    path = save_tests(test_cases, output)
    console.print(f"\n[bold green]Saved to:[/] {path}")
    console.print("[dim]Review and edit before adding to test_suites/[/]")


if __name__ == "__main__":
    main()
