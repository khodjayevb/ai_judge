"""
Configuration for the AI Evaluation Framework.
BYOK: Bring Your Own Key — supports any LLM provider.
"""

import os
from pathlib import Path

# Load .env file if present (no extra dependency needed)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and not os.environ.get(key):
                os.environ[key] = value

# --------------------------------------------------------------------------
# MODE: "demo" or "live"
#   - "demo" : Pre-generated responses, no API key needed
#   - "live" : Uses TARGET_PROVIDER and JUDGE_PROVIDER for real API calls
# --------------------------------------------------------------------------
MODE = os.getenv("EVAL_MODE", "demo")

# --------------------------------------------------------------------------
# TARGET MODEL — the model being evaluated
# --------------------------------------------------------------------------
# Provider: openai | anthropic | azure | azure_foundry | google | ollama
TARGET_PROVIDER = os.getenv("TARGET_PROVIDER", "openai")
TARGET_API_KEY = os.getenv("TARGET_API_KEY", "")
TARGET_MODEL = os.getenv("TARGET_MODEL", "gpt-4o")
TARGET_BASE_URL = os.getenv("TARGET_BASE_URL", "")   # Override endpoint (optional)
TARGET_API_VERSION = os.getenv("TARGET_API_VERSION", "2024-08-01-preview")  # Azure only
TARGET_DEPLOYMENT = os.getenv("TARGET_DEPLOYMENT", "")  # Azure: deployment name if different from model

# --------------------------------------------------------------------------
# JUDGE MODEL — scores responses (falls back to target if not set)
# --------------------------------------------------------------------------
JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", "")      # Falls back to TARGET_PROVIDER
JUDGE_API_KEY = os.getenv("JUDGE_API_KEY", "")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "")
JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", "")
JUDGE_API_VERSION = os.getenv("JUDGE_API_VERSION", "")
JUDGE_DEPLOYMENT = os.getenv("JUDGE_DEPLOYMENT", "")

# --------------------------------------------------------------------------
# SYSTEM PROMPT SOURCE
# --------------------------------------------------------------------------
# "local"  — use system prompt from prompts/ in this codebase (default)
# "none"   — send NO system prompt; test whatever is configured in the deployed model/assistant
# "file:/path/to/prompt.txt" — load system prompt from an external file
TARGET_SYSTEM_PROMPT = os.getenv("TARGET_SYSTEM_PROMPT", "local")

# --------------------------------------------------------------------------
# Role selection
# --------------------------------------------------------------------------
EVAL_ROLE = os.getenv("EVAL_ROLE", "azure_data_engineer")

# --------------------------------------------------------------------------
# Evaluation settings
# --------------------------------------------------------------------------
MAX_TOKENS = 2048
TEMPERATURE = 0.3


def get_target_config() -> dict:
    """Resolved target model configuration."""
    return {
        "provider": TARGET_PROVIDER,
        "api_key": TARGET_API_KEY,
        "model": TARGET_MODEL,
        "base_url": TARGET_BASE_URL,
        "api_version": TARGET_API_VERSION,
        "deployment": TARGET_DEPLOYMENT or TARGET_MODEL,
    }


def get_judge_config() -> dict:
    """Resolved judge model configuration — falls back to target."""
    target = get_target_config()
    return {
        "provider": JUDGE_PROVIDER or target["provider"],
        "api_key": JUDGE_API_KEY or target["api_key"],
        "model": JUDGE_MODEL or target["model"],
        "base_url": JUDGE_BASE_URL or target["base_url"],
        "api_version": JUDGE_API_VERSION or target["api_version"],
        "deployment": JUDGE_DEPLOYMENT or JUDGE_MODEL or target["deployment"],
    }


def get_model_display_name() -> str:
    """Human-readable model name for reports."""
    if MODE == "demo":
        return "demo (pre-generated)"
    provider = TARGET_PROVIDER
    model = TARGET_MODEL
    return f"{model} ({provider})"
