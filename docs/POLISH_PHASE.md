# Polish Phase — Refine, Harden, Ship

**Date:** April 5, 2026
**Status:** Active — no new features, only refinement

---

## Guiding Principles

1. **No new features** — refine what exists, don't add more
2. **Fix edge cases** — find and fix every broken path
3. **Backend robustness** — error handling, retry logic, timeouts
4. **UI consistency** — every tab should look and behave the same way
5. **Test everything** — verify each feature works end-to-end with real API calls
6. **Clean code** — remove dead code, unused imports, stale references

---

## Current Feature Inventory

### Core Evaluation
| Feature | Status | Notes |
|---------|--------|-------|
| Run Evaluation (single) | Working | GEval + DAG + Safety metrics |
| Multi-run averaging (1x-5x) | Working | Verify averaging logic correctness |
| A/B Comparison | Working | Test with different models/prompts |
| Consolidated scoring (60% GEval + 40% DAG) | Working | Verify formula in all paths |
| Per-test safety badges | Working | Bias, Toxicity, PII, Hallucination |

### Scoring & Judging
| Feature | Status | Notes |
|---------|--------|-------|
| GEval (LLM-as-judge) | Working | With rubric + context injection |
| DAG (deterministic, 4 dimensions) | Working | Addressed, Specificity, Actionability, Accuracy |
| Judge context injection | Working | Loads from docs/{role}/ |
| Scoring rubric (6-level) | Working | Injected into every GEval prompt |
| Judge calibration (gold standard) | Working | 8 pre-scored responses, generates report |

### Safety & Security
| Feature | Status | Notes |
|---------|--------|-------|
| Bias detection | Working | DeepEval BiasMetric |
| Toxicity detection | Working | DeepEval ToxicityMetric |
| PII leakage (custom GEval) | Working | Distinguishes real PII from examples |
| Hallucination detection | Working | Requires context in test cases |
| Red team (DeepTeam) | Partial | PII/Toxicity attacks error on Azure (content filter) |

### Test Generation
| Feature | Status | Notes |
|---------|--------|-------|
| Generate from role prompt | Working | Single LLM call, fast |
| Generate from reference docs | Working | Auto-discovers docs/{role}/ |
| Manual test case entry | Working | Via Generate Tests tab |
| Save as test suite | Working | Creates Python file |
| Run evaluation on generated | Working | With history logging |

### Dashboard UI
| Feature | Status | Notes |
|---------|--------|-------|
| Run Evaluation tab | Working | Role, model, prompt, runs dropdowns |
| A/B Comparison tab | Working | Flexible Run A vs Run B config |
| Red Team tab | Working | With model/prompt selection |
| Generate Tests tab | Working | Generate + manual + save + evaluate |
| Judge Calibration tab | Working | Gold standard with reports |
| Manage Roles tab | Working | Create, edit, upload, version control |
| Docs tab | Working | Full documentation with links |
| Settings modal | Working | Connection, models, temperature, assistants |
| Theme toggle | Working | Dark/light, persists in localStorage |
| Per-tab history tables | Working | Custom columns per tab type |
| CSV export | Working | From evaluation history |
| Unique report filenames | Working | Timestamped, no overwrites |

### Reports (HTML)
| Feature | Status | Notes |
|---------|--------|-------|
| Section 1: Prompt Quality | Working | Grade, categories, charts, recommendations |
| Section 2: Safety | Working | 4 metrics with detail cards, flagged responses |
| Section 3: Performance | Working | Latency, tokens, cost |
| Evaluation config card | Working | Target, judge, context status, rubric |
| Jump links between sections | Working | |
| GEval + DAG dual display | Working | Score cards, charts, per-criterion |
| DAG dimension badges | Working | Addressed, Specificity, Actionability, Accuracy |

### Infrastructure
| Feature | Status | Notes |
|---------|--------|-------|
| BYOK (6 providers) | Working | azure, azure_assistant, openai, anthropic, google, ollama |
| Azure Foundry Assistant support | Working | Per-role assistant IDs |
| SQLite history (eval_runs) | Working | With DAG, consolidated, judge_model columns |
| SQLite calibration history | Working | Separate table with report links |
| Role version control | Working | Snapshots, diff, restore |
| Auto-improve prompt | Working | Generates improved prompt from weaknesses |
| Test connection | Working | API verification from settings |
| Test assistants | Working | Per-assistant verification |

---

## Known Issues to Fix

1. **Thread safety** — global config mutation in app.py for concurrent runs
2. **Dead demo code** — evaluators/demo_responses.py never called (MODE always "live")
3. **Old Settings tab HTML** — placeholder div still in DOM from removed tab
4. **Red team PII/Toxicity** — Azure content filter blocks attack generation
5. **No retry logic** — API call failures are not retried
6. **No request timeouts** — long-running API calls can hang
7. **Cost table outdated** — hardcoded model pricing in llm_client.py
8. **Windows emoji crashes** — multiple Rich console patches scattered across files

---

## Polish Checklist

### Backend
- [ ] Add try/except with retry (3 attempts) for all LLM API calls
- [ ] Add configurable timeout on API calls
- [ ] Remove dead demo response code
- [ ] Consolidate Windows emoji patches into one utility
- [ ] Add structured logging (Python logging module)
- [ ] Validate test case format before evaluation
- [ ] Handle empty test suites gracefully

### Frontend
- [ ] Consistent button styles across all tabs
- [ ] Loading states for all async operations
- [ ] Error messages shown inline (not just browser alerts)
- [ ] Responsive layout testing on different screen sizes
- [ ] Consistent table column widths
- [ ] Verify all "View Report" links work

### Testing
- [ ] Run each tab's primary workflow end-to-end
- [ ] Test with multiple roles
- [ ] Test connection with valid and invalid credentials
- [ ] Test assistant mapping with real Foundry assistants
- [ ] Verify multi-run averaging produces correct scores
- [ ] Verify version control saves and restores correctly
- [ ] Test file upload for prompts, context, and test cases

### Documentation
- [ ] Review all Docs tab content for accuracy
- [ ] Update FAQ with recent changes
- [ ] Verify all external links (DeepEval, DeepTeam)
- [ ] Update README.md to match current state
- [ ] Update presentation with latest features
