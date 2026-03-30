"""
Evaluation engine: runs test cases, scores responses, captures performance metrics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from evaluators.llm_client import chat, ResponseMetrics
from evaluators.deepeval_adapter import create_judge_model, evaluate_criteria, evaluate_safety


@dataclass
class CriterionResult:
    text: str
    score: float          # 0.0 - 1.0
    explanation: str


@dataclass
class TestResult:
    test_id: str
    category: str
    question: str
    response: str
    criteria_results: list[CriterionResult]
    weight: int
    elapsed_seconds: float
    metrics: ResponseMetrics = field(default_factory=ResponseMetrics)
    safety: dict = field(default_factory=dict)  # {bias, toxicity, pii_leakage, hallucination}

    @property
    def score(self) -> float:
        if not self.criteria_results:
            return 0.0
        return sum(c.score for c in self.criteria_results) / len(self.criteria_results)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight

    @property
    def score_pct(self) -> float:
        return round(self.score * 100, 1)


@dataclass
class EvalReport:
    prompt_name: str
    prompt_version: str
    test_results: list[TestResult] = field(default_factory=list)
    total_elapsed: float = 0.0

    @property
    def overall_score(self) -> float:
        total_w = sum(r.weight for r in self.test_results)
        if total_w == 0:
            return 0.0
        return sum(r.weighted_score for r in self.test_results) / total_w

    @property
    def overall_pct(self) -> float:
        return round(self.overall_score * 100, 1)

    @property
    def grade(self) -> str:
        pct = self.overall_pct
        if pct >= 95: return "A+"
        if pct >= 90: return "A"
        if pct >= 85: return "A-"
        if pct >= 80: return "B+"
        if pct >= 75: return "B"
        if pct >= 70: return "B-"
        if pct >= 65: return "C+"
        if pct >= 60: return "C"
        return "D"

    def category_scores(self) -> dict[str, float]:
        from collections import defaultdict
        totals: dict[str, list[float]] = defaultdict(list)
        for r in self.test_results:
            totals[r.category].append(r.score)
        return {cat: round(sum(s) / len(s) * 100, 1) for cat, s in totals.items()}

    def weakest_criteria(self, n: int = 5) -> list[tuple[str, str, float]]:
        items: list[tuple[str, str, float]] = []
        for r in self.test_results:
            for c in r.criteria_results:
                items.append((r.test_id, c.text, c.score))
        items.sort(key=lambda x: x[2])
        return items[:n]

    # ── Safety aggregates ────────────────────────────────────────────

    def safety_summary(self) -> dict:
        """Aggregate safety metrics across all test results."""
        results_with_safety = [r for r in self.test_results if r.safety]
        if not results_with_safety:
            return {"available": False}

        metrics = {}
        for metric_name in ["bias", "toxicity", "pii_leakage", "hallucination"]:
            scores = []
            passed_count = 0
            reasons = []
            for r in results_with_safety:
                if metric_name in r.safety and r.safety[metric_name]["score"] >= 0:
                    scores.append(r.safety[metric_name]["score"])
                    if r.safety[metric_name]["passed"]:
                        passed_count += 1
                    if r.safety[metric_name]["score"] > 0.3:
                        reasons.append(f"{r.test_id}: {r.safety[metric_name]['reason'][:100]}")

            if scores:
                metrics[metric_name] = {
                    "avg_score": round(sum(scores) / len(scores), 3),
                    "max_score": round(max(scores), 3),
                    "pass_rate": round(passed_count / len(scores) * 100, 1),
                    "total_tested": len(scores),
                    "flagged_reasons": reasons[:5],
                }

        all_pass_rates = [m["pass_rate"] for m in metrics.values()]
        return {
            "available": True,
            "metrics": metrics,
            "overall_pass_rate": round(sum(all_pass_rates) / len(all_pass_rates), 1) if all_pass_rates else 0,
        }

    # ── Performance aggregates ────────────────────────────────────────

    def perf_summary(self) -> dict:
        """Aggregate performance metrics across all test results."""
        latencies = [r.metrics.latency_seconds for r in self.test_results if r.metrics.latency_seconds > 0]
        total_input = sum(r.metrics.input_tokens for r in self.test_results)
        total_output = sum(r.metrics.output_tokens for r in self.test_results)
        total_cost = sum(r.metrics.estimated_cost_usd for r in self.test_results)
        response_words = [r.metrics.response_words for r in self.test_results]

        if not latencies:
            return {"available": False}

        sorted_lat = sorted(latencies)
        p50_idx = len(sorted_lat) // 2
        p95_idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)

        return {
            "available": True,
            "avg_latency": round(sum(latencies) / len(latencies), 2),
            "min_latency": round(min(latencies), 2),
            "max_latency": round(max(latencies), 2),
            "p50_latency": round(sorted_lat[p50_idx], 2),
            "p95_latency": round(sorted_lat[p95_idx], 2),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "avg_output_tokens": round(total_output / len(self.test_results)) if self.test_results else 0,
            "avg_response_words": round(sum(response_words) / len(response_words)) if response_words else 0,
            "estimated_cost_usd": round(total_cost, 4),
            "model_id": self.test_results[0].metrics.model_id if self.test_results else "",
        }


def run_evaluation(
    system_prompt: str,
    test_cases: list[dict],
    prompt_name: str = "Unnamed",
    prompt_version: str = "0.0.0",
    domain: str = "General",
    role_slug: str = "azure_data_engineer",
    on_progress: callable = None,
) -> EvalReport:
    """Execute the full evaluation pipeline."""
    report = EvalReport(prompt_name=prompt_name, prompt_version=prompt_version)
    judge_model = create_judge_model()
    t0 = time.time()

    for i, tc in enumerate(test_cases):
        if on_progress:
            on_progress(i + 1, len(test_cases), tc["id"])

        # Step 1: Get model response + metrics
        t1 = time.time()
        response, metrics = chat(system_prompt, tc["question"], role_slug=role_slug)

        # Step 2: Evaluate response against criteria via deepeval
        eval_results = evaluate_criteria(
            question=tc["question"],
            response=response,
            criteria=tc["criteria"],
            domain=domain,
            judge_model=judge_model,
        )

        # Step 3: Run safety checks
        safety_results = evaluate_safety(
            question=tc["question"],
            response=response,
            judge_model=judge_model,
        )

        elapsed = time.time() - t1

        # Step 4: Build criterion results
        criteria_results = []
        for j, criterion_text in enumerate(tc["criteria"]):
            er = eval_results[j] if j < len(eval_results) else {"score": 0.0, "explanation": "Not evaluated"}
            criteria_results.append(
                CriterionResult(
                    text=criterion_text,
                    score=er["score"],
                    explanation=er["explanation"],
                )
            )

        report.test_results.append(
            TestResult(
                test_id=tc["id"],
                category=tc["category"],
                question=tc["question"],
                response=response,
                criteria_results=criteria_results,
                weight=tc["weight"],
                elapsed_seconds=round(elapsed, 2),
                metrics=metrics,
                safety=safety_results,
            )
        )

    report.total_elapsed = round(time.time() - t0, 2)
    return report
