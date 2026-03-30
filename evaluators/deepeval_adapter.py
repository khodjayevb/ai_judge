"""
DeepEval adapter — bridges the evaluation framework to deepeval's GEval metrics.
Supports any judge provider via BYOK config.
In demo mode, bypasses deepeval entirely and uses simulated scoring.
"""

from __future__ import annotations

import os
import config
from evaluators.demo_responses import demo_judge_scores

# Disable deepeval telemetry before any deepeval import
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"


def create_judge_model():
    """Create a deepeval-compatible judge model from config.

    DeepEval natively supports:
      - OpenAI (pass model name string, set OPENAI_API_KEY env)
      - Azure OpenAI (AzureOpenAIModel)
      - Anthropic (AnthropicModel) — deepeval >= 1.5
    For other providers, we use a custom wrapper.
    """
    if config.MODE == "demo":
        return None

    judge = config.get_judge_config()
    provider = judge["provider"]

    if provider == "openai":
        os.environ["OPENAI_API_KEY"] = judge["api_key"]
        if judge["base_url"]:
            os.environ["OPENAI_BASE_URL"] = judge["base_url"]
        return judge["model"]  # deepeval accepts model name string for OpenAI

    elif provider in ("azure", "azure_foundry"):
        from deepeval.models import AzureOpenAIModel
        base_url = judge["base_url"]
        # azure_foundry: ensure /openai/v1/ suffix for deepeval compatibility
        if provider == "azure_foundry" and base_url and not base_url.rstrip("/").endswith("/openai/v1"):
            base_url = base_url.rstrip("/") + "/openai/v1/"
        return AzureOpenAIModel(
            model=judge["model"],
            deployment_name=judge["deployment"],
            api_key=judge["api_key"],
            base_url=base_url,
            api_version=judge.get("api_version", "2024-06-01"),
            temperature=0.1,
        )

    elif provider == "anthropic":
        # DeepEval has AnthropicModel support
        try:
            from deepeval.models import AnthropicModel
            return AnthropicModel(
                model=judge["model"],
                api_key=judge["api_key"],
                temperature=0.1,
            )
        except ImportError:
            # Fallback: use custom DeepEvalBaseLLM wrapper
            return _create_custom_judge(judge)

    elif provider == "google":
        try:
            from deepeval.models import GeminiModel
            return GeminiModel(
                model=judge["model"],
                api_key=judge["api_key"],
                temperature=0.1,
            )
        except ImportError:
            return _create_custom_judge(judge)

    else:
        # ollama or any other provider — use custom wrapper
        return _create_custom_judge(judge)


def _create_custom_judge(judge_cfg: dict):
    """Wrap any provider as a deepeval-compatible model using DeepEvalBaseLLM."""
    from deepeval.models import DeepEvalBaseLLM
    from evaluators.llm_client import _create_client

    client_fn = _create_client(judge_cfg)

    class CustomJudge(DeepEvalBaseLLM):
        def __init__(self):
            self.model_name = judge_cfg["model"]

        def load_model(self):
            return self.model_name

        def generate(self, prompt: str, schema=None) -> str:
            text, _ = client_fn("You are an evaluation judge. Return JSON when asked.", prompt)
            return text

        async def a_generate(self, prompt: str, schema=None) -> str:
            return self.generate(prompt, schema)

        def get_model_name(self) -> str:
            return self.model_name

    return CustomJudge()


def evaluate_criteria(
    question: str,
    response: str,
    criteria: list[str],
    domain: str,
    judge_model,
) -> list[dict]:
    """
    Evaluate a response against a list of criteria.
    Returns list of {"score": float, "explanation": str} — one per criterion.
    """
    if config.MODE == "demo":
        seed_hint = question + response
        return demo_judge_scores(response, len(criteria), seed_hint)

    return _evaluate_with_deepeval(question, response, criteria, domain, judge_model)


def _evaluate_with_deepeval(
    question: str,
    response: str,
    criteria: list[str],
    domain: str,
    judge_model,
) -> list[dict]:
    """Run deepeval GEval for each criterion."""
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    from deepeval.metrics import GEval

    test_case = LLMTestCase(
        input=question,
        actual_output=response,
    )

    results = []
    for criterion in criteria:
        metric = GEval(
            name=criterion[:60],
            criteria=(
                f"Evaluate whether the response adequately addresses: {criterion}. "
                f"Context: This is a {domain} assistant."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=judge_model,
            threshold=0.5,
            verbose_mode=False,
        )
        try:
            metric.measure(test_case)
            results.append({
                "score": round(metric.score, 2),
                "explanation": metric.reason or "No explanation provided.",
            })
        except Exception as e:
            results.append({
                "score": 0.0,
                "explanation": f"Evaluation error: {str(e)[:200]}",
            })

    return results
