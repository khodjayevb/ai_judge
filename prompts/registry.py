"""
Prompt registry — auto-discovers role prompts and their test suites.

Convention:
  - Prompt: prompts/{role_slug}.py  → exports SYSTEM_PROMPT, PROMPT_METADATA
  - Tests:  test_suites/{role_slug}_tests.py → exports TEST_CASES
  - Weak variant: prompts/{role_slug}_v1_weak.py (optional, for A/B comparison)
"""

from __future__ import annotations

import importlib
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_TESTS_DIR = _PROMPTS_DIR.parent / "test_suites"

# Files to skip when listing roles
_SKIP = {"__init__", "registry"}


def list_roles(include_weak: bool = False) -> list[str]:
    """Return all available role slugs."""
    roles = []
    for f in sorted(_PROMPTS_DIR.glob("*.py")):
        slug = f.stem
        if slug in _SKIP:
            continue
        if not include_weak and slug.endswith("_v1_weak"):
            continue
        # Verify the file exports the required attributes
        try:
            mod = importlib.import_module(f"prompts.{slug}")
            if hasattr(mod, "SYSTEM_PROMPT") and hasattr(mod, "PROMPT_METADATA"):
                roles.append(slug)
        except Exception:
            continue
    return roles


def get_prompt(role_slug: str) -> tuple[str, dict]:
    """Return (SYSTEM_PROMPT, PROMPT_METADATA) for a role."""
    mod = importlib.import_module(f"prompts.{role_slug}")
    return mod.SYSTEM_PROMPT, mod.PROMPT_METADATA


def get_test_suite(role_slug: str) -> list[dict]:
    """Return TEST_CASES for a role."""
    # Strip _v1_weak suffix to find the base test suite
    base_slug = role_slug.replace("_v1_weak", "")
    mod = importlib.import_module(f"test_suites.{base_slug}_tests")
    return mod.TEST_CASES


def get_weak_variant(role_slug: str) -> str | None:
    """Return the weak variant slug if it exists, else None."""
    weak_slug = f"{role_slug}_v1_weak"
    path = _PROMPTS_DIR / f"{weak_slug}.py"
    if path.exists():
        return weak_slug
    return None


def role_info(role_slug: str) -> dict:
    """Return metadata for display."""
    _, meta = get_prompt(role_slug)
    has_tests = (_TESTS_DIR / f"{role_slug}_tests.py").exists()
    has_weak = get_weak_variant(role_slug) is not None
    return {
        "slug": role_slug,
        "name": meta.get("name", role_slug),
        "version": meta.get("version", "?"),
        "domain": meta.get("domain", "?"),
        "has_tests": has_tests,
        "has_weak_variant": has_weak,
    }
