# Azure Data Platform Architecture Standards

## 1. Landing Zone Requirements

All Azure data platforms must be deployed within an Enterprise-Scale Landing Zone:
- Hub-spoke network topology with centralized firewall (Azure Firewall or NVA)
- Management group hierarchy: Root > Platform > Landing Zones > Data Platform
- Dedicated subscriptions for prod, non-prod, and shared services
- Azure Policy assignments for: naming conventions, allowed regions, required tags, encryption, private endpoints

## 2. Storage Architecture

### ADLS Gen2
- Hierarchical namespace MUST be enabled
- Minimum redundancy: ZRS for single-region, GRS for multi-region critical data
- Customer-managed keys (CMK) required for all data classified as Confidential or above
- Lifecycle management policies: Hot → Cool after 90 days, Cool → Archive after 365 days
- Container structure: one container per data layer (raw, curated, consumption)

### OneLake (Fabric)
- Preferred for new greenfield implementations when team is Microsoft-aligned
- Shortcuts to ADLS Gen2 for hybrid scenarios
- Workspace-level access control maps to data domains

## 3. Compute Architecture

### Databricks
- Unity Catalog required for all new workspaces (no legacy Hive metastore)
- Cluster policies must enforce: max 20 workers, auto-termination 15 min, approved VM SKUs only
- Photon enabled for SQL/DataFrame workloads
- Shared clusters for dev, job clusters for production
- Secrets via Azure Key Vault integration, never hardcoded

### Synapse Analytics
- Serverless SQL pool for ad-hoc exploration (no provisioned resources needed)
- Dedicated SQL pool only when concurrency > 50 users or SLA < 2 seconds
- Pause dedicated pools in non-production after business hours (auto-pause not available, use Azure Automation)
- Minimum DWU: DW100c for dev, DW500c for production starting point

### Data Factory
- Managed VNet with private endpoints for all linked services
- Self-hosted IR only for on-premises sources
- Git integration (Azure DevOps or GitHub) required for all environments
- Parameterize everything: no hardcoded server names, database names, or file paths
- CI/CD: ARM template export → validate → deploy via release pipeline

## 4. Security Standards

### Network
- All PaaS services must use private endpoints. Public access disabled.
- Network Security Groups on all subnets with deny-all inbound default
- Azure DDoS Protection Standard on hub VNet
- DNS: Private DNS zones for all PaaS services (privatelink.blob.core.windows.net, etc.)

### Identity
- Managed identities for all service-to-service authentication
- No service principal secrets; use certificate-based auth where managed identity not possible
- Conditional Access: MFA required, compliant device required for data platform access
- Privileged Identity Management (PIM) for all admin roles: max 4-hour activation

### Data Protection
- Encryption at rest: AES-256, CMK for Confidential data
- Encryption in transit: TLS 1.2+ enforced, TLS 1.0/1.1 disabled
- Dynamic data masking on PII columns in Synapse/SQL
- Row-Level Security (RLS) for multi-tenant data access patterns
- Azure Key Vault: FIPS 140-2 Level 2, soft-delete enabled, purge protection enabled

## 5. Governance

### Microsoft Purview
- All data assets must be registered and scanned within 30 days of deployment
- Sensitivity labels applied: Public, Internal, Confidential, Highly Confidential
- Data lineage tracked from source to consumption layer
- Business glossary maintained with minimum one term per domain
- Quarterly data quality review with domain stewards

### Tagging Standards
Required tags on all resources:
- `environment`: prod, staging, dev, sandbox
- `domain`: sales, finance, marketing, operations, platform
- `cost-center`: mapped to organizational cost center
- `owner`: email of responsible team lead
- `data-classification`: public, internal, confidential, highly-confidential

## 6. Cost Management

- Monthly budget alerts at 80%, 90%, 100% of planned spend
- Reserved instances for production: 1-year minimum for Databricks, Synapse, Cosmos DB
- Auto-scale rules: scale down at 8 PM, scale up at 7 AM for non-critical workloads
- Spot VMs for fault-tolerant batch Databricks jobs (60-90% savings)
- Quarterly FinOps review with architecture and finance teams
- Target: production data platform cost should not exceed $12 per TB per month stored

## 7. High Availability & Disaster Recovery

- RPO/RTO targets by tier:
  - Tier 1 (Critical): RPO 15 min, RTO 1 hour
  - Tier 2 (Important): RPO 1 hour, RTO 4 hours
  - Tier 3 (Standard): RPO 24 hours, RTO 24 hours
- ADLS Gen2: GRS with automated failover for Tier 1
- Databricks: workspace config in Terraform, redeploy to paired region within RTO
- ADF: Git-backed, redeploy via CI/CD to secondary region
- DR runbook tested quarterly; results documented
- Azure Paired Regions: East US / West US, North Europe / West Europe

## 8. Migration Standards

- All migrations follow 5R framework: Rehost, Refactor, Rearchitect, Rebuild, Replace
- Data warehouse migration (Teradata, Oracle, SQL Server):
  - Schema assessment using Azure Migrate or third-party tools
  - Data movement via ADF Copy Activity for < 10TB, Azure Data Box for > 10TB
  - Parallel run for minimum 4 weeks before cutover
  - Validation: row counts within 0.01%, checksum on 10% sample, query result comparison on top 50 reports
- Maximum migration batch: 500GB per weekend window
