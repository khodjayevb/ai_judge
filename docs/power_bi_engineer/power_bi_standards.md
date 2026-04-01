# Power BI Engineering Standards — Clinical Trials Research

## 1. Data Modeling Standards

### Star Schema Requirements
- All analytical models MUST follow Kimball star schema methodology
- Fact tables: narrow, many rows, numeric measures, surrogate keys
- Dimension tables: wide, fewer rows, descriptive attributes, natural + surrogate keys
- No flat/wide tables — always decompose into facts and dimensions
- Cross-filter direction: single (dimension filters fact) — never bidirectional unless documented justification

### Clinical Trials Data Model
- **Fact tables**: fact_enrollment, fact_adverse_events, fact_lab_results, fact_protocol_deviations, fact_visits
- **Dimension tables**: dim_study, dim_site, dim_subject, dim_investigator, dim_date, dim_treatment_arm
- dim_date MUST be a dedicated, continuous date table marked as Date Table — never rely on Auto Date/Time
- dim_subject MUST NOT contain PHI — use pseudonymized subject IDs only
- Treatment arm dimensions require blinding controls — unblinded data only in restricted workspaces

### Relationships
- One-to-many from dimension to fact (always)
- Many-to-many only with bridge tables (e.g., subject-to-multiple-studies)
- Role-playing dimensions: use USERELATIONSHIP for multiple date relationships (enrollment date, AE onset date, visit date)
- Inactive relationships for secondary date joins

### Naming Conventions
- Measures: Descriptive, PascalCase (e.g., TotalEnrollment, AERate_SAE, AvgDaysOnStudy)
- Tables: dim_ prefix for dimensions, fact_ prefix for facts
- Columns: PascalCase, no abbreviations except standard ones (AE, SAE, SUSAR, DM, VS, LB)
- Calculated columns: prefix with "Calc_" to distinguish from source columns

## 2. DAX Standards

### Measure Writing
- ALWAYS use VAR / RETURN pattern for readability and performance
- ALWAYS use DIVIDE() instead of / to handle division by zero
- ALWAYS guard against BLANK with IF(NOT ISBLANK(...)) for time intelligence
- Use REMOVEFILTERS or ALL inside CALCULATE — document why filter context is being modified
- Prefer measures over calculated columns for all aggregations

### Clinical Trial Measures — Standard Library
Required measures for every clinical trial model:
- TotalEnrolled: COUNT of subjects with enrollment date
- ActiveSubjects: CALCULATE(COUNT, filter for active status)
- AERate: DIVIDE(CountAE, TotalExposureDays) — adverse event incidence rate
- SAECount: COUNT of Serious Adverse Events, filtered by SAE flag
- ScreenFailRate: DIVIDE(ScreenFails, TotalScreened)
- CompletionRate: DIVIDE(Completers, TotalEnrolled)
- ProtocolDeviationRate: DIVIDE(MajorDeviations, TotalSubjects)
- AvgDaysOnStudy: AVERAGEX over subject-level duration calculation

### Time Intelligence
- Enrollment trends: TOTALYTD, DATEADD for month-over-month comparison
- Custom fiscal calendar support for sponsor-specific reporting periods
- Study start date as reference point (not calendar year)
- PARALLELPERIOD for rolling 12-month safety monitoring windows

## 3. Security Standards

### Row-Level Security (RLS)
- Dynamic RLS using USERPRINCIPALNAME() — never hardcode user lists
- Security table: maps user email to allowed study IDs and site IDs
- Site monitors: see only their assigned sites
- Medical monitors: see all sites but only safety data (AE, SAE)
- Biostatisticians: see all data for assigned studies (blinded or unblinded per role)
- Study-level RLS: users only see studies they are assigned to

### Blinding Controls
- Unblinded reports (DSMB/DMC) MUST be in a separate, access-restricted workspace
- Treatment arm columns MUST NOT appear in blinded workspaces
- RLS alone is NOT sufficient for blinding — workspace isolation required
- Emergency unblinding access requires PIM (Privileged Identity Management) activation

### Object-Level Security (OLS)
- Hide treatment assignment columns from blinded roles via Tabular Editor
- Hide investigator PII columns (name, email) from non-authorized roles
- Apply OLS before publishing — cannot be configured in Power BI Service

### Workspace Permissions
- Production workspaces: Viewer role for consumers, Contributor for developers
- DSMB workspace: Admin role for unblinded biostat lead only
- Workspace per study or per therapeutic area — not one workspace for everything

## 4. Performance Standards

### Storage Mode
- Import mode for datasets under 1 GB (most clinical trial models)
- Composite models for large-scale multi-study reporting (fact tables in DirectQuery, dimensions in Dual mode)
- Dual storage mode for ALL dimension tables in composite models
- DirectQuery only when real-time data is required (rare in clinical trials — batch refresh sufficient)

### Model Size
- Target: under 500 MB for standard clinical trial models
- Remove unused columns before publishing (reduce model size)
- Disable Auto Date/Time at file level (prevents hidden date tables)
- Reduce cardinality: hash high-cardinality text columns, remove unnecessary precision

### Report Performance
- Maximum 15 visuals per page
- Use Performance Analyzer to identify slow visuals (target: all visuals under 3 seconds)
- DAX Studio + VertiPaq Analyzer for model profiling
- Aggregation tables for multi-study summary dashboards

### Refresh
- Incremental refresh for fact_adverse_events and fact_lab_results (high-volume tables)
- RangeStart/RangeEnd parameters on ADaM refresh date column
- Refresh window: 3 years archive, 30 days incremental
- Detect data changes via LastModifiedDate column to skip unchanged partitions

## 5. Deployment & CI/CD Standards

### Deployment Pipelines
- Three stages: Development → Test → Production
- Deployment rules MUST override connection strings per stage (Dev SQL → Test SQL → Prod SQL)
- Dataset parameters for environment-specific values (server, database, storage account)
- Gateway bindings configured per stage

### Git Integration
- All Power BI projects in PBIP format, connected to Azure DevOps repo
- Branching: feature branches → PR to develop → PR to main → deploy
- Tabular Editor Best Practice Analyzer (BPA) rules run in CI pipeline
- Block deployment if BPA violations found (no calculated columns in facts, no bi-directional filters)

### Version Control
- Semantic model changes tracked in Git (TMDL format)
- Report layout changes tracked in Git (PBIR format)
- Every deployment tagged with version number
- Rollback capability via previous Git tag

## 6. Governance & Monitoring

### Certification
- Only certified datasets used in production reports
- Certification requires: star schema validation, RLS testing, BPA compliance, performance benchmark
- Endorsed datasets for development/exploration use

### Monitoring
- Power BI Activity Log → Azure Log Analytics for audit trail
- Capacity Metrics app for Premium/Fabric capacity monitoring
- Alert on: refresh failures, usage spikes, capacity throttling
- Monthly governance review: unused reports, oversized datasets, stale refreshes

### Data Lineage
- Document source-to-report lineage for every production report
- ADaM dataset → Dataflow/Direct Lake → Semantic Model → Report
- Purview integration for cross-platform lineage tracking
