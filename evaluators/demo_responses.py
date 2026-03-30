"""
Demo response registry — pre-built responses for each role, enabling
the full pipeline to run without API keys.

Each role registers two functions:
  - strong(question) → detailed, high-quality response
  - weak(question)   → generic, shallow response (for A/B comparison)
"""

from __future__ import annotations

import re
import random


# ── Registry ──────────────────────────────────────────────────────────────

_REGISTRY: dict[str, dict[str, callable]] = {}


def register(role_slug: str, strong_fn: callable, weak_fn: callable):
    _REGISTRY[role_slug] = {"strong": strong_fn, "weak": weak_fn}


def get_demo_response(role_slug: str, question: str, weak: bool = False) -> str:
    """Get a demo response for a role. Falls back to a generic response."""
    entry = _REGISTRY.get(role_slug)
    if not entry:
        # Fall back to generic
        return _generic_response(question, weak)
    fn = entry["weak"] if weak else entry["strong"]
    return fn(question)


def demo_judge_scores(response: str, n_criteria: int, seed_hint: str) -> list[dict]:
    """Simulate LLM-as-judge scoring for demo mode."""
    is_weak = len(response.strip()) < 600
    random.seed(hash(seed_hint) % 2**32 + (7777 if is_weak else 0))

    results = []
    for i in range(n_criteria):
        if is_weak:
            score = random.choice([0.0, 0.0, 0.4, 0.4, 0.4, 0.7, 0.7, 0.7, 0.8, 0.8])
            if score >= 0.7:
                explanation = "Partially addressed but lacks specific depth."
            elif score >= 0.4:
                explanation = "Barely mentioned — generic advice without specifics."
            else:
                explanation = "Not addressed at all in the response."
        else:
            score = random.choice([0.7, 0.8, 0.8, 0.9, 0.9, 0.9, 1.0, 1.0, 1.0, 1.0])
            if score >= 0.9:
                explanation = "Criterion clearly addressed with specific details."
            elif score >= 0.7:
                explanation = "Partially addressed — could include more specific examples."
            else:
                explanation = "Mentioned briefly but lacks depth or specificity."
        results.append({"score": score, "explanation": explanation})
    return results


def _generic_response(question: str, weak: bool) -> str:
    if weak:
        return "I can help with that. Could you provide more details about your specific requirements?"
    return (
        "Based on your question, here's my recommendation:\n\n"
        "I'd suggest following best practices for your specific platform and use case. "
        "Could you provide more details so I can give targeted guidance?"
    )


# ══════════════════════════════════════════════════════════════════════════
# AZURE DATA ENGINEER
# ══════════════════════════════════════════════════════════════════════════

def _azure_de_strong(question: str) -> str:
    q = question.lower()
    if "synapse" in q and ("dedicated" in q or "serverless" in q):
        return (
            "## Dedicated vs Serverless SQL Pools in Azure Synapse\n\n"
            "**Dedicated SQL Pool** is a provisioned resource with reserved compute (DWUs). "
            "It's ideal for predictable, high-concurrency enterprise workloads with complex "
            "queries over large datasets. You pay for provisioned capacity even when idle, "
            "but you can **pause/resume** to save cost.\n\n"
            "**Serverless SQL Pool** is on-demand — you pay per TB of data scanned. "
            "It's perfect for ad-hoc exploration, querying external data in ADLS Gen2 via "
            "OPENROWSET or external tables, and data discovery.\n\n"
            "### When to use each:\n"
            "| Criteria | Dedicated | Serverless |\n"
            "|---|---|---|\n"
            "| Workload | Predictable, production dashboards | Ad-hoc exploration |\n"
            "| Cost model | Reserved DWUs | Per-TB scanned |\n"
            "| Concurrency | High (workload management) | Lower |\n"
            "| Data | Loaded into pool | External (ADLS, Cosmos DB) |\n\n"
            "**Cost tip**: Use reserved capacity for dedicated pools and pause when not in use."
        )
    elif "scd" in q or "slowly changing" in q:
        return (
            "## SCD Type 2 in Databricks with Delta Lake\n\n"
            "SCD Type 2 tracks historical changes by creating new rows with effective "
            "date ranges (`valid_from`, `valid_to`) and an `is_current` flag.\n\n"
            "### Implementation using Delta MERGE:\n\n"
            "```python\nfrom delta.tables import DeltaTable\n"
            "from pyspark.sql.functions import current_timestamp, lit\n\n"
            "target = DeltaTable.forPath(spark, '/mnt/gold/dim_customer')\n"
            "source = spark.read.table('staging.customers')\n"
            "source = source.withColumn('row_hash', md5(concat_ws('|', *source.columns)))\n\n"
            "target.alias('t').merge(\n"
            "    source.alias('s'),\n"
            "    't.customer_id = s.customer_id AND t.is_current = true'\n"
            ").whenMatchedUpdate(\n"
            "    condition='t.row_hash != s.row_hash',\n"
            "    set={'is_current': lit(False), 'valid_to': current_timestamp()}\n"
            ").whenNotMatchedInsert(\n"
            "    values={'customer_id': 's.customer_id', 'name': 's.name',\n"
            "            'row_hash': 's.row_hash', 'is_current': lit(True),\n"
            "            'valid_from': current_timestamp(), 'valid_to': lit(None)}\n"
            ").execute()\n```\n\n"
            "**Benefits of Delta Lake for SCD2**: Time travel (`VERSION AS OF`) lets you "
            "query any historical state without SCD2 logic, providing a safety net."
        )
    elif "medallion" in q:
        return (
            "## Medallion Architecture on Azure\n\n"
            "The medallion (multi-hop) architecture organizes data in three layers:\n\n"
            "### Bronze (Raw)\nRaw data as-is from source systems in ADLS Gen2 Delta format. "
            "Partitioned by ingestion date. Metadata only (source, timestamp, batch ID).\n\n"
            "### Silver (Cleansed)\nDeduplicated, validated, conformed data with schema enforcement "
            "via Delta Lake schema evolution. Data quality checks applied.\n\n"
            "### Gold (Aggregated)\nBusiness-level aggregates, star schemas, feature tables "
            "optimized for Power BI or ML pipelines.\n\n"
            "### Azure Implementation:\n"
            "- **Storage**: ADLS Gen2 with hierarchical namespace\n"
            "- **Processing**: Databricks (Delta Live Tables) or Synapse Spark\n"
            "- **Format**: Delta Lake across all layers\n"
            "- **Orchestration**: ADF or Databricks Workflows\n"
            "- **Governance**: Unity Catalog for lineage and access control"
        )
    elif "securely connect" in q and "on-premises" in q:
        return (
            "## Securely Connecting ADF to On-Premises SQL Server\n\n"
            "### 1. Self-hosted Integration Runtime (SHIR)\n"
            "Install the SHIR on a VM in your network that can reach the SQL Server.\n\n"
            "### 2. Network connectivity\n"
            "- **Preferred**: Azure ExpressRoute or site-to-site VPN\n"
            "- **Alternative**: SHIR with private endpoints to ADF's managed VNet\n"
            "- **Avoid**: Opening SQL Server port (1433) to the public internet\n\n"
            "### 3. Credential management\n"
            "- Store SQL credentials in **Azure Key Vault**\n"
            "- Reference the Key Vault secret in your ADF linked service\n"
            "- Use **managed identity** for ADF to authenticate to Key Vault\n"
            "- **Never** store passwords directly in linked service JSON\n\n"
            "### 4. Linked Service example:\n```json\n"
            '{"type": "SqlServer", "typeProperties": {"connectionString": '
            '{"type": "AzureKeyVaultSecret", "store": {"referenceName": "AzureKeyVaultLS"}, '
            '"secretName": "onprem-sql-connstring"}}, '
            '"connectVia": {"referenceName": "SelfHostedIR"}}\n```'
        )
    elif "securing" in q and "data lake" in q:
        return (
            "## Securing Azure Data Lake Storage Gen2\n\n"
            "### Access Control\n"
            "- **RBAC** at the management plane (Storage Blob Data Contributor/Reader)\n"
            "- **ACLs** at the data plane for fine-grained folder/file permissions\n"
            "- Combine both: RBAC for broad access, ACLs for path-level control\n\n"
            "### Network Security\n"
            "- Enable **private endpoints** and disable public network access\n"
            "- Use **service endpoints** as a minimum if private endpoints aren't feasible\n\n"
            "### Encryption\n"
            "- **At rest**: Enabled by default (Microsoft-managed keys); use CMK for compliance\n"
            "- **In transit**: TLS 1.2 enforced\n\n"
            "### Identity\n"
            "- Use managed identities for service-to-service access\n"
            "- Avoid shared access keys — disable them if possible"
        )
    elif "databricks" in q and "cost" in q:
        return (
            "## Reducing Azure Databricks Costs\n\n"
            "1. **Autoscaling** — Set min workers to match baseline, max for peak.\n\n"
            "2. **Spot instances** — Use Azure Spot VMs for fault-tolerant batch jobs. Saves 60-90%.\n\n"
            "3. **Right-size VMs** — Profile with Spark UI. Memory-heavy: E-series. Compute: F-series.\n\n"
            "4. **Cluster policies** — Enforce max size, allowed VM types, auto-termination.\n\n"
            "5. **Auto-termination** — Set 10-15 min idle timeout. #1 waste source: overnight clusters.\n\n"
            "6. **Job clusters** — Use ephemeral job clusters instead of all-purpose for production.\n\n"
            "7. **Photon** — Enable for heavy SQL/DataFrame workloads to reduce runtime and DBU cost."
        )
    elif "pyspark" in q and "json" in q:
        return (
            "## PySpark: Read JSON from ADLS Gen2, Flatten & Write to Delta\n\n"
            "```python\nfrom pyspark.sql import SparkSession\n"
            "from pyspark.sql.functions import explode, col, to_date\n\n"
            "spark = SparkSession.builder.appName('json_to_delta').getOrCreate()\n"
            "df = spark.read.json('abfss://raw@mystorageaccount.dfs.core.windows.net/iot/2024/')\n\n"
            "df_flat = (df.withColumn('sensor_reading', explode(col('readings')))\n"
            "    .select(col('device_id'), col('sensor_reading.metric').alias('metric'),\n"
            "            col('sensor_reading.value').alias('value'),\n"
            "            to_date(col('timestamp')).alias('event_date')))\n\n"
            "(df_flat.write.format('delta').mode('append').partitionBy('event_date')\n"
            "    .save('abfss://silver@mystorageaccount.dfs.core.windows.net/sensor_data/'))\n```\n\n"
            "**Notes**: Use `schema_of_json` for large datasets. Chain `explode`/`posexplode` for deep nesting."
        )
    elif "arm" in q or "bicep" in q:
        return (
            "## Bicep Template: ADF with Managed Virtual Network\n\n"
            "```bicep\n@description('Azure Data Factory with Managed VNet')\n"
            "param location string = resourceGroup().location\n"
            "param factoryName string = 'adf-${uniqueString(resourceGroup().id)}'\n\n"
            "resource dataFactory 'Microsoft.DataFactory/factories@2018-06-01' = {\n"
            "  name: factoryName\n  location: location\n"
            "  identity: { type: 'SystemAssigned' }\n"
            "  properties: { managedVirtualNetwork: { type: 'ManagedVirtualNetwork' } }\n}\n\n"
            "resource managedVnet 'Microsoft.DataFactory/factories/managedVirtualNetworks@2018-06-01' = {\n"
            "  parent: dataFactory\n  name: 'default'\n  properties: {}\n}\n\n"
            "resource autoResolveIR 'Microsoft.DataFactory/factories/integrationRuntimes@2018-06-01' = {\n"
            "  parent: dataFactory\n  name: 'AutoResolveIntegrationRuntime'\n"
            "  properties: { type: 'Managed', managedVirtualNetwork: {\n"
            "    referenceName: 'default', type: 'ManagedVirtualNetworkReference' },\n"
            "    typeProperties: { computeProperties: { location: 'AutoResolve' } } }\n"
            "  dependsOn: [managedVnet]\n}\n```\n\n"
            "Add `managedPrivateEndpoints` resource for storage/SQL private connectivity."
        )
    elif "hdinsight" in q or "gen1" in q:
        return (
            "## Recommendation: Avoid ADLS Gen1 and HDInsight for New Projects\n\n"
            "### ADLS Gen1 — End of Life\nReached **end of life Feb 29, 2024**. "
            "Migrate to **ADLS Gen2**: hierarchical namespace, better perf, lower cost, "
            "full integration with modern Azure analytics.\n\n"
            "### HDInsight — Consider Alternatives\nFor new projects, use **Azure Databricks** "
            "or **Synapse Spark** over HDInsight:\n"
            "- Lower operational overhead (fully managed, no cluster patching)\n"
            "- Better integration (Unity Catalog, Delta Lake, ADF connectors)\n"
            "- Better developer experience (collaborative notebooks, Git)\n"
            "- Performance (Photon engine, intelligent caching)\n\n"
            "HDInsight still has niche uses (Kafka, HBase) but for Spark/Hive workloads, "
            "managed alternatives are significantly better."
        )
    elif "aws" in q or "glue" in q:
        return (
            "## Azure Equivalents for AWS Glue\n\n"
            "As an Azure-focused assistant, here are the Azure-native equivalents:\n\n"
            "| AWS Glue Feature | Azure Equivalent |\n|---|---|\n"
            "| Glue ETL Jobs | **Azure Data Factory** Data Flows or **Databricks** Jobs |\n"
            "| Glue Crawlers | ADF Mapping Data Flows with schema drift |\n"
            "| Glue Data Catalog | **Unity Catalog** or **Microsoft Purview** |\n"
            "| Glue Studio | ADF visual authoring or Databricks notebooks |\n\n"
            "Happy to help design your architecture using ADF or Databricks. What's your use case?"
        )
    elif "real-time" in q or "iot" in q or "100k" in q:
        return (
            "## Real-Time IoT Pipeline for 100K Events/sec\n\n"
            "### Architecture:\n```\nIoT Devices -> Event Hubs -> Stream Processing -> Serving Layer -> Dashboard\n```\n\n"
            "### 1. Ingestion: Azure Event Hubs\n- Standard/Premium tier, 32 partitions for throughput\n"
            "- Capture to ADLS Gen2 for raw archival (Bronze)\n\n"
            "### 2. Stream Processing: Databricks Structured Streaming\n"
            "- Windowed aggregations, micro-batches every 30-60s for <5 min latency\n\n"
            "### 3. Serving Layer: Azure Data Explorer (ADX)\n"
            "- Optimized for time-series, sub-second response, KQL analytics\n\n"
            "### 4. Monitoring\n- Event Hubs metrics, StreamingQueryListener, Azure Monitor alerts"
        )
    elif "load data" in q and len(q) < 50:
        return (
            "I need more context to give the best answer. Could you clarify:\n\n"
            "1. **Source**: On-prem SQL, API, flat files, another cloud, streaming?\n"
            "2. **Destination**: ADLS Gen2, Synapse, Databricks, SQL Database, Cosmos DB?\n"
            "3. **Format**: CSV, JSON, Parquet, Avro, database tables?\n"
            "4. **Volume & Frequency**: One-time or recurring? Batch or streaming?\n"
            "5. **Transformations**: Transform during load or load raw first?\n\n"
            "Common patterns:\n"
            "- **Batch on-prem**: ADF + Self-hosted IR -> ADLS Gen2\n"
            "- **Batch cloud**: ADF managed IR -> ADLS Gen2 / Synapse\n"
            "- **Real-time**: Event Hubs -> Stream Analytics / Databricks\n"
            "- **File-based**: ADF Copy Activity with format conversion"
        )
    else:
        return (
            "Based on your question, here's my recommendation as an Azure Data Engineer:\n\n"
            "I'd suggest leveraging Azure Data Factory for orchestration, ADLS Gen2 for "
            "storage, and Databricks or Synapse for processing. For security, always use "
            "managed identities and Key Vault for secrets management.\n\n"
            "Could you provide more specific details about your use case?"
        )


def _azure_de_weak(question: str) -> str:
    q = question.lower()
    if "synapse" in q and ("dedicated" in q or "serverless" in q):
        return "Dedicated SQL pool is for big workloads and serverless is for smaller queries. Dedicated costs more but is faster."
    elif "scd" in q or "slowly changing" in q:
        return "SCD Type 2 tracks history by adding new rows. In Databricks you can use MERGE to update and insert rows."
    elif "medallion" in q:
        return "The medallion architecture has three layers: bronze for raw, silver for cleaned, gold for aggregates."
    elif "securely connect" in q and "on-premises" in q:
        return "Install a Self-hosted Integration Runtime on a machine that can access the SQL Server, then create a linked service."
    elif "securing" in q and "data lake" in q:
        return "Use role-based access control to manage who can access the data. Set up proper authentication."
    elif "databricks" in q and "cost" in q:
        return "Use smaller clusters and shut them down when not in use. Enable autoscaling."
    elif "pyspark" in q and "json" in q:
        return "Read JSON with spark.read.json() and write to Delta with .write.format('delta'). Use explode() for nested data."
    elif "arm" in q or "bicep" in q:
        return "Deploy ADF using an ARM template. Resource type is Microsoft.DataFactory/factories."
    elif "hdinsight" in q or "gen1" in q:
        return "HDInsight is a managed Hadoop service and ADLS Gen1 is storage. Both are available on Azure."
    elif "aws" in q or "glue" in q:
        return "AWS Glue is a serverless ETL service. Create a Glue job, define source and target, write transformations."
    elif "real-time" in q or "iot" in q or "100k" in q:
        return "Use Azure Event Hubs to ingest data and process with Stream Analytics or Databricks."
    elif "load data" in q and len(q) < 50:
        return "Use Azure Data Factory. Create a pipeline with a copy activity, configure source and destination."
    else:
        return "I'd suggest using Azure Data Factory or Databricks. They're both good options for data engineering on Azure."


register("azure_data_engineer", _azure_de_strong, _azure_de_weak)


# ══════════════════════════════════════════════════════════════════════════
# FABRIC DATA ENGINEER
# ══════════════════════════════════════════════════════════════════════════

def _fabric_de_strong(question: str) -> str:
    q = question.lower()
    if "lakehouse" in q and "warehouse" in q:
        return (
            "## Fabric Lakehouse vs Warehouse\n\n"
            "### Lakehouse\n"
            "- **Open format**: Data stored as Delta Parquet in OneLake\n"
            "- **Best for**: Data engineering, Spark-based transformations, ML workloads\n"
            "- **Access**: Spark notebooks, SQL endpoint (read-only T-SQL), Dataflows Gen2\n"
            "- **Schema**: Schema-on-read flexibility with Delta schema evolution\n"
            "- **Cost**: Included in Fabric capacity, no separate compute billing\n\n"
            "### Warehouse\n"
            "- **SQL-first**: Full T-SQL DML/DDL support (INSERT, UPDATE, DELETE, MERGE)\n"
            "- **Best for**: Traditional BI workloads, complex SQL transformations, multi-table joins\n"
            "- **Access**: T-SQL only (no Spark), cross-database queries\n"
            "- **Schema**: Schema-on-write, enforced data types\n"
            "- **Cost**: Uses Fabric capacity units (CUs) for query processing\n\n"
            "### When to use each:\n"
            "| Criteria | Lakehouse | Warehouse |\n|---|---|---|\n"
            "| Primary language | PySpark/Spark SQL | T-SQL |\n"
            "| Data format control | Full (Delta, Parquet) | Managed |\n"
            "| Write pattern | Append/merge via Spark | Full DML |\n"
            "| BI serving | Via SQL endpoint | Direct T-SQL |\n\n"
            "**Pro tip**: You can use shortcuts to make Lakehouse data accessible from Warehouse and vice versa."
        )
    elif "onelake" in q or "shortcut" in q:
        return (
            "## OneLake and Shortcuts in Microsoft Fabric\n\n"
            "### OneLake\n"
            "OneLake is Fabric's unified storage layer — think of it as **OneDrive for data**. "
            "Every Fabric workspace maps to a OneLake container. All Fabric items (Lakehouses, "
            "Warehouses, KQL databases) store data in OneLake in Delta Parquet format.\n\n"
            "### Shortcuts\n"
            "Shortcuts are **pointers** to data in external locations — no data copy required:\n"
            "- **ADLS Gen2**: Point to existing storage accounts\n"
            "- **Amazon S3 / GCS**: Cross-cloud data access\n"
            "- **Other OneLake locations**: Cross-workspace references\n"
            "- **Dataverse**: Direct access to Dynamics 365 data\n\n"
            "### Key Benefits:\n"
            "- **Zero-copy**: No ETL needed to access external data\n"
            "- **Unified governance**: OneLake security applies uniformly\n"
            "- **Cross-workspace**: Share data without duplication\n\n"
            "### Creating a shortcut:\n"
            "```python\n# In a Fabric notebook\n"
            "df = spark.read.format('delta').load('Tables/my_shortcut')\n"
            "# Reads directly from the external source via the shortcut\n```"
        )
    elif "dataflow" in q or "gen2" in q:
        return (
            "## Dataflows Gen2 in Microsoft Fabric\n\n"
            "Dataflows Gen2 is the **low-code ETL** tool in Fabric, powered by Power Query (M language).\n\n"
            "### Key Features:\n"
            "- **Power Query editor**: 300+ connectors, visual transformations\n"
            "- **Output destinations**: Lakehouse tables, Warehouse tables, KQL databases\n"
            "- **Staging**: Uses Lakehouse staging for better performance\n"
            "- **Incremental refresh**: Built-in support for date-based partitions\n\n"
            "### When to use Dataflows Gen2 vs Notebooks:\n"
            "| Criteria | Dataflows Gen2 | Spark Notebooks |\n|---|---|---|\n"
            "| Skill level | Low-code / citizen developer | Developer |\n"
            "| Data volume | Small-medium (<1GB per run) | Large (GB-TB) |\n"
            "| Transformations | Standard (filter, merge, pivot) | Complex (ML, UDFs) |\n"
            "| Orchestration | Data Pipeline activity | Data Pipeline / Notebooks |\n\n"
            "### Best Practice:\n"
            "Use Dataflows Gen2 for simple ingestion from SaaS sources, Spark notebooks "
            "for heavy transformations, and Data Pipelines to orchestrate both."
        )
    elif "spark" in q and "notebook" in q:
        return (
            "## Fabric Spark Notebooks Best Practices\n\n"
            "### Environment Setup\n"
            "- Use **Fabric Runtime** (managed Spark) — no cluster config needed\n"
            "- Fabric Spark supports PySpark, Spark SQL, Scala, and R\n"
            "- Default runtime includes Delta Lake, MLflow, and common libraries\n\n"
            "### Working with Lakehouse Data\n"
            "```python\n# Read from Lakehouse table\n"
            "df = spark.read.table('lakehouse_name.table_name')\n\n"
            "# Write to Lakehouse table\n"
            "df.write.mode('overwrite').format('delta').saveAsTable('lakehouse_name.output_table')\n\n"
            "# Use Fabric-specific abfss paths\n"
            "df = spark.read.parquet('abfss://workspace@onelake.dfs.fabric.microsoft.com/lakehouse.Lakehouse/Files/')\n```\n\n"
            "### Key Fabric Spark Features:\n"
            "- **V-Order optimization**: Automatically applied on write for faster reads\n"
            "- **High Concurrency mode**: Share Spark sessions across notebooks\n"
            "- **Notebook resources**: Upload .py, .whl files for library management\n"
            "- **mssparkutils**: Fabric-specific utilities (credentials, fs operations)"
        )
    elif "pipeline" in q or "orchestrat" in q:
        return (
            "## Data Pipelines in Microsoft Fabric\n\n"
            "Fabric Data Pipelines are the orchestration layer (similar to ADF but Fabric-native).\n\n"
            "### Key Activities:\n"
            "- **Copy Activity**: Move data between 100+ sources and Fabric destinations\n"
            "- **Notebook Activity**: Run Spark notebooks with parameters\n"
            "- **Dataflow Activity**: Execute Dataflows Gen2\n"
            "- **Stored Procedure**: Execute Warehouse stored procedures\n"
            "- **KQL Activity**: Run KQL queries against Eventhouse\n\n"
            "### Pipeline Patterns:\n"
            "```\nIngest (Copy) -> Transform (Notebook) -> Serve (Warehouse SP) -> Notify\n```\n\n"
            "### Best Practices:\n"
            "- Use **parameterized pipelines** for reusability across environments\n"
            "- Use **pipeline variables** for dynamic file paths and table names\n"
            "- Set up **retry policies** on activities for transient failures\n"
            "- Monitor via **Fabric Monitoring Hub** for run history and errors\n"
            "- Use **Git integration** to version-control pipeline definitions"
        )
    elif "security" in q or "access" in q or "governance" in q:
        return (
            "## Fabric Security and Governance\n\n"
            "### Workspace-level Security\n"
            "- **Workspace roles**: Admin, Member, Contributor, Viewer\n"
            "- Use Azure AD groups for role assignments\n"
            "- Separate workspaces for Dev/Test/Prod\n\n"
            "### Item-level Security\n"
            "- **Row-Level Security (RLS)**: Define roles in semantic models\n"
            "- **Column-Level Security (CLS)**: Available in Warehouse\n"
            "- **Object-Level Security (OLS)**: Hide tables/columns in semantic models\n\n"
            "### OneLake Security\n"
            "- **OneLake data access roles**: Control who can read specific folders\n"
            "- Inherits from workspace permissions by default\n"
            "- Shortcut security respects source system permissions\n\n"
            "### Governance\n"
            "- **Microsoft Purview integration**: Lineage, classification, sensitivity labels\n"
            "- **Endorsement**: Promote or certify trusted items\n"
            "- **Domains**: Organize workspaces by business domain"
        )
    elif "cost" in q or "capacity" in q:
        return (
            "## Fabric Capacity and Cost Management\n\n"
            "### Capacity Units (CUs)\n"
            "- All Fabric workloads consume CUs from a shared pool\n"
            "- **F2** (2 CUs) to **F2048** (2048 CUs) SKUs available\n"
            "- CUs are shared across: Spark, SQL, Dataflows, Power BI, Real-Time Analytics\n\n"
            "### Cost Optimization Strategies:\n"
            "1. **Right-size capacity**: Start with F64 for typical enterprise workloads\n"
            "2. **Capacity pause/resume**: Pause during off-hours via Azure Portal or API\n"
            "3. **Smoothing & bursting**: Fabric smooths CU usage over 24h — brief spikes are free\n"
            "4. **Monitor with Capacity Metrics app**: Track which workloads consume the most CUs\n"
            "5. **Optimize Spark**: Use V-Order, reduce shuffles, right-size Spark pools\n"
            "6. **Reserved capacity**: 1-year reservations save ~40% vs pay-as-you-go\n\n"
            "**Key insight**: Unlike Databricks/Synapse, Fabric has a single billing model — "
            "no separate charges for compute, storage, or ingress/egress within OneLake."
        )
    elif "medallion" in q or "bronze" in q or "silver" in q or "gold" in q:
        return (
            "## Medallion Architecture in Microsoft Fabric\n\n"
            "### Bronze Layer\n"
            "- **Lakehouse**: Store raw data in Files/ folder or as Delta tables\n"
            "- Use **Copy Activity** in Data Pipelines for ingestion\n"
            "- Add metadata columns: _source, _ingestion_timestamp, _batch_id\n\n"
            "### Silver Layer\n"
            "- **Spark Notebooks**: PySpark transformations for cleansing & deduplication\n"
            "- Apply schema enforcement via Delta Lake schema evolution\n"
            "- Write to Lakehouse Tables/ (auto-registered in SQL endpoint)\n\n"
            "### Gold Layer\n"
            "- **Warehouse** for star schemas served to Power BI (T-SQL, full DML)\n"
            "- OR **Lakehouse** Gold tables + semantic model\n\n"
            "### Fabric-Specific Advantages:\n"
            "- **No data movement**: Bronze->Silver->Gold all in OneLake\n"
            "- **Unified governance**: Purview lineage traces the full path\n"
            "- **Automatic SQL endpoint**: Silver/Gold tables queryable via T-SQL immediately\n"
            "- **V-Order**: Applied automatically for optimized reads by Power BI"
        )
    elif "real-time" in q or "eventstream" in q or "eventhouse" in q:
        return (
            "## Real-Time Analytics in Microsoft Fabric\n\n"
            "### Key Components:\n"
            "- **Eventstream**: No-code ingestion from Event Hubs, Kafka, custom apps\n"
            "- **Eventhouse**: KQL-based analytical store (based on Azure Data Explorer)\n"
            "- **Real-Time Dashboard**: Live KQL-powered dashboards\n"
            "- **Activator**: Data-driven alerts and actions\n\n"
            "### Architecture Pattern:\n"
            "```\nEvent Source -> Eventstream -> Eventhouse -> Real-Time Dashboard\n"
            "                          \\-> Lakehouse (archival)\n```\n\n"
            "### When to use:\n"
            "- IoT telemetry, clickstream, application logs, financial ticks\n"
            "- Need sub-second query latency on streaming data\n"
            "- Want KQL for powerful time-series analytics\n\n"
            "**Tip**: Use Eventstream's built-in transformations for light processing before landing in Eventhouse."
        )
    else:
        return (
            "As a Fabric Data Engineer, I'd recommend using Microsoft Fabric's integrated "
            "platform: Lakehouse for storage, Spark notebooks for transformations, Data Pipelines "
            "for orchestration, and the SQL endpoint for BI serving. All data lives in OneLake.\n\n"
            "Could you provide more details about your specific scenario?"
        )


def _fabric_de_weak(question: str) -> str:
    q = question.lower()
    if "lakehouse" in q and "warehouse" in q:
        return "Lakehouse is for unstructured data and Warehouse is for structured data. Use Lakehouse for big data."
    elif "onelake" in q or "shortcut" in q:
        return "OneLake is the storage for Fabric. Shortcuts let you reference external data."
    elif "dataflow" in q or "gen2" in q:
        return "Dataflows Gen2 is for low-code data transformations in Fabric. It uses Power Query."
    elif "spark" in q and "notebook" in q:
        return "Fabric notebooks use Spark. You can write PySpark code to process data."
    elif "pipeline" in q or "orchestrat" in q:
        return "Use Data Pipelines in Fabric to orchestrate your data workflows. Similar to ADF."
    elif "security" in q or "access" in q:
        return "Set up workspace roles to control access. Use Azure AD groups."
    elif "cost" in q or "capacity" in q:
        return "Fabric uses capacity units. Choose the right SKU for your workload."
    elif "medallion" in q or "bronze" in q:
        return "Bronze for raw data, silver for cleaned, gold for aggregated. Use Lakehouse."
    elif "real-time" in q or "eventstream" in q:
        return "Use Eventstream for real-time ingestion and Eventhouse for analytics."
    else:
        return "Use Microsoft Fabric for your data engineering needs. It has Lakehouse, Warehouse, and notebooks."


register("fabric_data_engineer", _fabric_de_strong, _fabric_de_weak)


# ══════════════════════════════════════════════════════════════════════════
# SQL REPORT ENGINEER
# ══════════════════════════════════════════════════════════════════════════

def _sql_report_strong(question: str) -> str:
    q = question.lower()
    if "paginated" in q or "ssrs" in q or "report builder" in q:
        return (
            "## Paginated Reports in Power BI / SSRS\n\n"
            "Paginated reports are **pixel-perfect**, designed for printing and PDF export. "
            "They render every row (no pagination limits like interactive reports).\n\n"
            "### When to use:\n"
            "- Invoices, purchase orders, statements\n"
            "- Regulatory reports requiring exact formatting\n"
            "- Reports with 1000+ rows that must be fully rendered\n"
            "- Operational reports distributed via email subscriptions\n\n"
            "### Tools:\n"
            "- **Power BI Report Builder** (modern, recommended)\n"
            "- **SQL Server Report Builder** (legacy SSRS)\n"
            "- **Visual Studio with SSRS extension** (for SSRS on-prem)\n\n"
            "### Data Sources:\n"
            "- Power BI datasets (semantic models)\n"
            "- Azure SQL, SQL Server, Analysis Services\n"
            "- Oracle, PostgreSQL (via ODBC/OLE DB)\n\n"
            "### Best Practices:\n"
            "- Use **stored procedures** for complex data retrieval\n"
            "- Parameterize reports for date ranges and filters\n"
            "- Test with realistic data volumes — pagination logic matters\n"
            "- Use **shared datasets** for reusability across reports"
        )
    elif "parameter" in q:
        return (
            "## Parameterized Reports Best Practices\n\n"
            "### Parameter Types:\n"
            "- **Text**: Free-text input (validate with available values where possible)\n"
            "- **Date/DateTime**: Use calendar picker, default to current month\n"
            "- **Dropdown**: Populated from a dataset query (cascading supported)\n"
            "- **Multi-value**: Allow multiple selections with IN clause\n\n"
            "### Cascading Parameters:\n"
            "```sql\n-- Parent parameter: Region\nSELECT DISTINCT Region FROM dim_geography\n\n"
            "-- Child parameter: City (filtered by Region)\n"
            "SELECT DISTINCT City FROM dim_geography WHERE Region IN (@Region)\n```\n\n"
            "### Performance Tips:\n"
            "- Use **default values** to avoid empty initial renders\n"
            "- Cache parameter datasets separately from main report\n"
            "- Use stored procedures with parameter sniffing protection (OPTION RECOMPILE)\n"
            "- For large multi-value parameters, consider a staging pattern"
        )
    elif "performance" in q or "optim" in q or "slow" in q:
        return (
            "## SQL Report Performance Optimization\n\n"
            "### Data Layer:\n"
            "- **Use stored procedures** instead of inline SQL — better execution plans\n"
            "- Add appropriate **indexes** on filter/sort columns\n"
            "- Use **OPTION (RECOMPILE)** for parameter-sensitive queries\n"
            "- Pre-aggregate in views or materialized views for summary reports\n\n"
            "### Report Layer:\n"
            "- **Reduce dataset scope**: Only select columns you actually display\n"
            "- **Avoid subreports** where possible — use sub-queries or JOINs instead\n"
            "- Minimize use of **lookup functions** across datasets\n"
            "- Use **shared datasets** to avoid duplicate query execution\n\n"
            "### Rendering:\n"
            "- **Limit images/charts** per page — heavy rendering impacts export time\n"
            "- Use **page breaks** strategically to control memory usage\n"
            "- For large reports (5000+ pages), consider splitting into subscriptions"
        )
    elif "expression" in q or "formula" in q:
        return (
            "## SSRS/Paginated Report Expressions\n\n"
            "Expressions use VB.NET syntax prefixed with `=`.\n\n"
            "### Common Patterns:\n"
            "```vb\n' Conditional formatting\n"
            "=IIF(Fields!Amount.Value < 0, \"Red\", \"Black\")\n\n"
            "' Running total\n=RunningValue(Fields!Sales.Value, Sum, Nothing)\n\n"
            "' Percentage of total\n=Fields!Sales.Value / Sum(Fields!Sales.Value)\n\n"
            "' Custom grouping\n=Switch(\n"
            "  Fields!Amount.Value >= 10000, \"High\",\n"
            "  Fields!Amount.Value >= 1000, \"Medium\",\n"
            "  True, \"Low\")\n\n"
            "' Page number\n=\"Page \" & Globals!PageNumber & \" of \" & Globals!TotalPages\n```\n\n"
            "### Best Practices:\n"
            "- Move complex calculations to the SQL query, not report expressions\n"
            "- Use **Code blocks** in report properties for reusable VB functions\n"
            "- Test expressions with NULL handling — use `IsNothing()`"
        )
    elif "subreport" in q or "drill" in q:
        return (
            "## Subreports and Drillthrough in Paginated Reports\n\n"
            "### Subreports (Embedded)\n"
            "- Rendered **inline** within the parent report\n"
            "- Each subreport instance is a separate data request (performance impact!)\n"
            "- Pass parameters from parent: right-click subreport -> Properties -> Parameters\n"
            "- **When to use**: Reusable components (headers, footers, address blocks)\n"
            "- **Avoid**: Inside tablix row groups — causes N+1 query problem\n\n"
            "### Drillthrough (Navigation)\n"
            "- Navigates to a **separate report** with context parameters\n"
            "- Better performance than subreports (loaded on demand)\n"
            "- Configure via: Textbox Properties -> Action -> Go to Report\n"
            "- **When to use**: Detail reports linked from summary views\n\n"
            "### Best Practice:\n"
            "Prefer drillthrough over subreports for detail data. Use subreports only for "
            "truly reusable visual components. If you find yourself with 50+ subreport instances, "
            "refactor to JOIN-based approach in a single dataset."
        )
    elif "subscription" in q or "schedul" in q or "email" in q:
        return (
            "## Report Subscriptions and Distribution\n\n"
            "### Power BI Service (Paginated):\n"
            "- **Email subscriptions**: Schedule delivery in PDF, Excel, Word, CSV, XML\n"
            "- Set frequency: daily, weekly, monthly, or after data refresh\n"
            "- Include **parameterized variants** per recipient\n"
            "- Requires Power BI Premium or PPU capacity\n\n"
            "### SSRS (On-premises):\n"
            "- **Standard subscriptions**: Email or file share delivery\n"
            "- **Data-driven subscriptions**: Dynamic recipients from a database query\n"
            "- Configure rendering format per subscription\n"
            "- Use **SQL Server Agent** as the scheduling engine\n\n"
            "### Best Practices:\n"
            "- Stagger subscriptions to avoid capacity spikes at 8:00 AM\n"
            "- Monitor delivery failures via SSRS execution log\n"
            "- For large distributions, use data-driven subscriptions + shared schedule"
        )
    elif "t-sql" in q or "stored proc" in q or "query" in q:
        return (
            "## T-SQL Best Practices for Reporting\n\n"
            "### Stored Procedure Pattern:\n"
            "```sql\nCREATE PROCEDURE rpt.usp_MonthlySalesSummary\n"
            "    @StartDate DATE, @EndDate DATE, @Region NVARCHAR(50) = NULL\nAS\nBEGIN\n"
            "    SET NOCOUNT ON;\n"
            "    SELECT c.CustomerName, p.ProductCategory,\n"
            "           SUM(s.Amount) AS TotalSales, COUNT(s.OrderID) AS OrderCount\n"
            "    FROM fact_sales s\n    JOIN dim_customer c ON s.CustomerKey = c.CustomerKey\n"
            "    JOIN dim_product p ON s.ProductKey = p.ProductKey\n"
            "    WHERE s.OrderDate BETWEEN @StartDate AND @EndDate\n"
            "      AND (@Region IS NULL OR c.Region = @Region)\n"
            "    GROUP BY c.CustomerName, p.ProductCategory\n"
            "    ORDER BY TotalSales DESC\n    OPTION (RECOMPILE);\nEND\n```\n\n"
            "### Key Principles:\n"
            "- Use `rpt` schema for reporting procedures\n"
            "- Always parameterize date ranges\n"
            "- Use OPTION (RECOMPILE) for parameter-sensitive queries\n"
            "- Create covering indexes on fact tables for report filter columns"
        )
    else:
        return (
            "As a SQL Report Engineer, I'd recommend following these principles:\n\n"
            "- Use **stored procedures** for data retrieval (better performance, reusability)\n"
            "- Choose **paginated reports** for pixel-perfect/print, interactive for dashboards\n"
            "- **Parameterize** everything — date ranges, filters, business units\n"
            "- Optimize T-SQL with proper indexing and query hints\n\n"
            "What specific reporting scenario are you working on?"
        )


def _sql_report_weak(question: str) -> str:
    q = question.lower()
    if "paginated" in q or "ssrs" in q:
        return "Paginated reports are for printing. Use Report Builder to create them."
    elif "parameter" in q:
        return "Add parameters to your report for user input. Use dropdowns for common values."
    elif "performance" in q or "slow" in q:
        return "Make sure your queries are optimized. Add indexes to your tables."
    elif "expression" in q:
        return "Use IIF expressions for conditional formatting. Prefix with = sign."
    elif "subreport" in q or "drill" in q:
        return "Subreports embed one report in another. Drillthrough navigates to a detail report."
    elif "subscription" in q or "email" in q:
        return "Set up email subscriptions in SSRS or Power BI Service to distribute reports."
    elif "t-sql" in q or "stored proc" in q:
        return "Use stored procedures for report data. Parameterize your queries."
    else:
        return "Use SSRS or Power BI paginated reports for your reporting needs."


register("sql_report_engineer", _sql_report_strong, _sql_report_weak)


# ══════════════════════════════════════════════════════════════════════════
# POWER BI ENGINEER
# ══════════════════════════════════════════════════════════════════════════

def _pbi_strong(question: str) -> str:
    q = question.lower()
    if "dax" in q and ("measure" in q or "calculat" in q):
        return (
            "## DAX Measures Best Practices\n\n"
            "### Core Patterns:\n"
            "```dax\n// Time intelligence — YTD Sales\n"
            "Sales YTD = TOTALYTD([Total Sales], 'Date'[Date])\n\n"
            "// Previous year comparison\n"
            "Sales PY = CALCULATE([Total Sales], SAMEPERIODLASTYEAR('Date'[Date]))\n\n"
            "// YoY Growth %\n"
            "YoY Growth % = DIVIDE([Total Sales] - [Sales PY], [Sales PY], BLANK())\n\n"
            "// Moving average (3-month)\n"
            "Sales 3M Avg = AVERAGEX(\n"
            "    DATESINPERIOD('Date'[Date], MAX('Date'[Date]), -3, MONTH),\n"
            "    [Total Sales])\n\n"
            "// Rank within category\n"
            "Product Rank = RANKX(ALLSELECTED('Product'[ProductName]), [Total Sales])\n```\n\n"
            "### Best Practices:\n"
            "- **Always use DIVIDE()** instead of `/` to handle division by zero\n"
            "- **Avoid calculated columns** for aggregations — use measures instead\n"
            "- **Use variables** (VAR/RETURN) for readability and performance\n"
            "- **Minimize FILTER()** — prefer CALCULATE with column filters\n"
            "- **Name measures descriptively**: `Sales YTD` not `Measure1`"
        )
    elif "data model" in q or "star schema" in q or "relationship" in q:
        return (
            "## Data Modeling in Power BI\n\n"
            "### Star Schema (Recommended)\n"
            "- **Fact tables**: Narrow, many rows, numeric measures, foreign keys\n"
            "- **Dimension tables**: Wide, fewer rows, descriptive attributes\n"
            "- **Relationships**: Fact -> Dimension (many-to-one)\n"
            "- **Cross-filter direction**: Single (dimension filters fact, not reverse)\n\n"
            "### Anti-Patterns to Avoid:\n"
            "- **Wide flat tables**: Cause ambiguous DAX context, poor compression\n"
            "- **Bidirectional filters**: Cause circular dependencies, performance issues\n"
            "- **Snowflake dimensions**: Flatten into single dimension tables\n"
            "- **Calculated columns for aggregation**: Use measures instead\n\n"
            "### Performance Tips:\n"
            "- Remove unused columns (reduce model size)\n"
            "- Use integer surrogate keys for relationships\n"
            "- Mark your date table with 'Mark as date table'\n"
            "- Set columns to 'Hidden' if not used in visuals\n"
            "- Enable **Auto date/time OFF** to prevent hidden date tables"
        )
    elif "rls" in q or "row.level" in q or "row-level" in q or "security" in q:
        return (
            "## Row-Level Security (RLS) in Power BI\n\n"
            "### Static RLS:\n"
            "```dax\n// In Power BI Desktop → Modeling → Manage Roles\n"
            "// Role: RegionManager\n"
            "[Region] = \"North America\"\n\n"
            "// Role: DynamicUser (recommended)\n"
            "[UserEmail] = USERPRINCIPALNAME()\n```\n\n"
            "### Dynamic RLS (Best Practice):\n"
            "1. Create a **security table**: `UserEmail, Region, Department`\n"
            "2. Relate security table to your model (inactive relationship + USERELATIONSHIP if needed)\n"
            "3. DAX filter: `[UserEmail] = USERPRINCIPALNAME()`\n"
            "4. All users share ONE role — permissions driven by data\n\n"
            "### Testing:\n"
            "- Desktop: Modeling → View as Roles\n"
            "- Service: Workspace → Dataset → Security → Test as Role\n\n"
            "### Key Considerations:\n"
            "- RLS only works on **Import** and **DirectQuery** models\n"
            "- Workspace admins/members bypass RLS — assign Viewer role for security\n"
            "- Test with actual user accounts, not just 'View as'"
        )
    elif "incremental" in q or "refresh" in q:
        return (
            "## Incremental Refresh in Power BI\n\n"
            "### Setup:\n"
            "1. Create **RangeStart** and **RangeEnd** parameters (DateTime type)\n"
            "2. Filter your source query: `WHERE OrderDate >= @RangeStart AND OrderDate < @RangeEnd`\n"
            "3. Right-click table → **Incremental refresh** → Configure:\n"
            "   - Archive: 3 years (historical, never re-fetched)\n"
            "   - Incremental: 30 days (re-fetched each refresh)\n\n"
            "### Query Folding (Critical!):\n"
            "- The date filter MUST fold to the source (pushed down as SQL WHERE)\n"
            "- Check: Right-click step → View Native Query (should show SQL)\n"
            "- If folding breaks, refresh downloads ALL data every time\n\n"
            "### Advanced:\n"
            "- **Detect data changes**: Use a column (e.g., `LastModifiedDate`) to skip unchanged partitions\n"
            "- **Real-time + incremental**: Enable DirectQuery for the latest partition\n"
            "- **XMLA endpoint**: Manage partitions programmatically for advanced scenarios"
        )
    elif "deployment" in q or "pipeline" in q or "ci" in q or "cd" in q:
        return (
            "## Power BI Deployment Pipelines and CI/CD\n\n"
            "### Deployment Pipelines (Built-in):\n"
            "- **3 stages**: Development → Test → Production\n"
            "- Supports: Reports, datasets, dashboards, dataflows\n"
            "- **Deployment rules**: Override connection strings per stage\n"
            "- One-click promote with diff comparison\n\n"
            "### Git Integration (Recommended for Teams):\n"
            "- Connect workspace to Azure DevOps or GitHub repo\n"
            "- Each item serialized as PBIR/TMDL files in the repo\n"
            "- Use branches for feature development\n"
            "- PR reviews before merge to main\n\n"
            "### CI/CD with Azure DevOps:\n"
            "- Use **Tabular Editor CLI** for dataset validation in pipeline\n"
            "- Use **Power BI REST API** for programmatic deployment\n"
            "- Best Practice Model:\n"
            "```\nDev (Git branch) → PR → Main → Deploy Pipeline → Test → Prod\n```\n\n"
            "### Parameter Rules:\n"
            "- Database server/database per environment\n"
            "- Storage account paths per environment\n"
            "- Never hardcode connection strings in .pbix files"
        )
    elif "power query" in q or " m " in q or "transform" in q:
        return (
            "## Power Query / M Language Best Practices\n\n"
            "### Query Folding:\n"
            "- **Always check** that transformations fold to the source\n"
            "- Operations that fold: filter, select columns, sort, group, merge (to SQL JOIN)\n"
            "- Operations that break folding: custom columns with M functions, pivot, unpivot (varies)\n"
            "- Check: right-click step → 'View Native Query'\n\n"
            "### Performance Patterns:\n"
            "```m\n// Good: Filter early (folds to SQL WHERE)\nlet\n"
            "    Source = Sql.Database(\"server\", \"db\"),\n"
            "    Sales = Source{[Schema=\"dbo\",Item=\"Sales\"]}[Data],\n"
            "    Filtered = Table.SelectRows(Sales, each [Year] >= 2024)\nin\n    Filtered\n\n"
            "// Good: Remove unused columns early\n"
            "    Trimmed = Table.SelectColumns(Filtered, {\"Date\",\"Amount\",\"Customer\"})\n```\n\n"
            "### Organization:\n"
            "- Group queries into folders (staging, dimensions, facts)\n"
            "- Use **reference queries** to branch from a common source\n"
            "- Disable load for staging queries\n"
            "- Use parameters for environment-specific values"
        )
    elif "composite" in q or "directquery" in q or "import" in q:
        return (
            "## Composite Models and Storage Modes\n\n"
            "### Storage Modes:\n"
            "- **Import**: Data loaded into memory. Fastest queries, scheduled refresh\n"
            "- **DirectQuery**: Queries sent to source on demand. Real-time, slower queries\n"
            "- **Dual**: Can behave as Import or DirectQuery depending on context\n\n"
            "### Composite Models:\n"
            "Mix Import + DirectQuery in the same model:\n"
            "- **Dimensions**: Import mode (fast slicing, low cardinality)\n"
            "- **Large fact tables**: DirectQuery (avoid importing billions of rows)\n"
            "- **Aggregation tables**: Import with pre-aggregated data for fast summaries\n\n"
            "### Aggregation Pattern:\n"
            "1. Create pre-aggregated table (daily summaries) as Import\n"
            "2. Keep detail table as DirectQuery\n"
            "3. Set 'Manage Aggregations' on the summary table\n"
            "4. Power BI automatically routes queries to the fastest source\n\n"
            "### Recommendations:\n"
            "- Prefer Import for datasets under 1GB\n"
            "- Use composite only when data volume exceeds Import capacity\n"
            "- Monitor with Performance Analyzer to verify aggregation hits"
        )
    else:
        return (
            "As a Power BI Engineer, here are the key principles I'd recommend:\n\n"
            "- **Star schema** data model with clear fact/dimension separation\n"
            "- **Measures over calculated columns** for all aggregations\n"
            "- **Incremental refresh** for large datasets\n"
            "- **RLS** for data security, driven by a security table\n"
            "- **Git integration** for team collaboration and CI/CD\n\n"
            "What specific Power BI challenge are you working on?"
        )


def _pbi_weak(question: str) -> str:
    q = question.lower()
    if "dax" in q:
        return "Use DAX measures for calculations. SUM, AVERAGE, and CALCULATE are the most common functions."
    elif "data model" in q or "star schema" in q:
        return "Create a star schema with fact and dimension tables. Use relationships to connect them."
    elif "rls" in q or "security" in q:
        return "Set up Row-Level Security in the Modeling tab. Create roles with DAX filters."
    elif "incremental" in q or "refresh" in q:
        return "Use incremental refresh for large datasets. Set up RangeStart and RangeEnd parameters."
    elif "deployment" in q or "pipeline" in q:
        return "Use deployment pipelines with Dev, Test, and Prod stages."
    elif "power query" in q or "transform" in q:
        return "Transform data in Power Query editor. Filter and clean before loading."
    elif "composite" in q or "directquery" in q:
        return "Use Import mode for small data, DirectQuery for large data."
    else:
        return "Use Power BI Desktop for development and the Service for sharing."


register("power_bi_engineer", _pbi_strong, _pbi_weak)


# ══════════════════════════════════════════════════════════════════════════
# AZURE DATA ARCHITECT
# ══════════════════════════════════════════════════════════════════════════

def _azure_arch_strong(question: str) -> str:
    q = question.lower()
    if "enterprise" in q and ("retail" in q or "platform" in q or "design" in q):
        return (
            "## Enterprise Data Platform Architecture for Retail\n\n"
            "### Ingestion Layer\n"
            "- **Real-time**: Azure Event Hubs (POS data, 500+ stores) → Databricks Structured Streaming / Stream Analytics\n"
            "- **Batch**: Azure Data Factory with managed IR for supply chain feeds (daily/hourly schedules)\n\n"
            "### Storage Layer — Medallion on ADLS Gen2\n"
            "- **Bronze**: Raw data partitioned by source/date in Delta format\n"
            "- **Silver**: Cleansed, deduplicated, conformed data with schema enforcement\n"
            "- **Gold**: Star schemas and aggregates for Power BI and data science\n"
            "- Partitioning: by store_region/date for optimal query performance at scale\n\n"
            "### Processing Layer\n"
            "- **Databricks** for heavy transformations, ML workloads\n"
            "- **Synapse Serverless** for ad-hoc SQL exploration of Bronze/Silver layers\n\n"
            "### Serving Layer\n"
            "- **Power BI** with Import mode on Gold aggregates, DirectQuery for real-time dashboards\n"
            "- **Synapse Dedicated Pool** for high-concurrency BI if needed\n\n"
            "### Governance & Security\n"
            "- **Microsoft Purview** for catalog, lineage, and sensitivity labels\n"
            "- RBAC per workspace: data engineers (Bronze/Silver), analysts (Gold), data science (ML workspace)\n"
            "- Private endpoints for all services, managed identities throughout"
        )
    elif "fabric" in q and ("standalone" in q or "versus" in q or "vs" in q or "differ" in q or "choose" in q):
        return (
            "## Fabric vs Standalone Azure Services\n\n"
            "### Cost Model\n"
            "- **Fabric**: Single capacity (CU) billing — all workloads share one pool\n"
            "- **Standalone**: Separate billing per service (Databricks DBUs, Synapse DWUs, ADF pipeline runs)\n"
            "- Fabric is simpler to budget; standalone gives more granular cost control\n\n"
            "### Governance\n"
            "- **Fabric**: Built-in OneLake governance, integrated lineage, endorsement\n"
            "- **Standalone**: Requires separate Purview setup, more configuration\n\n"
            "### Flexibility & Portability\n"
            "- **Standalone**: Multi-cloud possible (Databricks on AWS/GCP), deep customization\n"
            "- **Fabric**: Microsoft-only, less escape hatch, but rapid evolution\n\n"
            "### When to Choose:\n"
            "| Criteria | Fabric | Standalone |\n|---|---|---|\n"
            "| Team wants simplicity | Yes | No |\n"
            "| Multi-cloud required | No | Yes |\n"
            "| Regulated/complex env | Consider | Yes |\n"
            "| Budget predictability | Yes (CU) | Harder |\n"
            "| Deep Spark customization | Limited | Full control |"
        )
    elif "purview" in q or "governance" in q and "catalog" in q:
        return (
            "## Data Governance with Microsoft Purview\n\n"
            "### Data Catalog\n"
            "- Auto-scan ADLS Gen2, Synapse, Databricks, SQL databases for asset discovery\n"
            "- 200+ datasets organized by business domain with domain-level ownership\n\n"
            "### Data Lineage\n"
            "- End-to-end lineage from source → ADF pipelines → transformations → serving\n"
            "- Integration with Databricks notebook lineage via OpenLineage\n\n"
            "### Classification & Sensitivity\n"
            "- Auto-classify PII (names, SSN, email) with built-in classifiers\n"
            "- Apply sensitivity labels (Confidential, Internal, Public) with downstream enforcement\n\n"
            "### Business Glossary\n"
            "- Domain-specific terms owned by data stewards per business unit\n"
            "- Link glossary terms to physical assets for business-technical mapping\n\n"
            "### Access Policies\n"
            "- Purview access policies integrated with ADLS Gen2 RBAC\n"
            "- Self-serve data access requests with approval workflows"
        )
    elif "data mesh" in q:
        return (
            "## Data Mesh Architecture on Azure\n\n"
            "### Core Principles\n"
            "1. **Domain Ownership**: Each business domain owns its data end-to-end\n"
            "2. **Data as a Product**: Published datasets with SLAs, schema contracts, quality metrics\n"
            "3. **Self-Serve Platform**: Central team provides templates, policies, and tooling\n"
            "4. **Federated Governance**: Purview as the cross-domain governance layer\n\n"
            "### Azure Implementation\n"
            "- **Per-domain**: Separate subscriptions or Fabric workspaces with domain team ownership\n"
            "- **Data Products**: Published as Delta tables with defined schemas and access policies\n"
            "- **Platform Team**: Provides landing zone templates (Bicep/Terraform), CI/CD pipelines, monitoring\n"
            "- **Purview**: Federated catalog across all domains, lineage, glossary\n\n"
            "### Data Product Contract\n"
            "Each data product defines: schema version, refresh SLA, quality thresholds, ownership, access policy."
        )
    elif "zero trust" in q or ("security" in q and "pii" in q):
        return (
            "## Zero Trust Security for Azure Data Platform\n\n"
            "### Principles Applied\n"
            "- **Verify explicitly**: All access authenticated via Entra ID + MFA\n"
            "- **Least privilege**: RBAC per resource, PIM for admin access\n"
            "- **Assume breach**: Network segmentation, monitoring, encryption everywhere\n\n"
            "### Network Security\n"
            "- **Private endpoints** for ALL PaaS services (ADLS, Synapse, Databricks, Key Vault)\n"
            "- No public endpoints — Azure Policy enforces this at subscription level\n"
            "- NSG rules restrict traffic between subnets\n\n"
            "### Identity & Access\n"
            "- **Managed identities** for all service-to-service auth (no keys/passwords)\n"
            "- Conditional Access policies for user access\n"
            "- Regular access reviews (quarterly)\n\n"
            "### Data Protection\n"
            "- **CMK** (Customer-Managed Keys) in Azure Key Vault for encryption at rest\n"
            "- TLS 1.2+ enforced for all data in transit\n"
            "- Dynamic data masking for PII columns\n\n"
            "### EU Data Residency\n"
            "- Azure Policy enforces region pinning (EU West/North) for EU customer data\n"
            "- Geo-replication disabled where GDPR requires"
        )
    elif "finops" in q or ("cost" in q and ("150k" in q or "optim" in q or "strateg" in q)):
        return (
            "## FinOps Strategy for Azure Data Platform\n\n"
            "### Visibility\n"
            "- **Azure Cost Management** with budgets and alerts per subscription/resource group\n"
            "- **Tagging standards**: env (prod/dev), domain (sales/supply-chain), project, cost-center\n"
            "- Monthly cost reviews with domain owners (showback reports)\n\n"
            "### Optimization\n"
            "- **Reserved capacity**: 1-3 year reservations for predictable workloads (Synapse DWUs, Databricks)\n"
            "- **Auto-pause**: Synapse dedicated pools, Databricks clusters with auto-termination\n"
            "- **Right-sizing**: Review VM SKUs quarterly based on utilization metrics\n"
            "- **Spot instances**: For fault-tolerant Databricks batch jobs (60-90% savings)\n\n"
            "### Governance\n"
            "- Azure Policy to enforce allowed SKUs and prevent over-provisioning\n"
            "- Chargeback model: costs allocated to business domains based on consumption\n"
            "- Quarterly FinOps review with architecture and finance teams"
        )
    elif "teradata" in q or "migrat" in q:
        return (
            "## Teradata to Azure Migration Architecture\n\n"
            "### Phased Approach\n"
            "1. **Assess**: Inventory schemas, query patterns, data volumes (50TB), dependencies\n"
            "2. **Migrate**: Schema conversion + data movement + validation\n"
            "3. **Optimize**: Refactor for cloud-native patterns post-migration\n\n"
            "### Target Options\n"
            "| Target | Best For |\n|---|---|\n"
            "| Synapse Dedicated Pool | Lift-and-shift SQL workloads, familiar T-SQL |\n"
            "| Databricks Lakehouse | Modern lakehouse, Delta Lake, ML integration |\n"
            "| Fabric Warehouse | Integrated analytics, simplest operations |\n\n"
            "### Migration Tooling\n"
            "- **Schema/DDL**: Azure Database Migration Service or manual conversion scripts\n"
            "- **Data**: ADF Copy Activity (for bulk), Striim or Qlik (for CDC/continuous)\n"
            "- **Validation**: Row counts, checksums, query result comparison\n\n"
            "### Parallel Run\n"
            "Run Teradata and Azure in parallel for 4-8 weeks. Compare query results before cutover."
        )
    elif "disaster" in q or "rpo" in q or "rto" in q or "dr" in q:
        return (
            "## Disaster Recovery Strategy (RPO 1h / RTO 4h)\n\n"
            "### Storage (ADLS Gen2)\n"
            "- **GZRS** (Geo-Zone-Redundant Storage) for cross-region durability\n"
            "- RPO: ~15 minutes for async geo-replication (exceeds 1h requirement)\n\n"
            "### Compute Recovery\n"
            "- Databricks: Workspace config in Git/Terraform, redeploy to paired region\n"
            "- Synapse: ARM templates for workspace, dedicated pool restore from geo-backup\n"
            "- ADF: Git-integrated, redeploy pipelines to DR region\n\n"
            "### Automated Failover\n"
            "- Azure Traffic Manager or Front Door for endpoint failover\n"
            "- Runbooks in Azure Automation for DR orchestration\n"
            "- **Test quarterly**: Simulate failover to validate RTO meets 4h target\n\n"
            "### Paired Regions\n"
            "Use Azure Paired Regions (e.g., East US / West US) for compliance with data residency."
        )
    elif "well-architected" in q or "waf" in q or "five pillars" in q:
        return (
            "## Well-Architected Framework Review\n\n"
            "### 1. Reliability\n"
            "- Is ADLS Gen2 configured with GRS/GZRS? What's your RPO/RTO?\n"
            "- Databricks cluster auto-restart on failure? ADF retry policies?\n\n"
            "### 2. Security\n"
            "- Private endpoints on all services? Managed identities (no shared keys)?\n"
            "- Data encryption: CMK or Microsoft-managed? Key rotation schedule?\n\n"
            "### 3. Cost Optimization\n"
            "- Auto-pause enabled for Synapse/Databricks non-prod?\n"
            "- Reserved capacity for production workloads? Tagging for cost allocation?\n\n"
            "### 4. Operational Excellence\n"
            "- Monitoring: Azure Monitor dashboards, alerting on pipeline failures?\n"
            "- IaC: ARM/Bicep/Terraform for all resources? Git-backed ADF/Databricks?\n\n"
            "### 5. Performance Efficiency\n"
            "- Partitioning strategy on ADLS (date/region)? Databricks cluster sizing?\n"
            "- Power BI: Import vs DirectQuery? Aggregation tables for large datasets?"
        )
    elif "public endpoint" in q or ("public" in q and "pii" in q):
        return (
            "## Do NOT Use Public Endpoints for PII Data\n\n"
            "**This is a critical security risk.** Public endpoints expose your data lake to the internet.\n\n"
            "### Risks\n"
            "- Susceptible to brute-force, credential stuffing, and network-level attacks\n"
            "- Violates Zero Trust principle of 'assume breach'\n"
            "- May violate GDPR, HIPAA, or industry compliance requirements\n\n"
            "### Required: Private Endpoints\n"
            "- Deploy **private endpoints** for ADLS Gen2 and all connected services\n"
            "- Disable public network access on the storage account\n"
            "- Use **Azure Policy** (`Deny-PublicEndpoint`) to prevent future public endpoint creation\n\n"
            "### Defense-in-Depth\n"
            "Private endpoints + NSG rules + managed identities + encryption + Purview access policies."
        )
    elif "recommend" in q and len(q) < 60:
        return (
            "I'd love to help design your data platform, but I need more context first:\n\n"
            "1. **Data volume & velocity**: How much data? Real-time or batch?\n"
            "2. **Team size & skills**: How many engineers? SQL-heavy or Spark/Python?\n"
            "3. **Compliance**: Any regulatory requirements (GDPR, HIPAA, SOX, industry-specific)?\n"
            "4. **Budget**: What's the target monthly spend? Any existing Azure commitments?\n"
            "5. **Timeline**: Greenfield build or migration from existing platform?\n"
            "6. **Consumers**: Who uses the data? BI analysts, data scientists, applications?\n\n"
            "Once I understand these, I can recommend the right architecture pattern."
        )
    else:
        return (
            "As an Azure Data Architect, I focus on enterprise-scale data platform design "
            "aligned with the Azure Well-Architected Framework. My recommendations always "
            "address security, governance, cost, reliability, and performance.\n\n"
            "Could you provide more details about your specific architecture challenge?"
        )


def _azure_arch_weak(question: str) -> str:
    q = question.lower()
    if "enterprise" in q or "platform" in q: return "Use ADLS Gen2 for storage and Databricks for processing."
    elif "fabric" in q: return "Fabric is the newer option. Standalone gives more control."
    elif "purview" in q or "governance" in q: return "Use Purview for data cataloging and governance."
    elif "data mesh" in q: return "Data mesh gives domains ownership of their data."
    elif "zero trust" in q or "security" in q: return "Use private endpoints and managed identities."
    elif "cost" in q or "finops" in q: return "Use reserved capacity and auto-pause to save costs."
    elif "teradata" in q or "migrat" in q: return "Migrate to Synapse or Databricks using ADF."
    elif "disaster" in q or "dr" in q: return "Use geo-redundant storage and backup your configs."
    elif "well-architected" in q: return "Review against the five pillars of the Well-Architected Framework."
    elif "public" in q: return "Don't use public endpoints for sensitive data."
    else: return "Use Azure services for your data platform needs."


register("azure_data_architect", _azure_arch_strong, _azure_arch_weak)


# ══════════════════════════════════════════════════════════════════════════
# CLINICAL TRIALS DATA ENGINEER
# ══════════════════════════════════════════════════════════════════════════

def _clinical_de_strong(question: str) -> str:
    q = question.lower()
    if "audit trail" in q and ("edc" in q or "21 cfr" in q or "part 11" in q):
        return (
            "## Audit Trails for EDC-to-ADLS Gen2 Pipeline (21 CFR Part 11)\n\n"
            "Implement immutable, append-only storage using ADLS Gen2 immutability policies "
            "for all audit records. Per FDA 21 CFR Part 11 §11.10(e), every audit entry must "
            "capture: original value, new value, user ID, UTC timestamp, and reason for change. "
            "Audit records must not be modifiable or deletable by any role, including system "
            "administrators.\n\n"
            "Use managed identities (Entra ID) for all service-level actions — no shared "
            "accounts — per §11.10(d) unique user identification requirements. All pipeline "
            "actions must be attributable to an individual identity.\n\n"
            "Follow ALCOA+ principles throughout: every record must be Attributable, Legible, "
            "Contemporaneous, Original, and Accurate. Store raw EDC extracts as immutable "
            "Bronze-layer snapshots so the original data is always preserved."
        )
    elif "hipaa" in q and ("phi" in q or "encryption" in q or "de-identification" in q):
        return (
            "## HIPAA-Compliant PHI Protection in Azure/Fabric\n\n"
            "Apply the Safe Harbor de-identification method per HIPAA §164.514(b), removing "
            "all 18 HIPAA identifiers (names, dates, MRNs, geographic data, etc.) before data "
            "enters the analytics layer. Use AES-256 encryption at rest for every data store "
            "containing PHI, backed by customer-managed keys in Azure Key Vault.\n\n"
            "Enforce TLS 1.2+ for all data transfers — EDC-to-Azure, inter-service, and user "
            "access — with legacy TLS versions explicitly disabled. Maintain comprehensive "
            "access logging for all PHI resources with a minimum 6-year retention period to "
            "satisfy HIPAA audit requirements.\n\n"
            "Implement automated PHI scanning on all string fields to catch residual "
            "identifiers that survive the de-identification pipeline."
        )
    elif "sdtm" in q and ("transformation" in q or "validation" in q or "conformance" in q or "ig" in q):
        return (
            "## SDTM Transformation & Validation in Databricks/Spark\n\n"
            "Target full conformance with CDISC SDTM IG v3.4. Enforce variable naming "
            "conventions, labels, data types, and length requirements per the IG. Maintain a "
            "comprehensive mapping specification documenting each source-to-target "
            "transformation rule.\n\n"
            "Run Pinnacle 21 (OpenCDISC) validation with zero structural errors as the "
            "acceptance criterion before any downstream processing. Timing variables must "
            "follow strict rules: VISIT, VISITNUM populated, --DTC in ISO 8601 format, and "
            "--DY calculated from RFSTDTC.\n\n"
            "Achieve unit test coverage >95% of mapping rules with record count reconciliation "
            "between source and target datasets at every transformation step."
        )
    elif "adam" in q and ("adsl" in q or "bds" in q or "occds" in q or "derived" in q or "population" in q):
        return (
            "## Building ADaM Datasets (ADSL, BDS, OCCDS) from SDTM\n\n"
            "Follow ADaM IG v1.3 dataset structures: ADSL for subject-level data, BDS (Basic "
            "Data Structure) for longitudinal endpoints, and OCCDS for occurrence data such as "
            "adverse events. Key derived variables include AVAL, AVALC, CHG, PCHG, BASE, "
            "ABLFL, and ANL01FL — each with documented derivation logic.\n\n"
            "Population flags (SAFFL, ITTFL, FASFL, PPROTFL, COMPLFL) must match SAP "
            "definitions exactly. Generate define.xml v2.1 with computational algorithms for "
            "every derived variable.\n\n"
            "Validate via double-programming: an independent programmer re-derives 100% of "
            "ADaM outputs, with cell-by-cell comparison to the primary output."
        )
    elif "meddra" in q or "whodrug" in q or "medical coding" in q or "coding" in q:
        return (
            "## MedDRA and WHODrug Coding in the Clinical Data Pipeline\n\n"
            "MedDRA coding follows a five-level hierarchy: LLT (Lowest Level Term) -> PT "
            "(Preferred Term) -> HLT (High Level Term) -> HLGT (High Level Group Term) -> "
            "SOC (System Organ Class). For concomitant medications, use WHODrug Global with "
            "ATC classification.\n\n"
            "Track dictionary version in dataset metadata and document auto-coding versus "
            "manual coding decisions. For dictionary version upgrades, remap all existing "
            "terms with a before/after comparison to ensure no loss of granularity.\n\n"
            "Reference ICH E2B(R3) for adverse event reporting standards. Maintain a coding "
            "review log capturing coder ID, review date, and approval per ALCOA+ principles."
        )
    elif "edc" in q and ("ingestion" in q or "pipeline" in q or "incremental" in q or "medidata" in q or "rave" in q):
        return (
            "## EDC Ingestion Pipeline: Medidata Rave to ADLS Gen2\n\n"
            "Use incremental/delta loads based on EDC audit trail timestamps — never full "
            "reloads. Implement an error quarantine pattern: malformed records are routed to "
            "an error lakehouse while the pipeline continues processing valid data.\n\n"
            "Handle schema evolution from protocol amendments gracefully — new fields must be "
            "absorbed without data loss or pipeline failure. Perform record count reconciliation "
            "between EDC source and landing zone within 0.01% tolerance.\n\n"
            "The landing zone must preserve full history: original records are never overwritten, "
            "satisfying the ALCOA+ 'Original' principle. Partition by ingestion date and site "
            "for efficient downstream queries."
        )
    elif "sas" in q and ("spark" in q or "pyspark" in q or "migrating" in q or "validate" in q):
        return (
            "## Validating SAS-to-PySpark ADaM Migration\n\n"
            "Compare numeric values to a minimum of 10 decimal places between SAS reference "
            "outputs and Spark-generated datasets. Be aware of SAS vs Python date arithmetic "
            "differences — SAS dates are days since 1960-01-01 while Python uses different "
            "epoch conventions.\n\n"
            "Apply a double-programming approach: independent re-derivation serves as the "
            "gold-standard validation method. Run variable-by-variable comparison with "
            "pre-defined tolerance thresholds (integers: exact match; percentages: within "
            "0.1%; continuous values: within 0.01%).\n\n"
            "Document any numerical differences exceeding tolerance with a root cause "
            "explanation. All comparison reports must be archived for regulatory audit."
        )
    elif "data quality" in q or ("quality" in q and "checks" in q):
        return (
            "## Data Quality Checks Across Pipeline Stages\n\n"
            "Implement checks across four dimensions at every stage (landing, SDTM, ADaM): "
            "completeness, conformance, plausibility, and uniqueness. Critical DQ failures "
            "must halt downstream processing — never propagate bad data.\n\n"
            "Build DQ dashboards showing missing data rates per variable, site, and visit. "
            "Conformance rules include range checks, controlled terminology validation (using "
            "CDISC CT), and cross-field logic (e.g., death date after last dose date).\n\n"
            "Monitor plausibility via outlier detection and site-level pattern comparison "
            "against study-wide distributions. Flag sites with statistically anomalous data "
            "patterns for targeted source data verification."
        )
    elif "unblinding" in q or "treatment assignment" in q or "blinding" in q:
        return (
            "## Unblinding Controls in Fabric/Azure\n\n"
            "Store the randomization table in a separate ADLS container with dedicated Entra "
            "ID access controls. Maintain strict workspace isolation: the unblinded Fabric "
            "workspace must be physically separated from blinded workspaces.\n\n"
            "Blinded team members receive ADaM datasets with treatment columns removed or "
            "masked — not merely access-controlled. Implement an emergency unblinding workflow "
            "with a documented approval chain, single-subject reveal capability, and full "
            "audit documentation per ICH E6(R2) §5.5.2.\n\n"
            "All access attempts by blinded personnel to unblinded data must be denied and "
            "logged. Review these access logs quarterly."
        )
    elif "eu" in q or "gdpr" in q or "cross-border" in q or "erasure" in q:
        return (
            "## EU-to-US Clinical Data Transfer & GDPR Compliance\n\n"
            "Use the EU-US Data Privacy Framework or Standard Contractual Clauses as the "
            "legal transfer mechanism. Complete a Transfer Impact Assessment (TIA) per trial "
            "before any data flows.\n\n"
            "Apply pseudonymization and AES-256 encryption before cross-border transfer. "
            "For subject withdrawal (right to erasure), propagate the withdrawal through all "
            "pipeline stages with anonymization completed within 30 days per GDPR Art. 17.\n\n"
            "Enforce data minimization per GDPR Art. 5(1)(c): collect and process only "
            "protocol-required data elements. Use Azure Policy to enforce data residency "
            "constraints for EU-only datasets."
        )
    elif "ai" in q and ("phi" in q or "audit" in q or "governance" in q):
        return (
            "## AI Governance for Clinical Data Teams\n\n"
            "Deploy a PHI detection layer on all AI outputs to prevent surface, generation, "
            "or inclusion of protected health information. Log every AI interaction: user ID, "
            "session ID, full prompt, full response, model version, and UTC timestamp.\n\n"
            "AI interaction logs must be immutable and retained per DCRI policy, satisfying "
            "21 CFR Part 11 §11.10(e) requirements. Run prompt injection testing with "
            "adversarial prompts to validate PHI guardrails.\n\n"
            "Implement confidence scoring for AI responses with automatic escalation to a "
            "human reviewer when confidence falls below a defined threshold."
        )
    elif "load" in q and len(q) < 40:
        return (
            "Great question — but I need a few clarifications before recommending an approach:\n\n"
            "1. **Which data source?** EDC system (Rave, Veeva), lab feed, safety database?\n"
            "2. **Destination?** Landing zone, SDTM, ADaM layer?\n"
            "3. **Load type?** Initial full load or incremental?\n\n"
            "Each scenario has different requirements for audit trails, reconciliation, and "
            "validation under 21 CFR Part 11. Could you provide protocol-specific details?"
        )
    else:
        return (
            "## Clinical Data Engineering Guidance\n\n"
            "For clinical trial data pipelines, key considerations include regulatory "
            "compliance (21 CFR Part 11, HIPAA), CDISC standards (SDTM IG v3.4, ADaM IG "
            "v1.3), data quality enforcement across all pipeline stages, and ALCOA+ "
            "principles for audit trail integrity.\n\n"
            "Could you clarify which specific aspect of the clinical data pipeline you need "
            "guidance on? I can address EDC ingestion, SDTM/ADaM transformations, medical "
            "coding, SAS-to-Spark migration, unblinding controls, or cross-border transfers."
        )


def _clinical_de_weak(question: str) -> str:
    q = question.lower()
    if "audit trail" in q:
        return "Set up logging for your pipeline to track changes. Make sure you save who changed what and when."
    elif "hipaa" in q or "phi" in q:
        return "Encrypt your data and remove personal information before analysis. Use secure storage."
    elif "sdtm" in q:
        return "Follow CDISC standards for your SDTM datasets. Run validation before submission."
    elif "adam" in q:
        return "Build ADaM datasets from SDTM with the required derived variables and population flags."
    elif "meddra" in q or "coding" in q:
        return "Use MedDRA for adverse event coding and WHODrug for medications. Keep track of dictionary versions."
    elif "edc" in q or "ingestion" in q:
        return "Set up an ingestion pipeline from your EDC system. Use incremental loads for efficiency."
    elif "sas" in q and "spark" in q:
        return "Compare SAS and Spark outputs carefully. Check numeric precision and date handling differences."
    elif "data quality" in q or "quality" in q:
        return "Add data quality checks at each stage of your pipeline. Stop processing if critical issues are found."
    elif "unblinding" in q or "blinding" in q:
        return "Keep unblinded data separate from blinded data. Restrict access to authorized personnel only."
    elif "gdpr" in q or "eu" in q:
        return "Use approved transfer mechanisms for EU data. Handle withdrawal requests promptly."
    elif "ai" in q:
        return "Make sure AI tools don't expose patient data. Log all AI interactions for audit purposes."
    else:
        return "Follow best practices for clinical data engineering. Ensure regulatory compliance throughout."


register("clinical_data_engineer", _clinical_de_strong, _clinical_de_weak)


# ══════════════════════════════════════════════════════════════════════════
# CLINICAL TRIALS REPORTING ENGINEER
# ══════════════════════════════════════════════════════════════════════════

def _clinical_rpt_strong(question: str) -> str:
    q = question.lower()
    if "dsmb" in q and ("safety" in q or "report" in q or "automate" in q):
        return (
            "## Automating DSMB Safety Report Generation\n\n"
            "DSMB reports must include: AE summary by SOC/PT per treatment arm, SAE listings, "
            "enrollment summary, and protocol deviation counts. Create an immutable data "
            "lock/snapshot in a dedicated ADLS container before each report cycle, recording "
            "a timestamp and cryptographic hash for reproducibility verification.\n\n"
            "Report generation must run exclusively in the unblinded workspace — blinded "
            "personnel must have zero access to DSMB generation pipelines or outputs. "
            "Regeneration from the same snapshot must produce byte-identical output "
            "(verified by checksum match).\n\n"
            "Distribute via a secure portal with access logging, not email. Per 21 CFR Part "
            "11 §11.10(e), all generation and distribution actions must be audit-logged with "
            "user identity and timestamp."
        )
    elif "safety signal" in q or ("sae" in q and ("rate" in q or "threshold" in q or "alert" in q)):
        return (
            "## Real-Time Safety Signal Detection System\n\n"
            "Monitor SAE rates with both site-specific and study-wide thresholds. Configure "
            "per-protocol thresholds (not hardcoded) — for example, flag when a site's SAE "
            "rate exceeds the study-wide mean by 2 standard deviations.\n\n"
            "Deliver alerts to the medical monitor within 1 hour per ICH E6(R2) §5.17. Track "
            "SUSAR (Suspected Unexpected Serious Adverse Reaction) reporting timelines to "
            "ensure 7-day (fatal/life-threatening) and 15-day (other serious) deadlines are "
            "met per ICH E2A.\n\n"
            "Maintain a complete audit trail for every safety alert: who was notified, when, "
            "acknowledgment timestamp, and what corrective action was taken. Integrate with "
            "the DSMB reporting pipeline for seamless escalation."
        )
    elif "double-programming" in q or ("tlf" in q and ("verification" in q or "tolerance" in q or "accuracy" in q)):
        return (
            "## Double-Programming Verification for Statistical TLFs\n\n"
            "Primary programmer and independent QC programmer produce outputs separately "
            "with no code sharing. Apply strict tolerance thresholds: integers require exact "
            "match, percentages within 0.1%, and continuous values within 0.01%.\n\n"
            "Run cell-by-cell comparison between primary and QC outputs. Verify denominator "
            "populations (correct N for each treatment arm and subgroup) as a prerequisite "
            "before cell comparison.\n\n"
            "Document and resolve ALL discrepancies to root cause before sign-off — no "
            "exceptions regardless of magnitude. A 0.3% percentage difference exceeds the "
            "0.1% tolerance and must be investigated. Per 21 CFR Part 11, retain both primary "
            "and QC outputs with electronic signatures."
        )
    elif "power bi" in q and ("paginated" in q or "tlf" in q or "gxp" in q):
        return (
            "## Power BI Paginated Reports for Clinical TLFs (GxP)\n\n"
            "Use paginated reports (not interactive Power BI) for pixel-perfect TLF rendering "
            "suitable for regulatory submission. Enforce pagination rules: no orphaned rows, "
            "column headers repeat on each page, and footnotes are positioned correctly at "
            "page bottom.\n\n"
            "Parameterize by study, site, visit, and treatment arm. Trigger automatic refresh "
            "from pipeline completion events, displaying a data currency timestamp on every "
            "report page for GCP compliance.\n\n"
            "Test rendering with varying data volumes — sparse sites vs. large sites — to "
            "verify layout stability. Validate against the TLF shell specifications from the "
            "Statistical Analysis Plan (SAP)."
        )
    elif "ectd" in q or ("submission" in q and ("sdtm" in q or "adam" in q or "fda" in q)):
        return (
            "## Preparing SDTM/ADaM Datasets for FDA eCTD Submission\n\n"
            "Export all submission datasets in SAS Transport (XPT) v5 format — this is the "
            "only format accepted by FDA. Generate define.xml v2.1 and validate with Pinnacle "
            "21 (OpenCDISC) ensuring zero errors.\n\n"
            "Prepare the ADRG (Analysis Data Reviewer's Guide) including: dataset inventory, "
            "derivation methodology for all ADaM variables, and SAP crosswalk mapping each "
            "table/figure to its source ADaM dataset.\n\n"
            "Follow eCTD folder structure requirements (Module 5) and respect file size "
            "limits. Run Pinnacle 21 full submission validation as the final gate before "
            "packaging. All outputs must conform to CDISC SDTM IG v3.4 and ADaM IG v1.3."
        )
    elif "version" in q and ("report" in q or "tlf" in q or "distribution" in q):
        return (
            "## Report Versioning & Distribution (21 CFR Part 11)\n\n"
            "Auto-increment version numbers for each TLF package release. Store all previous "
            "versions in immutable archive storage — no version may be deleted or modified "
            "after finalization.\n\n"
            "Implement an approval workflow before finalization requiring electronic signature "
            "with meaning (e.g., 'Reviewed and Approved') per 21 CFR Part 11 §11.50. Provide "
            "version comparison capability showing differences between consecutive versions.\n\n"
            "Log all distribution events: who received which version, when, and via what "
            "channel. Use a secure portal rather than email for DSMB deliverables containing "
            "unblinded data."
        )
    elif "dashboard" in q and ("ae" in q or "sae" in q or "safety" in q):
        return (
            "## AE/SAE Safety Dashboard in Fabric/Power BI\n\n"
            "Architect the data flow as: ADaM AE dataset -> incremental refresh -> Power BI "
            "semantic model -> dashboard. Only authorized safety team members may view "
            "unblinded AE summaries — enforce via Entra ID security groups.\n\n"
            "Implement conditional alerting when site-specific SAE rates exceed the study-wide "
            "mean by N standard deviations (configurable per protocol). Display a data currency "
            "timestamp (last refresh) on every dashboard page for GCP compliance.\n\n"
            "Apply Row-Level Security (RLS) so site monitors see only their assigned sites. "
            "Per HIPAA §164.514(b), ensure no PHI is surfaced in dashboard visualizations."
        )
    elif "email" in q and "dsmb" in q:
        return (
            "## Secure DSMB Report Distribution\n\n"
            "DSMB reports contain unblinded treatment data and must NOT be distributed via "
            "email attachments. Email lacks the audit trail required for 21 CFR Part 11 "
            "compliance and cannot guarantee delivery confirmation or access control.\n\n"
            "Use a secure portal or encrypted file share with identity-verified access. Log "
            "every download: user identity, timestamp, document version, and IP address. "
            "Implement version control for all DSMB deliverables.\n\n"
            "If stakeholders insist on email, at minimum use encrypted attachments with "
            "separate password delivery, but strongly recommend migrating to a compliant "
            "secure distribution channel."
        )
    elif "discrepancy" in q or ("doesn't match" in q or "difference" in q or "skip" in q):
        return (
            "## Investigating TLF Discrepancies — No Exceptions\n\n"
            "ALL discrepancies between primary and QC outputs must be investigated to root "
            "cause, regardless of magnitude. A 0.3% difference on a percentage exceeds the "
            "standard 0.1% tolerance threshold and cannot be dismissed.\n\n"
            "Unexplained discrepancies may indicate systematic errors affecting other outputs. "
            "Investigate by comparing intermediate derivation steps, population definitions, "
            "and rounding logic between primary and QC programs.\n\n"
            "If a tolerance waiver is granted, document it formally with justification, "
            "approver signature, and impact assessment. FDA reviewers routinely flag "
            "unexplained differences during submission review."
        )
    elif "committee" in q and "report" in q:
        return (
            "I need to clarify several points before recommending an approach:\n\n"
            "1. **Which committee?** DSMB/DMC, IRB/EC, steering committee, or sponsor?\n"
            "2. **Scheduled or ad-hoc?** Is this a planned interim analysis or an urgent request?\n"
            "3. **Unblinded data needed?** This determines security and workspace requirements.\n"
            "4. **Data cut-off date?** Do we need a formal data lock?\n\n"
            "Each committee type has different content requirements, blinding rules, and "
            "distribution protocols under ICH GCP E6(R2)."
        )
    else:
        return (
            "## Clinical Reporting Engineering Guidance\n\n"
            "For clinical trial reporting, key considerations include DSMB safety report "
            "automation, TLF double-programming verification, eCTD submission preparation "
            "(SDTM IG v3.4, ADaM IG v1.3, define.xml v2.1), and 21 CFR Part 11-compliant "
            "versioning and distribution.\n\n"
            "Could you clarify which reporting area you need help with? I can address DSMB "
            "reports, TLF generation, safety dashboards, eCTD packaging, or report versioning."
        )


def _clinical_rpt_weak(question: str) -> str:
    q = question.lower()
    if "dsmb" in q:
        return "Generate DSMB reports with AE summaries by treatment arm. Use a data snapshot for reproducibility."
    elif "safety signal" in q or "sae" in q:
        return "Set up alerts when SAE rates exceed thresholds. Notify the medical monitor promptly."
    elif "double-programming" in q or "tlf" in q:
        return "Have two programmers create outputs independently and compare them. Investigate any differences."
    elif "power bi" in q or "paginated" in q:
        return "Use Power BI paginated reports for TLFs. Make sure pagination and headers work correctly."
    elif "ectd" in q or "submission" in q:
        return "Export datasets as XPT files and validate with Pinnacle 21. Prepare the define.xml and ADRG."
    elif "version" in q or "distribution" in q:
        return "Version your reports and keep an archive. Log who receives each version."
    elif "dashboard" in q:
        return "Build a Power BI dashboard for AE rates. Restrict access to authorized safety team members."
    elif "email" in q:
        return "Avoid emailing unblinded reports. Use a secure portal instead for better audit trails."
    elif "discrepancy" in q or "skip" in q or "difference" in q:
        return "Investigate all discrepancies regardless of size. Don't skip investigation even for small differences."
    elif "committee" in q:
        return "Which committee do you need the report for? Different committees have different requirements."
    else:
        return "Follow clinical reporting best practices. Ensure accuracy and regulatory compliance in all outputs."


register("clinical_reporting_engineer", _clinical_rpt_strong, _clinical_rpt_weak)


# ══════════════════════════════════════════════════════════════════════════
# CLINICAL TRIALS SECURITY & COMPLIANCE ENGINEER
# ══════════════════════════════════════════════════════════════════════════

def _clinical_sec_strong(question: str) -> str:
    q = question.lower()
    if "safe harbor" in q or ("de-identification" in q and ("analytics" in q or "phi" in q)):
        return (
            "## Safe Harbor De-identification for Clinical Trial Data\n\n"
            "Per HIPAA §164.514(b), remove or generalize all 18 Safe Harbor identifiers: "
            "names, geographic subdivisions smaller than state, dates (except year) for ages "
            "under 90, phone/fax numbers, email addresses, SSNs, MRNs, health plan numbers, "
            "account numbers, certificate/license numbers, VINs, device identifiers, URLs, "
            "IPs, biometric IDs, photos, and any unique identifying number.\n\n"
            "Dates must be shifted or generalized to year only; ages 90+ must be aggregated "
            "into a single category. Run automated de-identification validation scripts "
            "scanning all string fields for residual PHI patterns (regex for SSN, phone, "
            "email, date formats). The expert determination method (§164.514(a)) is an "
            "alternative when a statistical approach is needed.\n\n"
            "De-identification must occur BEFORE data enters the ADaM/analytics layer, not "
            "after. Document the de-identification process for audit readiness."
        )
    elif "pseudonymization" in q or ("key management" in q and "subject" in q):
        return (
            "## Pseudonymization & Key Management for Subject Identifiers\n\n"
            "Store pseudonymization keys in Azure Key Vault with PIM (Privileged Identity "
            "Management) access — only authorized data management personnel may access the "
            "key. Implement annual key rotation as the minimum policy, with automated rotation "
            "preferred.\n\n"
            "Apply dynamic data masking at query time for non-authorized viewers of PHI "
            "fields, so the underlying data remains intact but masked in query results. "
            "Per GDPR Art. 4(5), pseudonymization means processing such that data cannot be "
            "attributed to a specific subject without additional information kept separately.\n\n"
            "Reference HIPAA §164.514 for the relationship between pseudonymization and "
            "de-identification. Log every key access event for 21 CFR Part 11 audit trail "
            "compliance."
        )
    elif "unblinding" in q or ("double-blind" in q and ("control" in q or "architecture" in q)):
        return (
            "## Unblinding Control Architecture for Double-Blind Trials\n\n"
            "Store the randomization table in a separate, access-controlled ADLS container "
            "with Entra ID security groups. Implement Fabric workspace isolation: the "
            "unblinded workspace must be physically separated from blinded workspaces with "
            "no cross-workspace data sharing.\n\n"
            "Blinded ADaM datasets must have treatment columns removed or masked — access "
            "control alone is not sufficient. For emergency unblinding, implement a workflow: "
            "approval chain -> single-subject reveal -> audit log -> medical monitor "
            "notification. Emergency unblinding for one subject must NOT compromise the blind "
            "for other subjects.\n\n"
            "Per ICH E6(R2) §5.5.2, log all access attempts — including denied attempts by "
            "blinded personnel — with user identity, timestamp, and resource requested."
        )
    elif "encryption" in q and ("key" in q or "rest" in q or "transit" in q):
        return (
            "## Encryption Strategy for Clinical Trial Data\n\n"
            "Require AES-256 encryption at rest for all data stores containing PHI. Use "
            "customer-managed keys (CMK) stored in a FIPS 140-2 Level 2 HSM-backed Azure "
            "Key Vault — never Microsoft-managed keys for regulated clinical data.\n\n"
            "Enforce TLS 1.2+ for all data in transit with legacy TLS versions (1.0, 1.1) "
            "explicitly disabled via Azure Policy. Implement annual key rotation at minimum, "
            "with automated rotation configured in Key Vault.\n\n"
            "Document a break-glass procedure for key access during disaster recovery, "
            "including dual-control requirements (two authorized personnel) and post-event "
            "audit review. Per 21 CFR Part 11 §11.10(c), encryption protects records from "
            "unauthorized access."
        )
    elif "network" in q and ("security" in q or "nist" in q or "hipaa" in q):
        return (
            "## Network Security for Clinical Trial Azure Environment\n\n"
            "Implement VNet isolation: the clinical trial VNet must be separated from general "
            "corporate infrastructure. Configure NSG rules: no inbound from corporate network, "
            "outbound restricted to required endpoints only.\n\n"
            "Require private endpoints for ALL Azure PaaS services — no public endpoints for "
            "any resource containing PHI. Use VPN or ExpressRoute for EDC system connections "
            "(Rave, Veeva, etc.) rather than public internet.\n\n"
            "Per NIST 800-53 SC-7 (Boundary Protection), perform weekly vulnerability scanning "
            "with critical CVE patching within 72 hours. Document network architecture with "
            "data flow diagrams showing all ingress/egress points for HIPAA audit readiness."
        )
    elif ("eu" in q or "gdpr" in q) and ("transfer" in q or "cross-border" in q or "us" in q):
        return (
            "## GDPR-Compliant EU-to-US Clinical Data Transfer\n\n"
            "Use the EU-US Data Privacy Framework or Standard Contractual Clauses (SCCs) as "
            "the legal transfer mechanism. Complete a Transfer Impact Assessment (TIA) per "
            "trial before any data flows begin.\n\n"
            "Apply technical safeguards: encryption (AES-256) and pseudonymization BEFORE "
            "cross-border transfer, not after arrival. Enforce data residency via Azure Policy "
            "for EU-only datasets — disable geo-replication to prevent data from leaving the "
            "EU region.\n\n"
            "Implement transfer logging capturing source, destination, timestamp, and data "
            "categories for audit purposes. Per GDPR Art. 46, document the appropriate "
            "safeguards relied upon for each transfer."
        )
    elif "audit" in q and ("logging" in q or "log" in q or "21 cfr" in q):
        return (
            "## Audit Logging for 21 CFR Part 11 & HIPAA Compliance\n\n"
            "Implement immutable, append-only audit logs using ADLS immutability policies. "
            "Log every read/write/delete on PHI resources capturing: user identity, resource "
            "path, UTC timestamp, action performed, and source IP address.\n\n"
            "Include AI interaction logging: user ID, session ID, full prompt and response, "
            "model version, and timestamp. Per 21 CFR Part 11 §11.10(e), audit trails must "
            "be computer-generated and independently recorded.\n\n"
            "Enforce minimum 6-year log retention (HIPAA requirement), aligned with the "
            "15-year clinical data retention policy. Conduct quarterly access log reviews "
            "for compliance verification, with findings documented and signed off."
        )
    elif "role-based" in q or "rbac" in q or ("access control" in q and "pipeline" in q):
        return (
            "## Role-Based Access Control Across Clinical Pipeline Stages\n\n"
            "Define distinct Fabric workspace roles per pipeline stage (landing, SDTM, ADaM, "
            "reporting) with explicit permission boundaries. Data engineers cannot access "
            "unblinded ADaM datasets. Biostatisticians have read-only access to SDTM and "
            "read-write access to ADaM.\n\n"
            "Require Entra ID with MFA for all human users and managed identities for all "
            "service accounts — no shared credentials per 21 CFR Part 11 §11.10(d). "
            "Implement PIM (Privileged Identity Management) for time-limited elevation of "
            "privileged access.\n\n"
            "Review access grants quarterly and remove stale permissions. Document role "
            "definitions and permission matrices for regulatory inspection readiness."
        )
    elif "shared" in q and ("account" in q or "admin" in q or "credential" in q):
        return (
            "## Shared Accounts Are Non-Compliant\n\n"
            "Shared accounts violate 21 CFR Part 11 §11.10(d), which requires unique user "
            "identification for every individual. Every action in a regulated clinical data "
            "pipeline must be attributable to a specific person for audit trail integrity.\n\n"
            "Use managed identities (Entra ID) for service accounts — no shared passwords. "
            "For human users, assign individual Entra ID accounts with MFA. Use service "
            "principals with managed identity credentials for automated pipeline steps.\n\n"
            "Document this requirement in your platform SOP and enforce it via Azure Policy "
            "that blocks local account creation or shared credential usage."
        )
    elif "access" in q and "new team member" in q:
        return (
            "Before provisioning access, I need to clarify several points:\n\n"
            "1. **Role?** Data engineer, biostatistician, clinical data manager, medical monitor?\n"
            "2. **Blinded or unblinded access?** This determines workspace assignment.\n"
            "3. **Pipeline stages?** Landing, SDTM, ADaM, reporting — which stages?\n"
            "4. **Training complete?** Has role-specific GCP and platform training been verified per SOP?\n\n"
            "Access provisioning in clinical trials requires documented approval and training "
            "verification per ICH E6(R2) before granting any data access."
        )
    else:
        return (
            "## Clinical Security & Compliance Guidance\n\n"
            "For clinical trial security, key pillars include: HIPAA §164.514(b) Safe Harbor "
            "de-identification, 21 CFR Part 11 audit trails and electronic signatures, "
            "unblinding controls per ICH E6(R2), NIST 800-53 network security, and GDPR "
            "cross-border transfer safeguards.\n\n"
            "Could you clarify which security domain you need guidance on? I can address "
            "PHI protection, encryption, access control, network security, audit logging, "
            "or cross-border compliance."
        )


def _clinical_sec_weak(question: str) -> str:
    q = question.lower()
    if "safe harbor" in q or "de-identification" in q:
        return "Remove personal identifiers from the data before analysis. Use the HIPAA Safe Harbor method."
    elif "pseudonymization" in q:
        return "Replace real identifiers with pseudonyms. Store the mapping key securely in a key vault."
    elif "unblinding" in q or "double-blind" in q:
        return "Keep treatment assignment data separate. Only allow authorized personnel to access unblinded data."
    elif "encryption" in q:
        return "Use AES-256 encryption at rest and TLS for data in transit. Manage keys in Azure Key Vault."
    elif "network" in q:
        return "Isolate your clinical environment on a separate network. Use private endpoints for Azure services."
    elif "gdpr" in q or "transfer" in q or "eu" in q:
        return "Use Standard Contractual Clauses for EU data transfers. Encrypt data before sending it."
    elif "audit" in q:
        return "Enable audit logging for all data access. Keep logs immutable and retain them for at least six years."
    elif "rbac" in q or "access control" in q:
        return "Set up role-based access control. Give each team member only the access they need."
    elif "shared" in q and "account" in q:
        return "Don't use shared accounts. Each person should have their own credentials for accountability."
    elif "team member" in q or "access" in q:
        return "What role does the new team member have? Different roles need different levels of access."
    else:
        return "Follow security best practices for clinical data. Ensure compliance with HIPAA and 21 CFR Part 11."


register("clinical_security_engineer", _clinical_sec_strong, _clinical_sec_weak)
