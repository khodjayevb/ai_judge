"""
BYOK LLM client — supports any provider for the target model.
Providers: openai, anthropic, azure, azure_foundry, google, ollama
Returns response text + performance metrics (latency, tokens, cost).
"""

from __future__ import annotations

import time
from pathlib import Path
from dataclasses import dataclass, field

import config
from evaluators.demo_responses import get_demo_response


@dataclass
class ResponseMetrics:
    """Performance metrics captured from a single LLM call."""
    latency_seconds: float = 0.0        # Wall-clock time for the API call
    input_tokens: int = 0               # Prompt tokens consumed
    output_tokens: int = 0              # Completion tokens generated
    total_tokens: int = 0
    response_chars: int = 0             # Length of response text
    response_words: int = 0
    model_id: str = ""                  # Model that actually responded
    estimated_cost_usd: float = 0.0     # Rough cost estimate

    def to_dict(self) -> dict:
        return {
            "latency_seconds": round(self.latency_seconds, 3),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "response_chars": self.response_chars,
            "response_words": self.response_words,
            "model_id": self.model_id,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }


# Rough cost per 1M tokens (input/output) — update as pricing changes
_COST_TABLE = {
    "gpt-4o":       (2.50, 10.00),
    "gpt-4o-mini":  (0.15, 0.60),
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "claude-sonnet-4-20250514":  (3.00, 15.00),
    "claude-opus-4-20250514":    (15.00, 75.00),
    "claude-haiku-4-20250414":   (0.80, 4.00),
    "gemini-2.0-flash":          (0.10, 0.40),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    model_lower = model.lower()
    for key, (inp_cost, out_cost) in _COST_TABLE.items():
        if key in model_lower:
            return (input_tokens * inp_cost + output_tokens * out_cost) / 1_000_000
    return 0.0


def _create_client(cfg: dict):
    """Create a chat client. Returns callable(system, user, **kw) -> (str, ResponseMetrics)."""
    provider = cfg["provider"]

    if provider == "openai":
        from openai import OpenAI
        kwargs = {"api_key": cfg["api_key"]}
        if cfg["base_url"]:
            kwargs["base_url"] = cfg["base_url"]
        client = OpenAI(**kwargs)
        model = cfg["model"]

        def _call(system_prompt: str, user_message: str, **kw) -> tuple[str, ResponseMetrics]:
            msgs = [{"role": "user", "content": user_message}]
            if system_prompt:
                msgs.insert(0, {"role": "system", "content": system_prompt})
            t0 = time.perf_counter()
            r = client.chat.completions.create(
                model=model, messages=msgs,
                temperature=kw.get("temperature", config.TEMPERATURE),
                max_completion_tokens=config.MAX_TOKENS,
            )
            latency = time.perf_counter() - t0
            text = r.choices[0].message.content
            usage = r.usage
            m = ResponseMetrics(
                latency_seconds=latency,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                response_chars=len(text),
                response_words=len(text.split()),
                model_id=r.model or model,
            )
            m.estimated_cost_usd = _estimate_cost(m.model_id, m.input_tokens, m.output_tokens)
            return text, m
        return _call

    elif provider == "anthropic":
        from anthropic import Anthropic
        kwargs = {"api_key": cfg["api_key"]}
        if cfg["base_url"]:
            kwargs["base_url"] = cfg["base_url"]
        client = Anthropic(**kwargs)
        model = cfg["model"]

        def _call(system_prompt: str, user_message: str, **kw) -> tuple[str, ResponseMetrics]:
            t0 = time.perf_counter()
            r = client.messages.create(
                model=model, max_tokens=config.MAX_TOKENS,
                system=system_prompt or "",
                messages=[{"role": "user", "content": user_message}],
                temperature=kw.get("temperature", config.TEMPERATURE),
            )
            latency = time.perf_counter() - t0
            text = r.content[0].text
            m = ResponseMetrics(
                latency_seconds=latency,
                input_tokens=r.usage.input_tokens if r.usage else 0,
                output_tokens=r.usage.output_tokens if r.usage else 0,
                total_tokens=(r.usage.input_tokens + r.usage.output_tokens) if r.usage else 0,
                response_chars=len(text),
                response_words=len(text.split()),
                model_id=r.model or model,
            )
            m.estimated_cost_usd = _estimate_cost(m.model_id, m.input_tokens, m.output_tokens)
            return text, m
        return _call

    elif provider == "azure":
        from openai import AzureOpenAI
        client = AzureOpenAI(
            azure_endpoint=cfg["base_url"], api_key=cfg["api_key"],
            api_version=cfg.get("api_version", "2024-08-01-preview"),
        )
        deployment = cfg.get("deployment") or cfg["model"]

        def _call(system_prompt: str, user_message: str, **kw) -> tuple[str, ResponseMetrics]:
            msgs = [{"role": "user", "content": user_message}]
            if system_prompt:
                msgs.insert(0, {"role": "system", "content": system_prompt})
            t0 = time.perf_counter()
            r = client.chat.completions.create(
                model=deployment, messages=msgs,
                temperature=kw.get("temperature", config.TEMPERATURE),
                max_completion_tokens=config.MAX_TOKENS,
            )
            latency = time.perf_counter() - t0
            text = r.choices[0].message.content
            usage = r.usage
            m = ResponseMetrics(
                latency_seconds=latency,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                response_chars=len(text),
                response_words=len(text.split()),
                model_id=r.model or deployment,
            )
            m.estimated_cost_usd = _estimate_cost(m.model_id, m.input_tokens, m.output_tokens)
            return text, m
        return _call

    elif provider == "azure_assistant":
        # Azure AI Foundry Assistant — uses the Assistants API (thread → message → run)
        # The system prompt is baked into the assistant definition, not sent per call.
        from openai import AzureOpenAI
        client = AzureOpenAI(
            azure_endpoint=cfg["base_url"], api_key=cfg["api_key"],
            api_version=cfg.get("api_version", "2024-08-01-preview"),
        )
        assistant_id = cfg.get("deployment") or cfg["model"]  # Assistant ID

        def _call(system_prompt: str, user_message: str, **kw) -> tuple[str, ResponseMetrics]:
            t0 = time.perf_counter()
            # Create thread
            thread = client.beta.threads.create()
            # Add user message
            client.beta.threads.messages.create(
                thread_id=thread.id, role="user", content=user_message,
            )
            # Run the assistant
            run = client.beta.threads.runs.create(
                thread_id=thread.id, assistant_id=assistant_id,
            )
            # Poll for completion
            while run.status in ("queued", "in_progress"):
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

            latency = time.perf_counter() - t0

            # Get the assistant's response
            messages = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
            text = ""
            if messages.data:
                for block in messages.data[0].content:
                    if hasattr(block, "text"):
                        text += block.text.value

            # Get token usage from run
            usage = run.usage if hasattr(run, "usage") and run.usage else None
            m = ResponseMetrics(
                latency_seconds=latency,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                response_chars=len(text),
                response_words=len(text.split()) if text else 0,
                model_id=assistant_id,
            )
            m.estimated_cost_usd = _estimate_cost(cfg["model"], m.input_tokens, m.output_tokens)

            # Clean up thread
            try:
                client.beta.threads.delete(thread.id)
            except Exception:
                pass

            return text, m
        return _call

    elif provider == "azure_foundry":
        from openai import OpenAI
        base = cfg["base_url"].rstrip("/")
        if not base.endswith("/openai/v1"):
            base += "/openai/v1/"
        client = OpenAI(base_url=base, api_key=cfg["api_key"])
        model = cfg.get("deployment") or cfg["model"]

        def _call(system_prompt: str, user_message: str, **kw) -> tuple[str, ResponseMetrics]:
            msgs = [{"role": "user", "content": user_message}]
            if system_prompt:
                msgs.insert(0, {"role": "system", "content": system_prompt})
            t0 = time.perf_counter()
            r = client.chat.completions.create(
                model=model, messages=msgs,
                temperature=kw.get("temperature", config.TEMPERATURE),
                max_completion_tokens=config.MAX_TOKENS,
            )
            latency = time.perf_counter() - t0
            text = r.choices[0].message.content
            usage = r.usage
            m = ResponseMetrics(
                latency_seconds=latency,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                response_chars=len(text),
                response_words=len(text.split()),
                model_id=r.model or model,
            )
            m.estimated_cost_usd = _estimate_cost(m.model_id, m.input_tokens, m.output_tokens)
            return text, m
        return _call

    elif provider == "google":
        from google import genai
        client = genai.Client(api_key=cfg["api_key"])
        model = cfg["model"]

        def _call(system_prompt: str, user_message: str, **kw) -> tuple[str, ResponseMetrics]:
            t0 = time.perf_counter()
            r = client.models.generate_content(
                model=model, contents=user_message,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_prompt or None,
                    temperature=kw.get("temperature", config.TEMPERATURE),
                    max_output_tokens=config.MAX_TOKENS,
                ),
            )
            latency = time.perf_counter() - t0
            text = r.text
            usage = r.usage_metadata
            m = ResponseMetrics(
                latency_seconds=latency,
                input_tokens=usage.prompt_token_count if usage else 0,
                output_tokens=usage.candidates_token_count if usage else 0,
                total_tokens=usage.total_token_count if usage else 0,
                response_chars=len(text),
                response_words=len(text.split()),
                model_id=model,
            )
            m.estimated_cost_usd = _estimate_cost(m.model_id, m.input_tokens, m.output_tokens)
            return text, m
        return _call

    elif provider == "ollama":
        from openai import OpenAI
        base = cfg["base_url"] or "http://localhost:11434/v1"
        client = OpenAI(base_url=base, api_key="ollama")
        model = cfg["model"]

        def _call(system_prompt: str, user_message: str, **kw) -> tuple[str, ResponseMetrics]:
            msgs = [{"role": "user", "content": user_message}]
            if system_prompt:
                msgs.insert(0, {"role": "system", "content": system_prompt})
            t0 = time.perf_counter()
            r = client.chat.completions.create(
                model=model, messages=msgs,
                temperature=kw.get("temperature", config.TEMPERATURE),
            )
            latency = time.perf_counter() - t0
            text = r.choices[0].message.content
            usage = r.usage
            m = ResponseMetrics(
                latency_seconds=latency,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                response_chars=len(text),
                response_words=len(text.split()),
                model_id=model,
            )
            return text, m
        return _call

    else:
        raise ValueError(f"Unknown provider: {provider}. "
                         f"Supported: openai, anthropic, azure, azure_foundry, google, ollama")


# Cache clients
_client_cache: dict[str, callable] = {}


def _get_target_client():
    if "target" not in _client_cache:
        _client_cache["target"] = _create_client(config.get_target_config())
    return _client_cache["target"]


def resolve_system_prompt(local_prompt: str) -> str:
    """Resolve the system prompt based on TARGET_SYSTEM_PROMPT config."""
    source = config.TARGET_SYSTEM_PROMPT
    if source == "local":
        return local_prompt
    elif source == "none":
        return ""
    elif source.startswith("custom:"):
        return source[7:]  # Strip "custom:" prefix, return the pasted prompt
    elif source.startswith("file:"):
        p = Path(source[5:])
        if not p.exists():
            raise FileNotFoundError(f"System prompt file not found: {p}")
        return p.read_text(encoding="utf-8").strip()
    return local_prompt


def chat(
    system_prompt: str,
    user_message: str,
    role_slug: str = "azure_data_engineer",
    temperature: float | None = None,
) -> tuple[str, ResponseMetrics]:
    """Send a chat completion. Returns (response_text, metrics)."""
    if config.MODE == "demo":
        is_weak = len(system_prompt.strip()) < 500
        text = get_demo_response(role_slug, user_message, weak=is_weak)
        return text, ResponseMetrics(
            response_chars=len(text),
            response_words=len(text.split()),
            model_id="demo",
        )

    resolved_prompt = resolve_system_prompt(system_prompt)
    client_fn = _get_target_client()
    return client_fn(resolved_prompt, user_message,
                     temperature=temperature if temperature is not None else config.TEMPERATURE)
