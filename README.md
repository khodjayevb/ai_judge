# AI System Prompt Evaluation Framework

Evaluate, score, and improve AI system prompts with automated test suites, LLM-as-judge scoring (via **deepeval**), performance metrics, and visual reports. **BYOK** — works with any LLM provider.

Built for **DCRI Clinical Trials Data Management** with test criteria mapped to FDA 21 CFR Part 11, ICH GCP E6(R2), HIPAA, GDPR, and CDISC standards.

## Quick Start

### Web Dashboard (recommended)
```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

The dashboard provides:
- **Run Evaluation** tab — select role, model, and prompt source, then run with a single click
- **A/B Comparison** tab — compare different models, prompts, or both side-by-side
- **Evaluation History** — tracks every run with grade, score, latency, tokens, and cost
- Live progress bar during evaluation

### CLI
```bash
python run_evaluation.py --list-roles                          # See all roles
python run_evaluation.py --role clinical_data_engineer          # Run evaluation
python run_comparison.py --role clinical_data_engineer          # A/B comparison
```

### Demo Mode (no API key needed)
```bash
EVAL_MODE=demo python run_evaluation.py --role clinical_data_engineer
```

## BYOK — Bring Your Own Key

Configure your model provider in `.env` (copy from `.env.example`):

```env
EVAL_MODE=live
TARGET_PROVIDER=azure          # openai | anthropic | azure | azure_foundry | google | ollama
TARGET_API_KEY=your-key
TARGET_MODEL=gpt-4o
TARGET_BASE_URL=https://your-resource.openai.azure.com
```

### Supported Providers

| Provider | `TARGET_PROVIDER` | Notes |
|----------|------------------|-------|
| OpenAI | `openai` | Direct OpenAI API |
| Anthropic / Claude | `anthropic` | Claude Sonnet 4, Opus 4, Haiku 4.5 |
| Azure OpenAI | `azure` | Classic Azure OpenAI Service |
| Azure AI Foundry | `azure_foundry` | Any Foundry model: GPT, Llama, Mistral, Phi, DeepSeek |
| Google Gemini | `google` | Gemini 2.0 Flash, Pro, etc. |
| Ollama (local) | `ollama` | Any local model via Ollama |

### Separate Target and Judge Models

Test one model while a different (stronger) model judges the responses:

```env
# Test Llama, judge with GPT-4o
TARGET_PROVIDER=azure_foundry
TARGET_MODEL=Llama-3.1-70B

JUDGE_PROVIDER=azure
JUDGE_MODEL=gpt-4o
JUDGE_API_KEY=your-azure-key
JUDGE_BASE_URL=https://your-resource.openai.azure.com
```

### System Prompt Source

```env
TARGET_SYSTEM_PROMPT=local           # Use prompt from prompts/ in codebase (default)
TARGET_SYSTEM_PROMPT=none            # No prompt — test deployed model's own prompt
TARGET_SYSTEM_PROMPT=file:C:/path.txt  # Load from external file
```

## Available Roles

### Clinical Trials (DCRI)

| Role | Domain | Tests | Criteria Source |
|------|--------|-------|----------------|
| `clinical_data_engineer` | EDC ingestion, SDTM/ADaM, data quality, SAS-to-Spark | 12 | FDA 21 CFR Part 11, CDISC SDTM/ADaM IG, ICH GCP, HIPAA |
| `clinical_reporting_engineer` | TLFs, DSMB reports, eCTD submissions, safety signals | 10 | SAP, double-programming, Pinnacle 21, ICH E2B(R3) |
| `clinical_security_engineer` | PHI protection, unblinding, encryption, GDPR transfers | 10 | HIPAA Safe Harbor, GDPR Art. 44-49, NIST 800-53 |

### Data Platform

| Role | Domain | Tests |
|------|--------|-------|
| `azure_data_engineer` | ADF, Synapse, Databricks, ADLS Gen2, streaming | 12 |
| `fabric_data_engineer` | Lakehouses, Warehouses, OneLake, Spark, Dataflows Gen2 | 10 |
| `sql_report_engineer` | SSRS, paginated reports, T-SQL, Report Builder | 10 |
| `power_bi_engineer` | DAX, Power Query, data modeling, RLS, deployment | 10 |

## How Evaluation Works

```
app.py (Web Dashboard) or run_evaluation.py (CLI)
    |
    prompts/registry.py          # Auto-discovers role prompts
    |
    evaluators/llm_client.py     # BYOK: any provider via OpenAI/Anthropic/Google SDK
    |
    evaluators/deepeval_adapter.py  # GEval metrics per criterion
    |
    evaluators/scorer.py         # Orchestrates: model -> judge -> report + perf metrics
    |
    reports/html_report.py       # HTML report with two sections
    |
    results_db.py                # SQLite history tracking
```

### Evaluation Pipeline

1. Each role has a **system prompt** and a **test suite** (10-12 test cases, 5 criteria each)
2. The **target model** generates responses using the system prompt
3. **DeepEval GEval** (LLM-as-judge with chain-of-thought) scores each criterion 0.0-1.0
4. **Performance metrics** captured: latency, tokens, cost per test case
5. Scores weighted and aggregated into a letter grade (A+ through D)
6. **Recommendation engine** identifies weak areas and suggests prompt improvements
7. **HTML report** generated with two sections:
   - **Section 1: Prompt Quality** — grade, category radar/bar charts, test drill-down, recommendations
   - **Section 2: Performance** — latency (avg/p95/min/max), tokens, cost, latency chart
8. Run logged to **SQLite history** for tracking over time

### A/B Comparison

Compare any two configurations side-by-side:
- Same model, different prompts (weak baseline vs full prompt)
- Different models, same prompt (GPT-4o vs Claude Sonnet)
- Different everything (GPT-4o/local prompt vs Llama/no prompt)

## Adding a New Role

1. Create `prompts/your_role.py` exporting `SYSTEM_PROMPT` and `PROMPT_METADATA`
2. Create `test_suites/your_role_tests.py` exporting `TEST_CASES` and `CATEGORIES`
3. (Optional) Create `prompts/your_role_v1_weak.py` for A/B comparison baseline
4. (Optional) Add demo responses in `evaluators/demo_responses.py`

The registry auto-discovers new roles — no other changes needed.

## Scoring System

| Grade | Range | Grade | Range |
|-------|-------|-------|-------|
| A+ | 95-100% | B- | 70-74% |
| A | 90-94% | C+ | 65-69% |
| A- | 85-89% | C | 60-64% |
| B+ | 80-84% | D | <60% |
| B | 75-79% | | |

Each test case has a **weight** (1-3x) reflecting importance. Final score is a weighted average.

## Project Structure

```
AI Evaluation/
├── app.py                         # Web dashboard (Flask)
├── run_evaluation.py              # CLI: single evaluation
├── run_comparison.py              # CLI: A/B comparison
├── config.py                      # BYOK configuration + .env loader
├── results_db.py                  # SQLite history tracking
├── requirements.txt
├── .env                           # Your API keys (git-ignored)
├── .env.example                   # Configuration template
├── prompts/
│   ├── registry.py                # Auto-discovers role prompts
│   ├── clinical_data_engineer.py  # DCRI clinical trials pipeline
│   ├── clinical_reporting_engineer.py
│   ├── clinical_security_engineer.py
│   ├── azure_data_engineer.py
│   ├── fabric_data_engineer.py
│   ├── power_bi_engineer.py
│   └── sql_report_engineer.py
├── test_suites/
│   ├── clinical_data_engineer_tests.py   # 12 tests, FDA/CDISC/HIPAA criteria
│   ├── clinical_reporting_engineer_tests.py
│   ├── clinical_security_engineer_tests.py
│   ├── azure_data_engineer_tests.py
│   └── ...
├── evaluators/
│   ├── llm_client.py              # BYOK: OpenAI, Anthropic, Azure, Google, Ollama
│   ├── deepeval_adapter.py        # DeepEval GEval bridge
│   ├── scorer.py                  # Evaluation engine + performance metrics
│   ├── recommender.py             # Prompt improvement suggestions
│   └── demo_responses.py          # Pre-built responses for demo mode
├── reports/
│   ├── html_report.py             # Single evaluation HTML report
│   └── comparison_report.py       # A/B comparison HTML report
└── docs/
    └── DCRI_Clinical_Trials_Test_Suites.md  # Source criteria document
```
