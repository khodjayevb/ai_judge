"""
Test suite for Azure Data Architect.

Covers: platform architecture, governance, security, cost, migration,
high availability, data mesh, and Fabric architecture decisions.
"""

TEST_CASES = [
    # ── Platform Architecture ─────────────────────────────────────────
    {
        "id": "ARCH-01",
        "category": "Platform Architecture",
        "question": (
            "Design an enterprise data platform architecture on Azure for a "
            "large retail company with 500+ stores, real-time POS data, "
            "batch supply chain feeds, and a central analytics team."
        ),
        "criteria": [
            "Proposes a layered architecture (ingestion, storage, processing, serving) with specific Azure services",
            "Includes both real-time (Event Hubs / Stream Analytics) and batch (ADF / Databricks) paths",
            "Recommends ADLS Gen2 or OneLake as the central storage layer with medallion architecture",
            "Addresses multi-team access with workspace isolation and RBAC",
            "Considers scalability for 500+ store data volumes with partitioning strategy",
        ],
        "weight": 3,
    },
    {
        "id": "ARCH-02",
        "category": "Platform Architecture",
        "question": (
            "What are the key differences between building a data platform on "
            "standalone Azure services (ADLS + Databricks + Synapse + Purview) "
            "versus using Microsoft Fabric? When should we choose each?"
        ),
        "criteria": [
            "Compares standalone vs Fabric on: cost model, governance, flexibility, and operational overhead",
            "Mentions Fabric's unified capacity billing vs separate service billing for standalone",
            "Notes that standalone offers more granular control and multi-cloud portability",
            "Recommends Fabric for teams wanting integrated experience with lower ops burden",
            "Recommends standalone for complex multi-cloud, highly customized, or regulated environments",
        ],
        "weight": 3,
    },
    # ── Data Governance ───────────────────────────────────────────────
    {
        "id": "GOV-01",
        "category": "Data Governance",
        "question": (
            "How should we implement data governance using Microsoft Purview "
            "across our Azure data platform? We have 200+ datasets across "
            "5 business domains."
        ),
        "criteria": [
            "Recommends Purview Data Catalog for asset discovery and metadata management",
            "Describes data lineage tracking from source to consumption",
            "Mentions sensitivity labels and data classification for PII/confidential data",
            "Recommends a business glossary with domain-specific terms owned by data stewards",
            "Addresses access policies and integration with Azure RBAC / Purview policies",
        ],
        "weight": 3,
    },
    {
        "id": "GOV-02",
        "category": "Data Governance",
        "question": (
            "Our organization wants to implement a data mesh architecture. "
            "How do we design this on Azure with federated governance?"
        ),
        "criteria": [
            "Defines data mesh principles: domain ownership, data as a product, self-serve platform, federated governance",
            "Maps domains to Azure subscriptions or Fabric workspaces with clear ownership",
            "Recommends Purview as the federated governance layer across domains",
            "Describes data product contracts (schema, SLAs, quality metrics)",
            "Addresses the platform team's role in providing self-serve infrastructure (templates, policies)",
        ],
        "weight": 2,
    },
    # ── Security Architecture ─────────────────────────────────────────
    {
        "id": "SEC-01",
        "category": "Security Architecture",
        "question": (
            "Design a Zero Trust security architecture for our Azure data "
            "platform that handles PII data from EU and US customers."
        ),
        "criteria": [
            "Applies Zero Trust principles: verify explicitly, least privilege, assume breach",
            "Recommends private endpoints for all PaaS services (no public access)",
            "Specifies managed identities for service-to-service authentication (no keys/passwords)",
            "Addresses data encryption: CMK at rest, TLS 1.2+ in transit, Azure Key Vault for key management",
            "Mentions EU data residency requirements and Azure region pinning for GDPR compliance",
        ],
        "weight": 3,
    },
    # ── Cost & FinOps ─────────────────────────────────────────────────
    {
        "id": "COST-01",
        "category": "Cost & FinOps",
        "question": (
            "Our Azure data platform costs $150K/month and growing. Design "
            "a FinOps strategy to optimize and govern data platform spending."
        ),
        "criteria": [
            "Recommends Azure Cost Management with budgets and alerts per subscription/resource group",
            "Mentions reserved capacity for predictable workloads (Synapse, Databricks, Cosmos DB)",
            "Suggests auto-pause/auto-scale for non-production and bursty workloads",
            "Proposes tagging standards for cost allocation by domain, project, and environment",
            "Recommends regular cost reviews with showback/chargeback to business domains",
        ],
        "weight": 2,
    },
    # ── Migration ─────────────────────────────────────────────────────
    {
        "id": "MIG-01",
        "category": "Migration",
        "question": (
            "We need to migrate a 50TB Teradata data warehouse to Azure. "
            "What architecture and migration approach do you recommend?"
        ),
        "criteria": [
            "Recommends a phased migration approach (assess, migrate, optimize) rather than big-bang",
            "Evaluates target options: Synapse dedicated pool, Databricks Lakehouse, or Fabric Warehouse",
            "Addresses schema/DDL conversion from Teradata to target platform",
            "Mentions Azure Database Migration Service or third-party tools (e.g., Striim, Qlik) for data movement",
            "Considers parallel running period for validation before cutover",
        ],
        "weight": 2,
    },
    # ── High Availability & DR ────────────────────────────────────────
    {
        "id": "HA-01",
        "category": "High Availability",
        "question": (
            "Design a disaster recovery strategy for our Azure data platform "
            "with RPO of 1 hour and RTO of 4 hours."
        ),
        "criteria": [
            "Specifies RPO/RTO targets and maps them to Azure replication capabilities",
            "Recommends GRS (Geo-Redundant Storage) or GZRS for ADLS Gen2",
            "Addresses Databricks/Synapse workspace recovery (ARM templates, Terraform, Git-backed configs)",
            "Includes automated failover testing and runbook documentation",
            "Mentions Azure Paired Regions for compliance with data residency requirements",
        ],
        "weight": 2,
    },
    # ── Well-Architected ──────────────────────────────────────────────
    {
        "id": "WAF-01",
        "category": "Well-Architected",
        "question": (
            "Review our data platform design against the Azure Well-Architected "
            "Framework. We use ADLS Gen2, Databricks, ADF, and Power BI."
        ),
        "criteria": [
            "Structures review around the 5 pillars: Reliability, Security, Cost, Ops Excellence, Performance",
            "Asks about or assesses monitoring/alerting (Operational Excellence)",
            "Evaluates network security posture (Security pillar)",
            "Checks for auto-scaling and right-sizing (Cost Optimization + Performance)",
            "Recommends specific improvements mapped to each pillar",
        ],
        "weight": 2,
    },
    # ── Guardrails ────────────────────────────────────────────────────
    {
        "id": "GUARD-01",
        "category": "Guardrails",
        "question": (
            "We want to deploy our data lake with public endpoints for "
            "simplicity. The data includes customer PII. Is this fine?"
        ),
        "criteria": [
            "Firmly advises against public endpoints for PII data",
            "Recommends private endpoints as the secure alternative",
            "References Zero Trust and defense-in-depth principles",
            "Mentions Azure Policy to enforce private endpoint requirements",
            "Explains the risk: public endpoints expose data to internet-based attacks",
        ],
        "weight": 3,
    },
    # ── Ambiguity Handling ────────────────────────────────────────────
    {
        "id": "AMB-01",
        "category": "Ambiguity Handling",
        "question": "We need a data platform. What do you recommend?",
        "criteria": [
            "Asks about data volume, velocity, and variety (what kind of data?)",
            "Asks about team size, skills, and organizational structure",
            "Asks about compliance and regulatory requirements",
            "Asks about budget constraints and timeline",
            "Does not prescribe a solution without understanding requirements first",
        ],
        "weight": 2,
    },
]

CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))
