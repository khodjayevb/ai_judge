#!/usr/bin/env python3
"""
A/B Comparison: Evaluate V1 (weak) and V2 (improved) prompts side-by-side.

Usage:
    python run_comparison.py                                   # Demo, default role
    python run_comparison.py --role fabric_data_engineer        # Specific role
    EVAL_MODE=foundry python run_comparison.py --role power_bi_engineer
"""

import sys
import argparse
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

import config
from prompts.registry import get_prompt, get_test_suite, get_weak_variant, list_roles, role_info
from evaluators.scorer import run_evaluation
from evaluators.recommender import generate_recommendations
from reports.comparison_report import generate_comparison_report

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description="A/B Prompt Comparison")
    parser.add_argument("--role", default=None, help="Role slug to compare")
    parser.add_argument("--list-roles", action="store_true", help="List roles with A/B variants")
    parser.add_argument("--mode", default=None, help="Override EVAL_MODE")
    return parser.parse_args()


def run_with_progress(label: str, system_prompt: str, meta: dict, role_slug: str):
    test_cases = get_test_suite(role_slug)
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"{label}...", total=len(test_cases))

        def on_progress(current, total, test_id):
            progress.update(task, completed=current, description=f"{label} [cyan]{test_id}[/]")

        return run_evaluation(
            system_prompt=system_prompt,
            test_cases=test_cases,
            prompt_name=meta["name"],
            prompt_version=meta["version"],
            domain=meta["domain"],
            role_slug=role_slug,
            on_progress=on_progress,
        )


def main():
    args = parse_args()

    if args.mode:
        config.MODE = args.mode

    if args.list_roles:
        for slug in list_roles():
            info = role_info(slug)
            ab = "A/B ready" if info["has_weak_variant"] else "no weak variant"
            console.print(f"  [cyan]{slug:<30}[/] {info['name']} ({ab})")
        return

    role = args.role or config.EVAL_ROLE
    weak_slug = get_weak_variant(role)
    if not weak_slug:
        console.print(f"[red]No weak variant found for '{role}'.[/]")
        console.print(f"[dim]Create prompts/{role}_v1_weak.py to enable A/B comparison.[/]")
        return

    PROMPT_V1, META_V1 = get_prompt(weak_slug)
    PROMPT_V2, META_V2 = get_prompt(role)

    console.print(Panel.fit(
        f"[bold cyan]System Prompt A/B Comparison[/]\n"
        f"[dim]Mode: {config.MODE} | Role: {role} | "
        f"V1: {META_V1['version']} vs V2: {META_V2['version']}[/]",
        border_style="cyan",
    ))

    if config.MODE == "demo":
        console.print("[yellow]Running in demo mode (no API key needed).[/]\n")

    # Run V1
    console.print("[bold red]--- Phase 1: Evaluating V1 (Baseline) ---[/]\n")
    report_v1 = run_with_progress("V1", PROMPT_V1, META_V1, role)

    # Run V2
    console.print("\n[bold green]--- Phase 2: Evaluating V2 (Improved) ---[/]\n")
    report_v2 = run_with_progress("V2", PROMPT_V2, META_V2, role)

    # Summary table
    console.print()
    table = Table(title="Comparison Results", border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("V1 Baseline", justify="center")
    table.add_column("V2 Improved", justify="center")
    table.add_column("Delta", justify="center")

    delta = report_v2.overall_pct - report_v1.overall_pct
    d_style = "green" if delta > 0 else "red"
    table.add_row("Overall Score", f"{report_v1.overall_pct}%", f"{report_v2.overall_pct}%",
                   f"[{d_style}]{delta:+.1f}%[/]")
    table.add_row("Grade", report_v1.grade, report_v2.grade,
                   f"[{d_style}]{report_v1.grade} -> {report_v2.grade}[/]")

    cat_v1, cat_v2 = report_v1.category_scores(), report_v2.category_scores()
    for cat in sorted(set(list(cat_v1.keys()) + list(cat_v2.keys()))):
        s1, s2 = cat_v1.get(cat, 0), cat_v2.get(cat, 0)
        cd = s2 - s1
        cd_style = "green" if cd > 0 else "red" if cd < 0 else "dim"
        table.add_row(cat, f"{s1}%", f"{s2}%", f"[{cd_style}]{cd:+.1f}%[/]")

    console.print(table)

    recommendations = generate_recommendations(report_v2)

    report_path = generate_comparison_report(
        report_v1, report_v2, recommendations,
        output_path=f"reports/comparison_report_{role}.html",
        system_prompt_v1=PROMPT_V1,
        system_prompt_v2=PROMPT_V2,
        model_name=config.get_model_display_name(),
        mode=config.MODE,
    )
    console.print(f"\n[bold green]Report saved to:[/] {report_path}")
    webbrowser.open(f"file:///{report_path.replace(chr(92), '/')}")


if __name__ == "__main__":
    main()
