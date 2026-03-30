"""
Test suite for evaluating the SQL Report Engineer system prompt.

Each test case defines:
  - id: unique identifier
  - category: grouping for scoring
  - question: the user message to send
  - criteria: list of things to check in the response (graded 0-1 each)
  - weight: importance multiplier (1-3)
"""

TEST_CASES = [
    # ── Report Design ────────────────────────────────────────────────
    {
        "id": "RD-01",
        "category": "Report Design",
        "question": (
            "I need to build a paginated invoice report that prints cleanly "
            "on letter-size paper with a company logo header, line-item table, "
            "and a page footer showing totals carried forward. How should I "
            "design this in Report Builder?"
        ),
        "criteria": [
            "Recommends a table or list data region for line items",
            "Explains header/footer configuration with page-break considerations",
            "Mentions using expressions like Globals!PageNumber for page numbering",
            "Describes a running total or RunningValue expression for carried-forward totals",
            "Addresses image embedding for the company logo (external or embedded)",
        ],
        "weight": 3,
    },
    {
        "id": "RD-02",
        "category": "Report Design",
        "question": (
            "When should I use a subreport versus a drillthrough report? "
            "What are the performance implications?"
        ),
        "criteria": [
            "Explains that subreports are embedded inline and render with the parent",
            "Explains that drillthrough reports open as a separate navigated report",
            "Warns that subreports execute a separate query per instance and can be slow",
            "Recommends drillthrough for detail-on-demand scenarios to reduce load",
            "Mentions parameter passing differences between the two approaches",
        ],
        "weight": 2,
    },
    # ── T-SQL for Reporting ──────────────────────────────────────────
    {
        "id": "TSQL-01",
        "category": "T-SQL for Reporting",
        "question": (
            "Write a stored procedure that returns a monthly sales summary "
            "with running totals and a rank by revenue within each region, "
            "filtered by a date range."
        ),
        "criteria": [
            "Uses window functions (SUM OVER for running total, RANK or DENSE_RANK for ranking)",
            "Accepts date-range parameters (@StartDate, @EndDate)",
            "Groups by month and region appropriately",
            "Provides syntactically valid T-SQL",
            "Uses explicit JOIN syntax and meaningful aliases",
        ],
        "weight": 3,
    },
    {
        "id": "TSQL-02",
        "category": "T-SQL for Reporting",
        "question": (
            "How do I handle a multi-value parameter from SSRS in a stored "
            "procedure? The user can select multiple product categories."
        ),
        "criteria": [
            "Explains that SSRS sends multi-value parameters as comma-delimited strings",
            "Provides a STRING_SPLIT or table-valued parameter (TVP) approach",
            "Shows how to use the parsed values in a WHERE ... IN clause",
            "Mentions the SSRS expression =Join(Parameters!Param.Value, \",\") if needed",
            "Warns about SQL injection risks with dynamic SQL approaches",
        ],
        "weight": 3,
    },
    # ── Performance Optimization ─────────────────────────────────────
    {
        "id": "PERF-01",
        "category": "Performance Optimization",
        "question": (
            "Our SSRS report takes over 90 seconds to render. The underlying "
            "query returns 50,000 rows. What steps should I take to diagnose "
            "and fix this?"
        ),
        "criteria": [
            "Recommends checking the SSRS ExecutionLog3 view to separate data retrieval vs rendering time",
            "Suggests analyzing the query execution plan for missing indexes or table scans",
            "Recommends reducing the row count or pre-aggregating data where possible",
            "Mentions execution snapshots or cached report instances for repeated access",
            "Addresses report rendering complexity (e.g., too many subreports, toggle visibility overhead)",
        ],
        "weight": 3,
    },
    # ── Parameterization ─────────────────────────────────────────────
    {
        "id": "PARAM-01",
        "category": "Parameterization",
        "question": (
            "How do I set up cascading parameters in SSRS so that selecting a "
            "Country populates the State/Province dropdown, which then populates "
            "the City dropdown?"
        ),
        "criteria": [
            "Describes creating separate datasets for each parameter level",
            "Explains that each child dataset filters by the parent parameter value",
            "Mentions the parameter dependency order matters in the report parameter list",
            "Notes that default values should be set carefully to avoid null-reference issues",
            "Mentions the user experience impact of each cascade triggering a postback",
        ],
        "weight": 2,
    },
    # ── Security & Distribution ──────────────────────────────────────
    {
        "id": "SECDIST-01",
        "category": "Security & Distribution",
        "question": (
            "How do I set up a data-driven subscription in SSRS that emails "
            "different regional managers their own region's PDF report each Monday?"
        ),
        "criteria": [
            "Explains data-driven subscriptions use a query to supply recipient and parameter values",
            "Describes the delivery table/query with columns for email address and region parameter",
            "Mentions scheduling configuration for weekly Monday delivery",
            "Specifies PDF as a rendering format option in the subscription settings",
            "Notes that the SSRS service account needs SMTP relay permissions",
        ],
        "weight": 2,
    },
    {
        "id": "SECDIST-02",
        "category": "Security & Distribution",
        "question": (
            "How should I implement row-level security so that regional "
            "managers only see their own region's data in a shared SSRS report?"
        ),
        "criteria": [
            "Recommends implementing RLS in the SQL query/view layer, not in the report",
            "Suggests using the User!UserID built-in field to pass the current user to the query",
            "Describes a mapping table that links users or roles to regions",
            "Provides a T-SQL example joining the mapping table to filter results",
            "Warns against relying solely on report-level parameter restrictions for security",
        ],
        "weight": 3,
    },
    # ── Guardrails ───────────────────────────────────────────────────
    {
        "id": "GUARD-01",
        "category": "Guardrails",
        "question": (
            "Should I build this dashboard with live KPI tiles, slicers, "
            "and cross-filtering in SSRS paginated reports?"
        ),
        "criteria": [
            "Clarifies that SSRS paginated reports are not designed for interactive dashboards",
            "Recommends Power BI interactive reports for slicers and cross-filtering",
            "Explains when paginated reports are the right choice (print-ready, pixel-perfect, large exports)",
            "Does not blindly attempt to replicate Power BI interactivity in SSRS",
            "Offers a hybrid approach if appropriate (Power BI dashboard with drillthrough to paginated detail)",
        ],
        "weight": 2,
    },
    # ── Ambiguity Handling ───────────────────────────────────────────
    {
        "id": "AMB-01",
        "category": "Ambiguity Handling",
        "question": "My report is slow. How do I fix it?",
        "criteria": [
            "Asks clarifying questions (SSRS version, report type, data volume, symptoms)",
            "Does not assume a single root cause without more information",
            "May offer common troubleshooting areas to help the user narrow down the issue",
            "Keeps the response helpful despite the vague question",
            "Demonstrates the 'clarify assumptions' constraint from the system prompt",
        ],
        "weight": 2,
    },
]

CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))
