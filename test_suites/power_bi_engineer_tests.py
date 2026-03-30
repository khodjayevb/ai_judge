"""
Test suite for evaluating the Power BI Engineer system prompt.

Each test case defines:
  - id: unique identifier
  - category: grouping for scoring
  - question: the user message to send
  - criteria: list of things to check in the response (graded 0-1 each)
  - weight: importance multiplier (1-3)
"""

TEST_CASES = [
    # ── DAX & Measures ───────────────────────────────────────────────
    {
        "id": "DAX-01",
        "category": "DAX & Measures",
        "question": (
            "What is the difference between CALCULATE and CALCULATETABLE in DAX? "
            "When should I use CALCULATE with context transition versus an iterator "
            "like SUMX?"
        ),
        "criteria": [
            "Explains that CALCULATE returns a scalar while CALCULATETABLE returns a table",
            "Describes context transition — row context converted to filter context",
            "Explains when SUMX is preferred (row-by-row evaluation with different granularity)",
            "Mentions REMOVEFILTERS or ALL for clearing filter context inside CALCULATE",
            "Provides a concrete DAX example demonstrating the difference",
        ],
        "weight": 3,
    },
    {
        "id": "DAX-02",
        "category": "DAX & Measures",
        "question": (
            "Write a DAX measure that calculates year-over-year growth percentage, "
            "handling the case where the prior year value is zero or blank."
        ),
        "criteria": [
            "Uses SAMEPERIODLASTYEAR, DATEADD, or PARALLELPERIOD for prior year",
            "Handles division by zero or blank with IF / DIVIDE",
            "Returns a percentage (formats or divides correctly)",
            "Uses VAR / RETURN pattern for readability",
            "Recommends a proper Date table marked as Date table",
        ],
        "weight": 3,
    },
    # ── Data Modeling ────────────────────────────────────────────────
    {
        "id": "MODEL-01",
        "category": "Data Modeling",
        "question": (
            "I have a flat table with 50 columns and 20 million rows. Reports are "
            "slow. How should I restructure the model?"
        ),
        "criteria": [
            "Recommends splitting into a star schema with fact and dimension tables",
            "Explains benefits of star schema for Power BI (compression, performance, clarity)",
            "Advises removing high-cardinality columns or moving them to dimensions",
            "Mentions disabling Auto Date/Time if not already done",
            "Suggests using Performance Analyzer or VertiPaq Analyzer to identify bottlenecks",
        ],
        "weight": 3,
    },
    # ── Security ─────────────────────────────────────────────────────
    {
        "id": "SEC-01",
        "category": "Security",
        "question": (
            "How do I implement dynamic Row-Level Security so that sales managers "
            "only see data for their own region, and the VP of Sales sees all regions?"
        ),
        "criteria": [
            "Uses USERPRINCIPALNAME() or USERNAME() in the RLS filter expression",
            "Describes creating a security mapping table (user-to-region)",
            "Explains how the VP role can use an 'all regions' flag or a separate role with no filter",
            "Mentions testing RLS using 'View as Roles' in Power BI Desktop and Service",
            "Warns about configuring role membership in the Power BI Service after publishing",
        ],
        "weight": 3,
    },
    # ── Performance ──────────────────────────────────────────────────
    {
        "id": "PERF-01",
        "category": "Performance",
        "question": (
            "Our DirectQuery report over Azure SQL is very slow. What are the top "
            "strategies to improve performance without switching to Import mode?"
        ),
        "criteria": [
            "Recommends aggregation tables (automatic or user-defined) to reduce DQ queries",
            "Suggests dual storage mode for dimensions to avoid cross-source joins",
            "Mentions proper indexing and query tuning on the Azure SQL source",
            "Advises reducing visuals per page and avoiding complex DAX over DirectQuery",
            "Mentions composite models as a way to combine Import and DirectQuery",
        ],
        "weight": 3,
    },
    # ── Deployment & CI/CD ───────────────────────────────────────────
    {
        "id": "CICD-01",
        "category": "Deployment & CI/CD",
        "question": (
            "How do I set up a CI/CD pipeline for Power BI reports using Azure DevOps "
            "and deployment pipelines?"
        ),
        "criteria": [
            "Describes Power BI deployment pipelines (Dev / Test / Prod stages)",
            "Mentions Git integration with Azure DevOps or GitHub for source control",
            "Explains deployment rules for overriding parameters and data sources per stage",
            "References Power BI REST APIs or Fabric REST APIs for automation",
            "Mentions Tabular Editor or pbi-tools for advanced CI/CD scenarios",
        ],
        "weight": 2,
    },
    # ── Power Query ──────────────────────────────────────────────────
    {
        "id": "PQ-01",
        "category": "Power Query",
        "question": (
            "Some of my Power Query transformations are very slow. How do I check "
            "if query folding is happening and fix steps that break it?"
        ),
        "criteria": [
            "Explains query folding — pushing transformations to the data source",
            "Describes how to check folding (right-click step > 'View Native Query')",
            "Lists common steps that break folding (custom columns with M logic, merges with non-foldable sources)",
            "Recommends reordering steps to keep foldable operations early",
            "Mentions the query diagnostics tool for detailed profiling",
        ],
        "weight": 2,
    },
    # ── Guardrails ───────────────────────────────────────────────────
    {
        "id": "GUARD-01",
        "category": "Guardrails",
        "question": "How do I create a calculated column that shows the running total of sales?",
        "criteria": [
            "Discourages using a calculated column for a running total (context issues, storage cost)",
            "Recommends a measure instead for dynamic evaluation in visual context",
            "Provides a DAX measure example for running total (e.g., using CALCULATE + FILTER with date logic)",
            "Explains why measures are preferred over calculated columns for aggregations",
            "Does not blindly provide a calculated column solution",
        ],
        "weight": 2,
    },
    {
        "id": "GUARD-02",
        "category": "Guardrails",
        "question": "How should I build this dashboard in Tableau?",
        "criteria": [
            "Stays within Power BI scope or politely redirects to Power BI equivalents",
            "Does not provide a full Tableau tutorial",
            "May offer a brief comparison but focuses on Power BI capabilities",
            "Suggests equivalent Power BI features for common dashboard patterns",
            "Maintains the Power BI Engineer persona",
        ],
        "weight": 2,
    },
    # ── Ambiguity Handling ───────────────────────────────────────────
    {
        "id": "AMB-01",
        "category": "Ambiguity Handling",
        "question": "My report is slow. How do I fix it?",
        "criteria": [
            "Asks clarifying questions (storage mode, data volume, number of visuals, DAX complexity)",
            "Does not assume a single root cause",
            "May offer a structured troubleshooting checklist covering common causes",
            "Mentions Performance Analyzer as a starting diagnostic tool",
            "Demonstrates the 'clarify assumptions' constraint from the prompt",
        ],
        "weight": 2,
    },
]

CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))
