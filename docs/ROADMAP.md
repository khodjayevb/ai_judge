# AI Evaluation Framework — Development Roadmap

**Document Version:** 1.0
**Date:** March 30, 2026
**Status:** Active

---

## Current State (v1.0)

The framework is operational with the following capabilities:

- **7 roles** evaluated: 3 clinical trials (DCRI) + 4 data platform
- **BYOK model support**: OpenAI, Anthropic/Claude, Azure OpenAI, Azure AI Foundry, Google Gemini, Ollama
- **DeepEval GEval** as LLM-as-judge for criterion-level scoring
- **Web dashboard** (Flask) with run controls, A/B comparison, and history tracking
- **Performance metrics**: latency, token usage, cost estimation
- **SQLite history** with CSV export
- **HTML reports** with prompt quality (Section 1) and performance (Section 2)
- **CLI runners** for evaluation and A/B comparison
- **Separate target/judge models** for unbiased evaluation
- **Flexible prompt source**: local codebase, deployed model, or external file

### Test Coverage by Regulation

| Regulation | Tests | Roles |
|-----------|-------|-------|
| FDA 21 CFR Part 11 | Audit trails, e-signatures, access control, validation | Clinical DE, Security |
| ICH GCP E6(R2) | Source data verification, protocol compliance, safety reporting | Clinical DE, Reporting |
| HIPAA | Safe Harbor de-identification, encryption, access logging | Clinical DE, Security |
| GDPR | Cross-border transfer, right to erasure, data minimization | Clinical DE, Security |
| CDISC SDTM IG v3.4 | Variable naming, Pinnacle 21 validation, RELREC | Clinical DE |
| CDISC ADaM IG v1.3 | Derived variables, population flags, define.xml | Clinical DE, Reporting |
| ICH E2B(R3) | MedDRA coding, adverse event reporting | Clinical DE |
| NIST 800-53 | Network segmentation, vulnerability management, key management | Clinical Security |

---

## Phase 1: Safety & Adversarial Testing

**Priority:** HIGH — Required by DCRI test suite (TEAM-004)
**Timeline:** Next sprint
**Rationale:** The DCRI Clinical Trials Test Suites document Section 6.1 explicitly requires:
- *"Execute prompt injection test suite (100+ adversarial prompts); verify zero PHI leakage"*
- *"AI responses contain no patient names, dates of birth, site-specific identifiers, or other PHI"*

### 1.1 Red Teaming with DeepTeam

| Item | Description | Effort |
|------|-------------|--------|
| Integrate DeepTeam framework | DeepEval's companion red teaming tool with 40+ adversarial attack vectors | Medium |
| PHI leakage testing | Prompt injection attempts to extract patient data, site identifiers, treatment assignments | Medium |
| Jailbreak resistance | Test model's ability to maintain clinical persona under adversarial prompts | Medium |
| Data extraction attacks | Verify model doesn't reveal system prompt contents or training data | Low |
| Multi-turn attack simulation | Crescendo jailbreaking, linear escalation, tree-based attacks | Medium |

**Success Criteria:** Zero PHI leakage across 100+ adversarial prompts for all clinical roles.

### 1.2 Safety Metrics

| Item | Description | Effort |
|------|-------------|--------|
| BiasMetric | Detect gender, racial, age bias in clinical recommendations | Low |
| ToxicityMetric | Evaluate appropriateness of language in clinical context | Low |
| PIILeakageMetric | Automated detection of personally identifiable information in responses | Low |

**Implementation:** Add these as standard metrics alongside GEval for all clinical roles. One-line addition per metric in `deepeval_adapter.py`.

### 1.3 Hallucination Detection

| Item | Description | Effort |
|------|-------------|--------|
| HallucinationMetric | Detect fabricated regulation citations, invented CDISC standards, or fake drug names | Low |
| Ground truth context | Provide regulatory text as context for faithfulness checking | Medium |

**Why it matters:** A model citing "21 CFR Part 11 §11.10(z)" (which doesn't exist) could lead to compliance failures. Hallucination detection catches this.

---

## Phase 2: Expanded Evaluation Capabilities

**Priority:** MEDIUM — Extends framework depth
**Timeline:** Sprint +1
**Rationale:** Move beyond single-turn Q&A to cover real-world usage patterns.

### 2.1 Multi-Turn Conversation Evaluation

| Item | Description | Effort |
|------|-------------|--------|
| ConversationalTestCase support | DeepEval's multi-turn test case format | Medium |
| Multi-turn test suites | Clinical scenarios requiring follow-up questions (e.g., troubleshooting a pipeline failure) | Medium |
| Context retention metrics | Does the model remember earlier context in a conversation? | Low |
| ConversationalGEval | DeepEval's conversation-aware version of GEval | Low |

**Example scenario:** User asks about SDTM mapping → follow-up about a specific domain (AE) → follow-up about timing variables → asks for code. The model must maintain context throughout.

### 2.2 RAG Evaluation (if/when RAG is implemented)

| Item | Description | Effort |
|------|-------------|--------|
| ContextualRelevancyMetric | Does retrieved context match the query? | Low |
| FaithfulnessMetric | Is the response faithful to retrieved context (no hallucination)? | Low |
| ContextualPrecisionMetric | Are the most relevant chunks ranked highest? | Low |
| ContextualRecallMetric | Were all relevant chunks retrieved? | Low |

**When to implement:** When DCRI adds a RAG pipeline (e.g., retrieving from SOPs, protocol documents, or regulatory databases to augment AI responses).

### 2.3 DAG Metric (Deterministic Alternative to GEval)

| Item | Description | Effort |
|------|-------------|--------|
| Implement DAG metric | DeepEval's newest metric: fully deterministic, decision-tree based | Low |
| Run DAG alongside GEval | Compare scoring consistency between the two approaches | Low |
| Evaluate for clinical use | Determine if DAG's determinism is better suited for regulated environments | Low |

**Why consider:** GEval is non-deterministic (different scores on re-run). For regulated clinical environments where reproducibility matters, DAG's deterministic scoring may be preferred.

### 2.4 Synthetic Test Generation

| Item | Description | Effort |
|------|-------------|--------|
| DeepEval Synthesizer integration | Auto-generate test cases from source documents | Medium |
| Generate from DCRI docs | Feed SOPs, protocols, regulatory text to create test scenarios | Medium |
| Human review workflow | Generated tests must be reviewed by domain experts before use | Low |

**Value:** Currently all 160 criteria are manually authored. Synthetic generation could scale to 500+ criteria across new domains with human review as quality gate.

---

## Phase 3: Production Hardening & CI/CD

**Priority:** MEDIUM — Required for team-wide adoption
**Timeline:** Sprint +2
**Rationale:** Move from a single-user tool to a team-wide platform with automated quality gates.

### 3.1 Pytest Integration

| Item | Description | Effort |
|------|-------------|--------|
| Migrate to deepeval test runner | `deepeval test run test_clinical_de.py` | Medium |
| CI/CD pipeline integration | Run evaluations on PR merge or schedule | Medium |
| Baseline tracking | `--baseline` flag to compare against previous best | Low |
| Test tagging and filtering | `--include-tags clinical --exclude-tags wip` | Low |
| Threshold gates | Fail CI if score drops below configurable threshold (e.g., 80%) | Low |

**Goal:** `git push` → CI runs evaluation → blocks merge if prompt quality drops below threshold.

### 3.2 Baseline Regression Detection

| Item | Description | Effort |
|------|-------------|--------|
| Baseline storage | Save "known good" scores as baselines per role | Low |
| Regression alerts | Flag when a new evaluation scores significantly lower than baseline | Medium |
| Trend visualization | Score-over-time chart in dashboard | Medium |
| Statistical significance | P-value calculation for A/B comparisons, not just raw deltas | Low |

**Why:** Model provider updates (e.g., GPT-4o version bump) can silently degrade quality. Regression detection catches this automatically.

### 3.3 Thread-Safe Dashboard

| Item | Description | Effort |
|------|-------------|--------|
| Per-request config isolation | Replace global config mutation with request-scoped context | Medium |
| Concurrent run support | Multiple team members running evaluations simultaneously | Medium |
| Job queue | Queue long-running evaluations instead of blocking threads | Medium |

### 3.4 Observability

| Item | Description | Effort |
|------|-------------|--------|
| Structured logging | Python `logging` module with JSON output | Low |
| API call retry logic | Exponential backoff for rate limits and transient errors | Medium |
| Request timeout protection | Configurable timeouts on all LLM API calls | Low |
| Error reporting | Detailed error capture instead of truncated messages | Low |

---

## Phase 4: Scale & Collaboration

**Priority:** LOW — Future enhancements
**Timeline:** Quarterly planning
**Rationale:** Scale to more teams, more roles, and enterprise-level collaboration.

### 4.1 Confident AI Dashboard (or Self-Hosted Alternative)

| Item | Description | Effort |
|------|-------------|--------|
| Evaluate Confident AI | DeepEval's cloud platform for team dashboards and collaboration | Low |
| Self-hosted option | Docker deployment within DCRI network for data sovereignty | Medium |
| Team collaboration | Comments on test results, teammate tagging, shared reports | - |
| Automated regression alerts | Email/Slack notifications on score drops | - |

**Decision point:** Evaluate whether Confident AI meets DCRI security requirements (data residency, PHI concerns) or if self-hosted is required.

### 4.2 Model Comparison Matrix

| Item | Description | Effort |
|------|-------------|--------|
| Multi-model evaluation | Run same test suite across N models in one batch | Medium |
| Comparison matrix report | Side-by-side scoring table for 3+ models | Medium |
| Cost-performance analysis | Plot quality vs cost vs latency for model selection | Low |

**Use case:** "Should we use GPT-4o, Claude Sonnet, or Llama 3.1 for our clinical data engineer assistant?" — run one evaluation, get a ranked comparison.

### 4.3 Custom Criteria Builder (UI)

| Item | Description | Effort |
|------|-------------|--------|
| Web form for test case creation | Non-technical users can add questions + criteria via UI | High |
| Preview and validation | Dry-run a test case before adding to suite | Medium |
| Export to Python | Generate test suite code from UI-created tests | Medium |

**Value:** Enables clinical data managers and biostatisticians to contribute test cases without writing Python.

### 4.4 Prompt Auto-Improvement

| Item | Description | Effort |
|------|-------------|--------|
| Recommendation-to-prompt pipeline | Automatically apply recommendations to improve the system prompt | High |
| Iterative optimization loop | Run eval → get recs → apply → re-eval → repeat until score plateau | High |
| Human-in-the-loop approval | Generated prompt changes require human review before adoption | Medium |

**Caution:** For regulated clinical environments, any auto-generated prompt changes MUST go through human review and validation before deployment.

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-29 | Use DeepEval GEval as primary metric | Industry standard LLM-as-judge, supports Azure OpenAI |
| 2026-03-29 | BYOK architecture | Team uses multiple providers, need flexibility |
| 2026-03-29 | Separate target/judge models | Avoid self-grading bias, especially for clinical compliance |
| 2026-03-30 | Prioritize red teaming (Phase 1) | DCRI TEAM-004 requires adversarial PHI testing |
| 2026-03-30 | DAG metric evaluation planned (Phase 2) | Determinism important for regulated environments |

---

## Appendix: DeepEval Features Reference

| Feature | DeepEval Module | Current Status |
|---------|----------------|----------------|
| GEval (LLM-as-judge) | `deepeval.metrics.GEval` | Implemented |
| Answer Relevancy | `deepeval.metrics.AnswerRelevancyMetric` | Not yet |
| Faithfulness | `deepeval.metrics.FaithfulnessMetric` | Not yet |
| Hallucination | `deepeval.metrics.HallucinationMetric` | Planned (Phase 1) |
| Bias | `deepeval.metrics.BiasMetric` | Planned (Phase 1) |
| Toxicity | `deepeval.metrics.ToxicityMetric` | Planned (Phase 1) |
| PII Leakage | `deepeval.metrics.PIILeakageMetric` | Planned (Phase 1) |
| DAG Metric | `deepeval.metrics.DAGMetric` | Planned (Phase 2) |
| Conversational GEval | `deepeval.metrics.ConversationalGEval` | Planned (Phase 2) |
| ConversationalTestCase | `deepeval.test_case.ConversationalTestCase` | Planned (Phase 2) |
| Red Teaming | `deepteam` | Planned (Phase 1) |
| Synthesizer | `deepeval.synthesizer.Synthesizer` | Planned (Phase 2) |
| EvaluationDataset | `deepeval.dataset.EvaluationDataset` | Not yet |
| Pytest integration | `deepeval test run` | Planned (Phase 3) |
| Confident AI | `deepeval login` | Evaluate (Phase 4) |
