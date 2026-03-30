"""
Test suite for evaluating the Azure Data Engineer system prompt.

Each test case defines:
  - id: unique identifier
  - category: grouping for scoring
  - question: the user message to send
  - criteria: list of things to check in the response (graded 0-1 each)
  - weight: importance multiplier (1-3)
"""

TEST_CASES = [
    # ── Accuracy & Depth ──────────────────────────────────────────────
    {
        "id": "ACC-01",
        "category": "Accuracy & Depth",
        "question": (
            "What is the difference between a Synapse dedicated SQL pool "
            "and a serverless SQL pool? When should I use each?"
        ),
        "criteria": [
            "Correctly distinguishes provisioned (dedicated) vs on-demand (serverless) models",
            "Mentions cost model differences (reserved vs per-TB scanned)",
            "Recommends dedicated for predictable, high-concurrency workloads",
            "Recommends serverless for ad-hoc exploration and external tables",
            "Mentions pause/resume capability for dedicated pools",
        ],
        "weight": 3,
    },
    {
        "id": "ACC-02",
        "category": "Accuracy & Depth",
        "question": (
            "How do I implement slowly changing dimensions (SCD Type 2) "
            "in Azure Databricks using Delta Lake?"
        ),
        "criteria": [
            "Describes SCD Type 2 concept (history tracking with effective dates)",
            "Uses Delta Lake MERGE statement",
            "Provides a PySpark or SQL code example",
            "Mentions surrogate keys or hash-based change detection",
            "References Delta Lake features like time travel as a benefit",
        ],
        "weight": 3,
    },
    {
        "id": "ACC-03",
        "category": "Accuracy & Depth",
        "question": "Explain the medallion architecture and how to implement it on Azure.",
        "criteria": [
            "Defines Bronze (raw), Silver (cleansed), Gold (aggregated) layers",
            "Maps layers to Azure services (ADLS Gen2 + Databricks/Synapse)",
            "Mentions data quality enforcement between layers",
            "Discusses partitioning strategies for each layer",
            "Mentions Delta Lake or Lakehouse format",
        ],
        "weight": 2,
    },
    # ── Security ──────────────────────────────────────────────────────
    {
        "id": "SEC-01",
        "category": "Security",
        "question": (
            "How should I securely connect Azure Data Factory to an "
            "on-premises SQL Server?"
        ),
        "criteria": [
            "Recommends Self-hosted Integration Runtime",
            "Mentions private endpoints or VPN/ExpressRoute",
            "Recommends storing credentials in Azure Key Vault",
            "Suggests managed identity where possible",
            "Warns against storing passwords in plain text in linked services",
        ],
        "weight": 3,
    },
    {
        "id": "SEC-02",
        "category": "Security",
        "question": "What are best practices for securing Azure Data Lake Storage Gen2?",
        "criteria": [
            "Mentions RBAC (role-based access control) at management plane",
            "Mentions ACLs (access control lists) at data plane",
            "Recommends private endpoints",
            "Mentions encryption at rest and in transit",
            "Suggests disabling public network access",
        ],
        "weight": 2,
    },
    # ── Cost Optimization ─────────────────────────────────────────────
    {
        "id": "COST-01",
        "category": "Cost Optimization",
        "question": (
            "Our Azure Databricks costs have spiked. What are the top "
            "strategies to reduce spend?"
        ),
        "criteria": [
            "Recommends autoscaling clusters with appropriate min/max",
            "Mentions spot/preemptible instances for fault-tolerant jobs",
            "Suggests right-sizing VM SKUs based on workload profiling",
            "Recommends cluster policies to enforce guardrails",
            "Mentions auto-termination for idle clusters",
        ],
        "weight": 2,
    },
    # ── Code Quality ──────────────────────────────────────────────────
    {
        "id": "CODE-01",
        "category": "Code Quality",
        "question": (
            "Write a PySpark script that reads JSON files from ADLS Gen2, "
            "flattens nested arrays, and writes to Delta format partitioned "
            "by date."
        ),
        "criteria": [
            "Uses spark.read.json or similar correct API",
            "Uses explode() or posexplode() for flattening arrays",
            "Writes in Delta format (.write.format('delta'))",
            "Partitions by a date column (.partitionBy(...))",
            "Code is syntactically valid PySpark",
        ],
        "weight": 3,
    },
    {
        "id": "CODE-02",
        "category": "Code Quality",
        "question": (
            "Give me an ARM template or Bicep file to deploy an Azure Data "
            "Factory with a managed virtual network."
        ),
        "criteria": [
            "Provides valid ARM JSON or Bicep syntax",
            "Includes Microsoft.DataFactory/factories resource type",
            "Configures managed virtual network (managedVirtualNetwork property)",
            "Sets appropriate API version",
            "Includes managed private endpoints or explains how to add them",
        ],
        "weight": 2,
    },
    # ── Guardrails & Constraints ──────────────────────────────────────
    {
        "id": "GUARD-01",
        "category": "Guardrails",
        "question": "Should I use HDInsight or Azure Data Lake Storage Gen1 for my new project?",
        "criteria": [
            "Discourages ADLS Gen1 as it is deprecated / end-of-life",
            "Recommends ADLS Gen2 as the replacement",
            "Suggests Databricks or Synapse Spark over HDInsight for most new projects",
            "Explains why (managed service, better integration, lower ops overhead)",
            "Does not blindly recommend the deprecated services",
        ],
        "weight": 3,
    },
    {
        "id": "GUARD-02",
        "category": "Guardrails",
        "question": "How should I set up a data pipeline on AWS Glue?",
        "criteria": [
            "Stays within Azure scope or politely redirects to Azure equivalents",
            "Does not provide a full AWS Glue tutorial",
            "May offer a brief comparison but focuses on Azure alternatives (ADF, Synapse)",
            "Suggests Azure Data Factory or Synapse Pipelines as the Azure equivalent",
            "Maintains the Azure Data Engineer persona",
        ],
        "weight": 2,
    },
    # ── Real-Time & Streaming ─────────────────────────────────────────
    {
        "id": "STREAM-01",
        "category": "Real-Time & Streaming",
        "question": (
            "Design a real-time data pipeline that ingests IoT sensor data "
            "at 100K events/sec and makes it queryable within 5 minutes."
        ),
        "criteria": [
            "Recommends Azure Event Hubs (or IoT Hub) for ingestion",
            "Suggests a stream processing layer (Stream Analytics, Databricks Structured Streaming, or Fabric Eventstream)",
            "Specifies a serving layer (Synapse, Cosmos DB, or ADX/Data Explorer)",
            "Addresses partitioning for throughput (Event Hubs partitions)",
            "Mentions monitoring / alerting for pipeline health",
        ],
        "weight": 2,
    },
    # ── Ambiguity Handling ────────────────────────────────────────────
    {
        "id": "AMB-01",
        "category": "Ambiguity Handling",
        "question": "How do I load data?",
        "criteria": [
            "Asks clarifying questions (source, destination, format, volume)",
            "Does not assume a single interpretation",
            "May offer a few common scenarios to help the user narrow down",
            "Keeps the response helpful despite the vague question",
            "Demonstrates the 'clarify assumptions' constraint from the prompt",
        ],
        "weight": 2,
    },
]

CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))
