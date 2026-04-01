# Clinical Trials Reporting Patterns for Power BI

## 1. Standard Report Types

### Enrollment Dashboard
- **Purpose**: Real-time enrollment tracking against study targets
- **Key visuals**: Enrollment curve (actual vs planned), site map, screen-fail funnel
- **Measures**: TotalScreened, TotalEnrolled, ScreenFailRate, EnrollmentRate_Monthly
- **Filters**: Study, therapeutic area, region, site, date range
- **Refresh**: Daily (from ADaM ADSL dataset)
- **Security**: All study team members can view; site-level RLS for site monitors

### Safety Monitoring Dashboard
- **Purpose**: AE/SAE monitoring for medical monitor and safety team
- **Key visuals**: AE summary by SOC/PT (System Organ Class / Preferred Term), SAE timeline, exposure-adjusted AE rates, lab shift tables
- **Measures**: AERate, SAECount, SUSAR_Count, ExposureAdjustedRate, LabShift_High, LabShift_Low
- **MedDRA hierarchy**: Use hierarchy slicer for SOC → HLT → PT → LLT drill-down
- **Filters**: Study, treatment arm (blinding-dependent), site, severity, causality, date range
- **Refresh**: Daily or per data transfer
- **Security**: Medical monitors see all sites; site monitors see their sites only via RLS
- **CRITICAL**: Unblinded safety reports (showing treatment arm) MUST be in isolated DSMB workspace

### Study Progress Dashboard
- **Purpose**: Operational tracking of visit completion, data entry, query resolution
- **Key visuals**: Visit completion heatmap (site × visit), query aging chart, data entry lag
- **Measures**: VisitCompletionRate, OpenQueryCount, MedianQueryAge, DataEntryLag_Days
- **Filters**: Study, site, visit window, form/CRF
- **Refresh**: Daily
- **Security**: Clinical operations team and project managers

### Protocol Deviation Report
- **Purpose**: Track and categorize protocol deviations per ICH E6 requirements
- **Key visuals**: Deviation by category (stacked bar), site comparison, trend over time
- **Measures**: MajorDeviationCount, MinorDeviationCount, DeviationRate_PerSubject
- **Filters**: Study, site, deviation category, severity (major/minor)
- **Refresh**: Weekly
- **Security**: Study team with site-level RLS

### DSMB/DMC Report Package (Paginated)
- **Purpose**: Formal safety report for Data Safety Monitoring Board
- **Format**: Power BI paginated reports (pixel-perfect for PDF export)
- **Content**: AE summary tables by treatment arm, SAE listings, enrollment by arm, efficacy interim (if applicable)
- **CRITICAL**: Contains unblinded treatment data — restricted workspace only
- **Version control**: Each DSMB package versioned and archived in immutable storage
- **Data lock**: Generate from locked data snapshot, not live data

## 2. DAX Patterns for Clinical Trials

### Enrollment Curve (Actual vs Planned)
```dax
EnrolledCumulative =
VAR CurrentDate = MAX('Date'[Date])
RETURN
    CALCULATE(
        COUNTROWS(fact_enrollment),
        fact_enrollment[EnrollmentDate] <= CurrentDate,
        ALL('Date')
    )

PlannedCumulative =
VAR CurrentDate = MAX('Date'[Date])
RETURN
    CALCULATE(
        SUM(dim_study[PlannedCumulative]),
        dim_study[PlannedDate] <= CurrentDate,
        ALL('Date')
    )

EnrollmentVariance = [EnrolledCumulative] - [PlannedCumulative]
```

### Adverse Event Incidence Rate (Exposure-Adjusted)
```dax
AEIncidenceRate =
VAR TotalAEs = COUNTROWS(fact_adverse_events)
VAR TotalExposureDays =
    SUMX(
        dim_subject,
        DATEDIFF(
            dim_subject[FirstDoseDate],
            COALESCE(dim_subject[LastDoseDate], TODAY()),
            DAY
        )
    )
VAR ExposureYears = DIVIDE(TotalExposureDays, 365.25)
RETURN
    DIVIDE(TotalAEs, ExposureYears)
```

### Screen Failure Funnel
```dax
ScreenFailRate =
DIVIDE(
    CALCULATE(COUNTROWS(dim_subject), dim_subject[SubjectStatus] = "Screen Failure"),
    CALCULATE(COUNTROWS(dim_subject), dim_subject[SubjectStatus] IN {"Enrolled", "Screen Failure", "Screening"})
)
```

### Visit Completion Rate
```dax
VisitCompletionRate =
VAR ExpectedVisits =
    COUNTROWS(
        CROSSJOIN(
            VALUES(dim_subject[SubjectID]),
            VALUES(dim_visit_schedule[VisitName])
        )
    )
VAR CompletedVisits = COUNTROWS(fact_visits)
RETURN
    DIVIDE(CompletedVisits, ExpectedVisits)
```

## 3. Compliance Requirements

### 21 CFR Part 11
- All Power BI access logged via Power BI Activity Log + Azure Log Analytics
- Electronic signatures not applicable to BI reports (reports are for review, not approval)
- Audit trail: who viewed what report, when, with what filters applied
- Report export controls: restrict PDF/Excel export for sensitive datasets via tenant admin settings

### HIPAA
- No PHI in Power BI datasets — use pseudonymized subject IDs
- dim_subject contains SubjectID (pseudonymized), NOT patient name, DOB, MRN
- Site-level data (site name, PI name) may be PII — apply OLS if needed
- Export to Excel restricted for datasets containing site-level details

### GDPR
- EU subject data residency: ensure Power BI capacity in EU region for EU studies
- Right to erasure: if subject withdraws, data anonymized in source → reflects in next refresh
- Data minimization: only include necessary columns in the model

### ICH GCP E6(R2)
- Reports used for safety monitoring must be reproducible (data lock + version control)
- DSMB reports must be generated from locked data snapshots
- Timestamp of data currency displayed on every report page

## 4. Power Query / Data Source Patterns

### ADaM → Power BI Pipeline
- Source: ADaM datasets in ADLS Gen2 (Parquet/Delta format) or Fabric Lakehouse
- Connection: Direct Lake (Fabric) or Import via ADLS Gen2 connector
- Recommended: Dataflow Gen2 for transformation layer between ADaM and semantic model
- Query folding: verify all transformations fold to source (right-click → View Native Query)

### Incremental Refresh Configuration
- Apply to: fact_adverse_events, fact_lab_results, fact_visits (high-volume tables)
- RangeStart/RangeEnd: based on data transfer date or last modified date
- Archive window: full study duration (typically 3-5 years)
- Incremental window: 30 days
- Detect changes: LastModifiedDate column

### Gateway Requirements
- On-premises SQL Server (legacy EDC extracts): requires Standard Gateway
- ADLS Gen2 / Fabric: no gateway needed (cloud-to-cloud)
- Gateway cluster for high availability in production

## 5. Migration Patterns

### From SAS to Power BI
- SAS PROC TABULATE / PROC REPORT → Power BI paginated reports
- SAS macro variables → Power BI parameters
- SAS formats → DAX SWITCH or calculated columns
- SAS ODS output → Power BI subscriptions (PDF/Excel export)
- Validation: compare Power BI output to SAS output cell-by-cell for TLFs

### From Tableau to Power BI
- Tableau calculated fields → DAX measures
- Tableau LOD expressions → CALCULATE with filter modifiers (REMOVEFILTERS, ALL)
- Tableau parameters → Power BI What-If parameters or field parameters
- Tableau data extracts → Power BI Import mode datasets
- Tableau Dashboard Actions → Power BI drill-through and cross-filtering
