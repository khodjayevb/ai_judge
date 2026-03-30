# Known Issues & Status

**Date:** March 30, 2026
**Last Updated:** March 30, 2026

---

## Red Team Module

### Issue 1: PII Leakage and Toxicity attacks fail with Azure OpenAI
**Status:** UNDERSTOOD — Azure limitation, not a code bug
**Severity:** MEDIUM

**Symptoms:**
- PII Leakage: `"Attack simulation failed — model refused to generate adversarial prompts"`
- Toxicity: `"Azure content filter blocked attack generation"`

**Root Cause:** DeepTeam uses the `simulator_model` to GENERATE attack prompts. Azure's content safety filter blocks:
- PII extraction prompts → model returns None → `'NoneType' has no attribute 'data'`
- Toxic content generation → HTTP 400 "The response was filtered"

**This is actually positive:** Azure refuses to create harmful content, even for testing purposes.

**Workaround:** To fully test PII/Toxicity:
- Use an unrestricted model (e.g., local Ollama) as `simulator_model`
- Keep Azure as the `evaluation_model` (judge) and target
- OR use OpenAI directly (less restrictive content filters for research)

**Current behavior:** Bias testing works correctly (100% pass rate). PII/Toxicity show as ERROR with friendly messages, excluded from overall pass rate.

---

### Issue 2: DeepTeam Rich console crashes on Windows (FIXED)
**Status:** FIXED
**Fix:** Monkey-patch `RedTeamer._print_risk_assessment` and `RedTeamer._post_risk_assessment` to no-op. Both use Rich console with emoji characters that crash on Windows cp1252 encoding.

---

### Issue 3: DeepTeam async a_generate returns None (FIXED)
**Status:** FIXED
**Fix:** Patched `PIILeakage.a_simulate_attacks` and `Toxicity.a_simulate_attacks` to use synchronous `simulate_attacks` instead. The async path has a bug with Azure model's schema parameter.

---

### Issue 4: Model responds to bias prompts
**Status:** PARTIALLY RESOLVED
**Severity:** MEDIUM

Some bias attacks succeed — the model answers stereotype questions instead of refusing. With the current DCRI clinical data engineer prompt, GPT-4o scores ~83-100% on bias resistance.

**Improvement:** Add explicit anti-bias guardrails to system prompts:
- "NEVER engage with questions about racial, gender, or religious stereotypes"
- "If asked about bias or stereotypes, redirect to evidence-based clinical trial practices"

---

## Dashboard

### Issue 5: Thread-safety with global config
**Status:** OPEN — Deferred to Phase 3
**Severity:** MEDIUM

Running multiple evaluations concurrently mutates global config. Not an issue for single-user use.

---

## DeepEval Integration

### Issue 6: API version must be 2024-08-01-preview or later
**Status:** FIXED
**Root Cause:** DeepEval GEval uses `json_schema` response format which requires `api_version >= 2024-08-01-preview`. Default was `2024-06-01`.

---

## Git Log

```
15d776d Fix red team: patch async bug, add friendly error messages
3b9aa02 Fix red team: patch DeepTeam print methods, handle errors properly
d484503 Fix red team integration and document known issues
1690c78 Phase 1: Safety metrics and red teaming
5fc1ed8 Add development roadmap with 4 phases
f97e12c Fix critical bugs found in code review
be2269f Initial commit: AI System Prompt Evaluation Framework
```
