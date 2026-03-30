"""
Test suite for evaluating the Fabric Data Engineer system prompt.

Each test case defines:
  - id: unique identifier
  - category: grouping for scoring
  - question: the user message to send
  - criteria: list of things to check in the response (graded 0-1 each)
  - weight: importance multiplier (1-3)
"""

TEST_CASES = [
    # ── Architecture ─────────────────────────────────────────────────
    {
        "id": "ARCH-01",
        "category": "Architecture",
        "question": (
            "What is the difference between a Fabric Lakehouse and a Fabric "
            "Warehouse? When should I use each?"
        ),
        "criteria": [
            "Correctly distinguishes Lakehouse (Delta + Spark + SQL endpoint) from Warehouse (T-SQL managed engine)",
            "Mentions that Lakehouse supports both structured and unstructured data while Warehouse is structured/relational only",
            "Recommends Lakehouse for data engineering/Spark workloads and Warehouse for SQL-centric BI workloads",
            "Explains that both store data in OneLake as Delta-Parquet",
            "Mentions the SQL analytics endpoint on Lakehouse as a read-only T-SQL surface",
        ],
        "weight": 3,
    },
    {
        "id": "ARCH-02",
        "category": "Architecture",
        "question": (
            "How does OneLake work, and how do Shortcuts enable cross-domain "
            "data access without duplication?"
        ),
        "criteria": [
            "Describes OneLake as Fabric's unified data lake built on ADLS Gen2",
            "Explains the hierarchical namespace: tenant / workspace / item / tables and files",
            "Describes Shortcuts as virtual pointers enabling zero-copy access",
            "Mentions Shortcut targets: OneLake, ADLS Gen2, S3, and GCS",
            "Highlights the benefit of avoiding data duplication across workspaces or domains",
        ],
        "weight": 3,
    },
    # ── Data Transformation ──────────────────────────────────────────
    {
        "id": "TRANS-01",
        "category": "Data Transformation",
        "question": (
            "Write a PySpark notebook that reads raw CSV files from the "
            "Lakehouse Files section, cleans the data, and writes it as a "
            "Delta table to the Lakehouse Tables section."
        ),
        "criteria": [
            "Uses spark.read.csv or similar correct Spark API for reading CSVs",
            "References Fabric Lakehouse paths (e.g., Files/ and Tables/ or abfss:// OneLake paths)",
            "Includes data cleaning steps (null handling, type casting, deduplication, or filtering)",
            "Writes output in Delta format using .write.format('delta') or saveAsTable()",
            "Code is syntactically valid PySpark",
        ],
        "weight": 3,
    },
    {
        "id": "TRANS-02",
        "category": "Data Transformation",
        "question": (
            "When should I use Dataflows Gen2 versus a Spark notebook for "
            "data transformation in Fabric?"
        ),
        "criteria": [
            "Recommends Dataflows Gen2 for low-code/no-code and citizen-developer scenarios",
            "Recommends Spark notebooks for complex transformations, large-scale data, and custom logic",
            "Mentions the 300+ connectors available in Dataflows Gen2 via Power Query",
            "Discusses CU consumption differences between the two approaches",
            "Mentions staging Lakehouse support in Dataflows Gen2 for better performance",
        ],
        "weight": 2,
    },
    # ── Security & Governance ────────────────────────────────────────
    {
        "id": "SEC-01",
        "category": "Security & Governance",
        "question": (
            "How do I implement fine-grained access control in a Fabric "
            "Lakehouse so that different teams can only see their own data?"
        ),
        "criteria": [
            "Explains workspace roles (Admin, Member, Contributor, Viewer) for coarse-grained control",
            "Describes OneLake data access roles for folder-level security within a Lakehouse",
            "Mentions RLS on the SQL analytics endpoint or semantic model for row-level filtering",
            "Recommends a least-privilege approach",
            "Mentions Purview or sensitivity labels for governance and data classification",
        ],
        "weight": 3,
    },
    # ── Cost Management ──────────────────────────────────────────────
    {
        "id": "COST-01",
        "category": "Cost Management",
        "question": (
            "Our Fabric capacity CU usage is spiking. What strategies can "
            "we use to reduce costs?"
        ),
        "criteria": [
            "Recommends using the Capacity Metrics App to identify heavy workloads and items",
            "Suggests pausing capacity during non-business hours to stop compute billing",
            "Mentions V-Order optimization for efficient Delta reads that reduce CU consumption",
            "Recommends right-sizing the capacity SKU based on actual utilization data",
            "Suggests optimizing Spark jobs (reduce shuffles, partition wisely, cache appropriately)",
        ],
        "weight": 2,
    },
    # ── Real-Time Analytics ──────────────────────────────────────────
    {
        "id": "RT-01",
        "category": "Real-Time Analytics",
        "question": (
            "Design a real-time analytics solution in Fabric that ingests "
            "clickstream events and makes them queryable within seconds."
        ),
        "criteria": [
            "Recommends Eventstream for real-time event ingestion",
            "Routes data to an Eventhouse (KQL Database) for low-latency querying",
            "Mentions KQL as the query language for the Eventhouse",
            "Suggests in-flight transformations in Eventstream (filter, manage fields) if needed",
            "Discusses Real-Time Dashboard or Power BI DirectQuery for visualization",
        ],
        "weight": 2,
    },
    # ── Guardrails ───────────────────────────────────────────────────
    {
        "id": "GUARD-01",
        "category": "Guardrails",
        "question": (
            "Should I use standalone Azure Data Factory and Azure Synapse "
            "Analytics instead of Microsoft Fabric for my new data platform?"
        ),
        "criteria": [
            "Redirects toward Fabric-native equivalents (Fabric Pipelines, Lakehouse, Warehouse)",
            "Acknowledges that standalone ADF/Synapse still exist but explains Fabric's unified approach",
            "Mentions benefits of Fabric: single OneLake, unified governance, shared capacity model",
            "Does not blindly recommend legacy standalone services for greenfield projects",
            "Provides a balanced view noting cases where standalone services may still be appropriate",
        ],
        "weight": 3,
    },
    {
        "id": "GUARD-02",
        "category": "Guardrails",
        "question": "How do I set up a data lakehouse on AWS using Glue and Athena?",
        "criteria": [
            "Stays within Fabric scope or politely redirects to Fabric equivalents",
            "Does not provide a full AWS tutorial",
            "Suggests Fabric Lakehouse as the equivalent approach",
            "May offer a brief comparison but keeps focus on Fabric",
            "Maintains the Fabric Data Engineer persona",
        ],
        "weight": 2,
    },
    # ── Ambiguity Handling ───────────────────────────────────────────
    {
        "id": "AMB-01",
        "category": "Ambiguity Handling",
        "question": "How do I load data into Fabric?",
        "criteria": [
            "Asks clarifying questions (source type, volume, batch vs real-time, destination item)",
            "Does not assume a single interpretation",
            "May offer common scenarios (Pipelines for batch, Eventstream for streaming, Dataflows Gen2 for low-code)",
            "Keeps the response helpful despite the vague question",
            "Demonstrates the 'clarify assumptions' constraint from the prompt",
        ],
        "weight": 2,
    },
]

CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))
