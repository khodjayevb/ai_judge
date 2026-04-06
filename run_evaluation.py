#!/usr/bin/env python3
"""
AI Evaluation Framework — Evaluate a system prompt for any role.

Usage:
    python run_evaluation.py                              # Demo mode, default role
    python run_evaluation.py --role power_bi_engineer      # Specific role
    python run_evaluation.py --list-roles                  # Show available roles
    EVAL_MODE=foundry python run_evaluation.py --role fabric_data_engineer
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
from prompts.registry import list_roles, get_prompt, get_test_suite, role_info
from evaluators.scorer import run_evaluation
from evaluators.recommender import generate_recommendations
from reports.html_report import generate_html_report

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description="AI System Prompt Evaluator")
    parser.add_argument("--role", default=None, help="Role slug to evaluate (e.g., power_bi_engineer)")
    parser.add_argument("--list-roles", action="store_true", help="List all available roles")
    parser.add_argument("--mode", default=None, help="Override EVAL_MODE (demo/azure/foundry/openai)")
    return parser.parse_args()


def show_roles():
    table = Table(title="Available Roles", border_style="cyan")
    table.add_column("Slug", style="cyan bold")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Domain")
    table.add_column("Tests", justify="center")
    table.add_column("A/B", justify="center")

    for slug in list_roles():
        info = role_info(slug)
        table.add_row(
            slug,
            info["name"],
            info["version"],
            info["domain"],
            "Y" if info["has_tests"] else "-",
            "Y" if info["has_weak_variant"] else "-",
        )
    console.print(table)


def main():
    args = parse_args()

    if args.mode:
        config.MODE = args.mode

    if args.list_roles:
        show_roles()
        return

    role = args.role or config.EVAL_ROLE
    SYSTEM_PROMPT, PROMPT_METADATA = get_prompt(role)
    TEST_CASES = get_test_suite(role)

    prompt_source = config.TARGET_SYSTEM_PROMPT
    if prompt_source == "none":
        prompt_label = "deployed model's own prompt"
    elif prompt_source.startswith("file:"):
        prompt_label = f"file: {prompt_source[5:]}"
    else:
        prompt_label = f"{PROMPT_METADATA['name']} v{PROMPT_METADATA['version']}"

    console.print(Panel.fit(
        f"[bold cyan]AI System Prompt Evaluator[/]\n"
        f"[dim]Mode: {config.MODE} | Role: {role} | Tests: {len(TEST_CASES)}\n"
        f"Model: {config.get_model_display_name()} | Prompt: {prompt_label}[/]",
        border_style="cyan",
    ))

    if prompt_source == "none":
        console.print("[yellow]System prompt source: NONE — testing the model's deployed/built-in prompt.[/]\n")
    elif prompt_source.startswith("file:"):
        console.print(f"[yellow]System prompt source: {prompt_source}[/]\n")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("Evaluating...", total=len(TEST_CASES))

        def on_progress(current, total, test_id):
            progress.update(task, completed=current, description=f"Testing [cyan]{test_id}[/]")

        report = run_evaluation(
            system_prompt=SYSTEM_PROMPT,
            test_cases=TEST_CASES,
            prompt_name=PROMPT_METADATA["name"],
            prompt_version=PROMPT_METADATA["version"],
            domain=PROMPT_METADATA["domain"],
            role_slug=role,
            on_progress=on_progress,
        )

    console.print()
    grade_color = "green" if report.grade.startswith("A") else "yellow" if report.grade.startswith("B") else "red"
    console.print(Panel.fit(
        f"[bold {grade_color}]  Grade: {report.grade}  |  Score: {report.overall_pct}%  [/]",
        border_style=grade_color, title="Results",
    ))

    # Performance summary
    perf = report.perf_summary()
    if perf.get("available"):
        console.print(f"\n[bold]Performance:[/]")
        console.print(
            f"  Latency: avg [cyan]{perf['avg_latency']}s[/] | p95 [cyan]{perf['p95_latency']}s[/] | "
            f"Tokens: [cyan]{perf['total_tokens']:,}[/] total | "
            f"Cost: [cyan]${perf['estimated_cost_usd']:.4f}[/]"
        )

    console.print("\n[bold]Category Scores:[/]")
    for cat, score in sorted(report.category_scores().items()):
        bar_len = int(score / 100 * 30)
        color = "green" if score >= 90 else "yellow" if score >= 75 else "red"
        bar = f"[{color}]{'#' * bar_len}{'-' * (30 - bar_len)}[/]"
        console.print(f"  {cat:<25} {bar} {score}%")

    recommendations = generate_recommendations(report)
    if recommendations:
        console.print(f"\n[bold]Top Recommendations ({len(recommendations)}):[/]")
        for rec in recommendations[:5]:
            p_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}[rec.priority]
            console.print(f"  [{p_color}]{rec.priority}[/] {rec.title}")

    # For the report: show local prompt if used, or indicate deployed model
    if prompt_source == "none":
        _report_prompt = "(No system prompt sent — testing the model's deployed/built-in prompt)"
    elif prompt_source.startswith("file:"):
        _report_prompt = Path(prompt_source[5:]).read_text(encoding="utf-8").strip()
    else:
        _report_prompt = SYSTEM_PROMPT

    judge_cfg = config.get_judge_config()
    _judge_display = f"{judge_cfg['model']} ({judge_cfg['provider']})"

    from evaluators.judge_context import get_judge_context_info
    report_path = generate_html_report(
        report, recommendations,
        output_path=f"reports/evaluation_report_{role}.html",
        system_prompt=_report_prompt,
        model_name=config.get_model_display_name(),
        judge_model_name=_judge_display,
        mode=config.MODE,
        judge_context_info=get_judge_context_info(role),
    )
    console.print(f"\n[bold green]Report saved to:[/] {report_path}")

    # Log to history
    from results_db import log_run
    run_id = log_run(
        report=report, role=role,
        model=config.get_model_display_name(),
        judge_model=_judge_display,
        provider=config.TARGET_PROVIDER,
        mode=config.MODE,
        prompt_source=prompt_source,
        report_path=report_path,
        run_type="evaluation",
    )
    console.print(f"[dim]Run #{run_id} logged to history. View dashboard: python app.py[/]")

    webbrowser.open(f"file:///{report_path.replace(chr(92), '/')}")


if __name__ == "__main__":
    main()
