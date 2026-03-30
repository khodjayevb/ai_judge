# DUKE CLINICAL RESEARCH INSTITUTE

## Clinical Trials Data Management — Comprehensive Test Suites

### Azure / Microsoft Fabric Environment

**Document Version:** 1.0
**Date:** March 29, 2026
**Classification:** CONFIDENTIAL

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Suite 1: Regulatory & Compliance Test Cases](#suite-1-regulatory--compliance-test-cases)
3. [Suite 2: CDISC Data Standards Test Cases](#suite-2-cdisc-data-standards-test-cases)
4. [Suite 3: Data Pipeline & Architecture Test Cases](#suite-3-data-pipeline--architecture-test-cases)
5. [Suite 4: Reporting & Submission Test Cases](#suite-4-reporting--submission-test-cases)
6. [Suite 5: Security & Data Handling Test Cases](#suite-5-security--data-handling-test-cases)
7. [Suite 6: AI Assistant & Team Governance Test Cases](#suite-6-ai-assistant--team-governance-test-cases)
8. [Appendix A: Test Execution Summary](#appendix-a-test-execution-summary)
9. [Appendix B: Document Control](#appendix-b-document-control)

---

## Executive Summary

This document defines comprehensive test suites for the Duke Clinical Research Institute (DCRI) clinical trials data management platform built on Microsoft Azure and Fabric. The test suites address six critical dimensions: regulatory compliance, CDISC data standards, data pipeline integrity, reporting accuracy, security controls, and AI assistant governance.

Each test case is mapped to specific regulatory requirements (FDA 21 CFR Part 11, ICH GCP E6(R2), HIPAA, GDPR), industry standards (CDISC CDASH/SDTM/ADaM, MedDRA, WHODrug), and DCRI standard operating procedures. Severity classifications (Critical, High, Medium) reflect the risk to patient safety, data integrity, and regulatory compliance.

**Assumed Reference Pipeline:**

> EDC (Rave/Veeva/Clinical One/REDCap) → ADLS Gen2 Landing Zone → SDTM Transformation (Databricks/Fabric) → ADaM Generation → TLF Reporting (Power BI Paginated) → Regulatory Submission (eCTD)

---

## Suite 1: Regulatory & Compliance Test Cases

These test cases validate compliance with FDA, ICH, HIPAA, and GDPR requirements. Failure of any Critical-severity test case constitutes a potential regulatory finding and must be remediated before production use. All tests should be executed as part of the computerized system validation (CSV) protocol under IQ/OQ/PQ framework.

### 1.1 FDA 21 CFR Part 11 — Electronic Records & Signatures

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| REG-001 | Audit Trail | Verify all data modifications in EDC landing zone generate timestamped, user-attributed audit trail entries in immutable storage | Each INSERT, UPDATE, DELETE produces audit record with: original value, new value, user ID, timestamp (UTC), reason for change. Records stored in append-only ADLS container. | 21 CFR Part 11 §11.10(e) | **Critical** | Query audit log table; compare row counts pre/post modification; verify immutability via ADLS access policy | |
| REG-002 | Audit Trail | Confirm audit trail records cannot be modified or deleted by any user role including system administrators | Attempted DELETE/UPDATE on audit log returns access denied. ADLS immutability policy enforced at storage layer. No Fabric workspace role permits audit log modification. | 21 CFR Part 11 §11.10(e) | **Critical** | Attempt DELETE with admin credentials; verify ADLS immutable blob policy; review Fabric RBAC on audit lakehouse | |
| REG-003 | Electronic Sig | Validate electronic signatures include signer identification, date/time, and meaning of signature (e.g., approval, review, authorship) | Signature metadata captures: full name, unique user ID, organization, timestamp (UTC), signature meaning from controlled vocabulary. Stored as signed record in database. | 21 CFR Part 11 §11.50 | **Critical** | Execute e-signature workflow; query signature table; verify all required fields populated and non-null | |
| REG-004 | Electronic Sig | Verify signed records cannot be altered after signature without invalidating the signature and triggering re-authentication | Modification attempt on signed record triggers signature invalidation flag, generates alert to data management, requires re-signature with new audit entry documenting the change. | 21 CFR Part 11 §11.10(c) | **Critical** | Modify signed record via API; verify signature status changes to INVALIDATED; confirm re-authentication required | |
| REG-005 | Access Control | Validate role-based access control enforces principle of least privilege across all pipeline stages (landing, SDTM, ADaM, reporting) | Each pipeline stage has distinct Fabric workspace roles. Data engineers cannot access unblinded ADaM datasets. Biostatisticians have read-only on SDTM. Clinical data managers cannot execute ADaM transformations. | 21 CFR Part 11 §11.10(d) | **Critical** | Enumerate all role assignments per workspace; test cross-workspace access with each role; verify deny-by-default | |
| REG-006 | Access Control | Confirm unique user identification: no shared accounts, no generic logins, each action attributable to an individual | All service accounts use managed identity (no shared password). Human users authenticate via Entra ID with MFA. No generic accounts (e.g., admin, test) exist in production. | 21 CFR Part 11 §11.10(d) | **Critical** | Audit Entra ID for shared/generic accounts; verify MFA enforcement policy; test that service principals use managed identity | |
| REG-007 | System Validation | Execute IQ/OQ/PQ validation protocol for all Fabric components processing regulated data | IQ: infrastructure deployed per specification. OQ: each component operates within defined parameters under normal conditions. PQ: end-to-end pipeline produces correct output from known test data. | 21 CFR Part 11 §11.10(a) | **Critical** | Run IQ/OQ/PQ test scripts; compare outputs to pre-validated expected results; document deviations | |
| REG-008 | Data Integrity | Verify ALCOA+ principles: Attributable, Legible, Contemporaneous, Original, Accurate + Complete, Consistent, Enduring, Available | All data records attributable to source. Timestamps generated at point of capture. Original records preserved in landing zone. No data loss across transformations. Data retrievable for entire retention period. | 21 CFR Part 11 §11.10(a) | **Critical** | Trace sample records through full pipeline; verify attribution at each stage; confirm landing zone preservation | |

### 1.2 ICH GCP E6(R2) — Good Clinical Practice

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| REG-009 | Source Data Verification | Validate that EDC-sourced data in SDTM datasets can be traced back to original source documents | Each SDTM observation includes: STUDYID, SITEID, USUBJID, and source record key mapping to EDC database. Traceability metadata maintained in separate mapping table. | ICH E6(R2) §5.18.4 | **Critical** | Select random SDTM records; trace to EDC source via mapping keys; verify values match | |
| REG-010 | Protocol Compliance | Confirm edit checks in EDC-to-landing pipeline enforce protocol-defined data validation rules | Protocol-specified range checks, cross-field validations, and required field rules fire during ingestion. Violations logged as queries. Data failing critical checks quarantined in error lakehouse. | ICH E6(R2) §5.18.3 | **High** | Submit test data violating each edit check category; verify quarantine; confirm query generation | |
| REG-011 | Data Quality | Verify automated data quality checks run at each pipeline stage: landing, SDTM, ADaM | DQ framework executes completeness, conformance, plausibility, and uniqueness checks. Results logged to DQ dashboard. Critical DQ failures halt downstream processing. | ICH E6(R2) §5.18.3 | **High** | Inject known DQ issues; verify detection rate >99%; confirm pipeline halt on critical failures | |

### 1.3 HIPAA — Protected Health Information

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| REG-012 | PHI De-identification | Validate Safe Harbor de-identification removes all 18 HIPAA identifiers before data enters analytics layer | Names, dates (except year), phone/fax, email, SSN, MRN, device IDs, URLs, IPs, biometric IDs, photos, and other unique identifiers removed or generalized. Expert determination documented if statistical method used. | HIPAA §164.514(b) | **Critical** | Run de-identification validation script against ADaM datasets; scan all string fields for residual PHI patterns; verify date shifting applied consistently | |
| REG-013 | Encryption at Rest | Confirm all data stores containing PHI use AES-256 encryption at rest | ADLS Gen2, Fabric Lakehouse, SQL databases, and backup storage all encrypted via Microsoft-managed or customer-managed keys. Encryption verified at storage account level. | HIPAA §164.312(a)(2)(iv) | **Critical** | Query Azure Resource Manager for encryption settings on each storage account; verify key vault configuration; test that raw storage access returns encrypted bytes | |
| REG-014 | Encryption in Transit | Verify all data transfers use TLS 1.2+ encryption including EDC-to-Azure, inter-service, and user access | TLS 1.2 minimum enforced. Legacy TLS versions disabled. Internal service mesh communication encrypted. VPN/ExpressRoute for EDC connections. | HIPAA §164.312(e)(1) | **Critical** | Scan endpoints with TLS checker; verify minimum version policy in Azure; test that TLS 1.0/1.1 connections rejected | |
| REG-015 | Access Logging | Validate comprehensive access logging for all PHI-containing resources | Every read/write/delete operation logged with: user identity, resource accessed, timestamp, action type, source IP. Logs retained per DCRI retention policy (minimum 6 years). | HIPAA §164.312(b) | **Critical** | Access PHI resources with test account; verify log entries within 60 seconds; confirm log retention configuration | |

### 1.4 GDPR — EU Trial Sites & Subjects

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| REG-016 | Cross-Border Transfer | Validate EU-to-US data transfer complies with EU-US Data Privacy Framework or Standard Contractual Clauses | Transfer mechanism documented and active. Data transfer impact assessment completed. Technical safeguards (encryption, pseudonymization) applied before transfer. Transfer logs maintained. | GDPR Art. 46 | **Critical** | Review transfer mechanism documentation; verify SCC execution; confirm pseudonymization applied pre-transfer; audit transfer logs | |
| REG-017 | Right to Erasure | Confirm subject withdrawal triggers data deletion/anonymization across all pipeline stages within required timeframe | Withdrawal request propagates from EDC through all downstream datasets. Subject data anonymized (not deleted, per regulatory retention) within 30 days. Confirmation sent to requesting site. | GDPR Art. 17 | **High** | Submit test withdrawal; verify propagation to all datasets within SLA; confirm anonymization complete; check no residual identifiable data | |
| REG-018 | Data Minimization | Verify only protocol-required data elements collected and processed at each pipeline stage | EDC forms collect only CRF-specified fields. SDTM datasets contain only standard and protocol-required variables. ADaM datasets derive only SAP-specified endpoints. No extraneous data persisted. | GDPR Art. 5(1)(c) | **High** | Compare dataset schemas against protocol CRF annotations and SAP; identify any non-required variables; verify justification for each additional field | |

---

## Suite 2: CDISC Data Standards Test Cases

These test cases validate conformance with CDISC standards across the data lifecycle: CDASH for collection, SDTM for tabulation, ADaM for analysis, and define.xml for metadata documentation. Medical coding accuracy (MedDRA, WHODrug) is also validated. Pinnacle 21 (formerly OpenCDISC) is the primary validation tool for structural conformance.

### 2.1 CDASH — Clinical Data Acquisition Standards

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| CDISC-001 | CDASH Conformance | Validate EDC collection forms conform to CDASH v2.2 standards for all core domains (DM, VS, AE, CM, LB, MH, EX) | CRF field names, labels, and data types align with CDASH implementation guide. Core variables present for each domain. Controlled terminology from CDISC CT applied. | CDISC CDASH v2.2 | **High** | Map EDC field definitions against CDASH IG; run automated conformance checker; document deviations with justification | |
| CDISC-002 | CDASH Terminology | Verify controlled terminology values in EDC match current CDISC Controlled Terminology package | All coded fields use values from the specified CT package version. No deprecated or non-standard values accepted. CT version documented in study metadata. | CDISC CT | **High** | Extract distinct values per coded variable; compare against CT package; identify non-conformant values | |

### 2.2 SDTM — Study Data Tabulation Model

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| CDISC-003 | SDTM Structure | Validate SDTM datasets conform to SDTM IG v3.4 structure requirements: variable names, labels, types, lengths | All datasets pass Pinnacle 21 (OpenCDISC) structural validation with zero errors. Variable metadata matches define.xml. No truncation of character variables. | SDTM IG v3.4 | **Critical** | Run Pinnacle 21 Community/Enterprise; review validation report; verify zero structural errors | |
| CDISC-004 | SDTM Mapping | Confirm EDC-to-SDTM mapping produces accurate transformations for all collected data points | Mapping specification documents each source-to-target transformation. Unit test coverage >95% of mapping rules. Reconciliation counts match between source and target for all subjects. | SDTM IG v3.4 | **Critical** | Execute mapping test suite; compare source/target record counts; verify value-level accuracy on 10% random sample | |
| CDISC-005 | SDTM RELREC | Validate relationship records (RELREC) correctly link related observations across domains | Parent-child relationships (e.g., AE-CM for concomitant meds treating AEs) documented in RELREC with correct USUBJID, RDOMAIN, IDVAR, IDVARVAL linkage. | SDTM IG v3.4 | **High** | Query RELREC; verify referential integrity across linked domains; confirm no orphaned relationships | |
| CDISC-006 | SDTM Timing | Verify timing variables (VISIT, VISITNUM, DTC, DY) calculated correctly and consistently across all domains | Visit numbers sequential per protocol schedule. Study day calculated from RFSTDTC. Date/time in ISO 8601 format. No future dates beyond current date. Visit windowing applied per SAP. | SDTM IG v3.4 | **High** | Validate DY calculation logic; check VISITNUM sequencing; verify ISO 8601 compliance across all --DTC variables | |

### 2.3 ADaM — Analysis Data Model

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| CDISC-007 | ADaM Structure | Validate ADSL (subject-level), BDS (basic data structure), and OCCDS (occurrence data structure) datasets conform to ADaM IG v1.3 | Pinnacle 21 validation returns zero structural errors. Required variables (STUDYID, USUBJID, PARAMCD, AVAL, etc.) present. Traceability to SDTM maintained via mapping metadata. | ADaM IG v1.3 | **Critical** | Run Pinnacle 21 ADaM checks; verify required variable presence; test traceability to SDTM source records | |
| CDISC-008 | ADaM Derivations | Confirm derived variables (AVAL, AVALC, CHG, PCHG, BASE, ABLFL, ANL01FL) calculated per Statistical Analysis Plan | Baseline flag (ABLFL) assigned per SAP window definition. Change from baseline (CHG = AVAL - BASE) calculated correctly. Analysis flags populated per pre-specified rules. | ADaM IG v1.3, SAP | **Critical** | Independently recalculate derived variables for 100% of subjects; compare against ADaM output; identify discrepancies | |
| CDISC-009 | ADaM Population | Verify population flags (SAFFL, ITTFL, FASFL, PPROTFL, COMPLFL) correctly assigned per SAP criteria | Each population flag matches SAP definition. Subject counts reconcile with enrollment log. Edge cases (e.g., early termination, major protocol deviations) correctly classified. | ADaM IG v1.3, SAP | **Critical** | Compare population counts against independent derivation; verify edge case classification; reconcile with DSMB-reported counts | |
| CDISC-010 | define.xml | Validate define.xml (v2.1) accurately documents all SDTM and ADaM datasets, variables, controlled terms, and derivation methods | define.xml passes Pinnacle 21 define validation. All datasets and variables documented. Derivation methods (computational algorithms) present for all derived variables. Hyperlinks to annotated CRF functional. | CDISC Define-XML v2.1 | **High** | Run Pinnacle 21 define checks; verify hyperlink functionality; confirm derivation method completeness | |

### 2.4 Medical Coding

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| CDISC-011 | MedDRA Coding | Validate adverse event coding against MedDRA dictionary (current version) with correct hierarchy: LLT, PT, HLT, HLGT, SOC | All AE verbatim terms coded. Auto-coded terms match expected PT. Manual coding queue captured with coder ID and timestamp. MedDRA version documented in dataset metadata. | MedDRA, ICH E2B(R3) | **Critical** | Verify coding completeness (0% uncoded in final); validate hierarchy integrity; test auto-coding accuracy against gold standard | |
| CDISC-012 | WHODrug Coding | Validate concomitant medication coding against WHODrug Global (current version) with ATC classification | All CM verbatim terms coded to WHODrug preferred name and ATC code. Drug-drug interaction flags populated where applicable. WHODrug version documented. | WHODrug | **High** | Verify coding completeness; validate ATC code assignment; check version consistency across studies | |
| CDISC-013 | Coding Upgrades | Confirm dictionary version upgrades (MedDRA/WHODrug) properly remap existing coded terms without data loss | Version upgrade produces mapping report. All previously coded terms re-evaluated. Changes documented with before/after values. No loss of coding granularity. | MedDRA/WHODrug | **High** | Execute dictionary upgrade on test dataset; verify remapping completeness; compare pre/post coding distributions | |

---

## Suite 3: Data Pipeline & Architecture Test Cases

These test cases validate the end-to-end data pipeline from EDC ingestion through ADaM generation. Tests cover data completeness, transformation accuracy, error handling, idempotency, and the critical SAS-to-Spark parity validation for teams transitioning from traditional SAS programming to Python/Spark environments.

### 3.1 EDC Ingestion (Medidata Rave / Veeva / Oracle Clinical One → ADLS Gen2)

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| PIPE-001 | Data Extraction | Validate EDC extract completeness: all subjects, all visits, all forms, all fields ingested without data loss | Record counts reconcile between EDC source and landing zone within 0.01%. Checksums match for critical fields. Extraction log documents any excluded records with justification. | ICH E6(R2) | **Critical** | Compare EDC export counts vs. landing zone counts by site, subject, visit, form; verify checksum on 10% sample | |
| PIPE-002 | Incremental Load | Confirm incremental/delta loads correctly identify and process only new or modified records | Delta detection based on EDC audit trail timestamp. Modified records overwrite in staging (not landing). Landing zone preserves full history. No duplicate records created by re-processing. | 21 CFR Part 11 | **High** | Run incremental load; verify only modified records processed; check for duplicates; validate audit trail continuity | |
| PIPE-003 | Error Handling | Verify pipeline error handling: malformed records quarantined, pipeline continues for valid data, alerts generated | Malformed records (schema violations, encoding errors, data type mismatches) routed to error lakehouse. Pipeline completes for valid records. Automated alert sent to data management team within 5 minutes. | CSV/GxP | **High** | Inject malformed records; verify quarantine; confirm pipeline completion for valid records; validate alert delivery | |
| PIPE-004 | Schema Evolution | Validate pipeline handles EDC schema changes (new fields, modified fields) without data loss or pipeline failure | New fields added to schema automatically or via managed process. Modified field types handled with explicit conversion rules. Schema version tracked in metadata. No silent data truncation. | CSV/GxP | **High** | Deploy EDC amendment adding new fields; run pipeline; verify new fields captured; confirm existing data unaffected | |

### 3.2 SDTM Transformation (Databricks / Fabric Notebooks)

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| PIPE-005 | SDTM Mapping Execution | Validate SDTM mapping specifications execute correctly in Databricks/Spark environment | All mapping rules produce expected output for known test data. Execution completes within defined SLA. Transformation logs capture row-level processing statistics. | CDISC SDTM IG | **Critical** | Execute mapping on reference test data; compare output to validated expected results; verify execution time within SLA | |
| PIPE-006 | Character Encoding | Confirm UTF-8 encoding preserved through all pipeline stages for international site data (accented characters, non-Latin scripts) | Non-ASCII characters in site names, investigator names, verbatim terms preserved without corruption. No mojibake or replacement characters in output datasets. | CDISC SDTM IG | **High** | Inject test data with accented/CJK characters; verify preservation through landing, SDTM, and ADaM stages | |
| PIPE-007 | Referential Integrity | Validate cross-domain referential integrity: all USUBJID in domain datasets exist in DM; all referenced records exist in parent domains | Zero orphaned records across domains. All USUBJID values in domain datasets match DM. Cross-references (e.g., AE to CM via RELREC) resolve correctly. | CDISC SDTM IG | **Critical** | Run referential integrity queries across all domain pairs; report orphan counts; verify RELREC resolution | |
| PIPE-008 | Idempotency | Confirm pipeline re-execution produces identical output (idempotent processing) | Re-running pipeline on same source data produces byte-identical output datasets. No timestamp-dependent derivations create differences. Checksum verification passes. | CSV/GxP | **High** | Execute pipeline twice on identical input; compare output checksums; identify any non-deterministic transformations | |

### 3.3 ADaM Generation & Analysis-Ready Data

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| PIPE-009 | ADaM Derivation Engine | Validate ADaM derivation logic produces correct analysis values, flags, and population assignments | Independently derived values match pipeline output for 100% of subjects. Statistical analysis plan rules implemented correctly. Edge cases (missing data, partial dates, early termination) handled per SAP. | ADaM IG, SAP | **Critical** | Double-program ADaM datasets independently; run comparison utility; resolve all discrepancies to root cause | |
| PIPE-010 | Unblinding Controls | Verify unblinded treatment assignment data (ADSL.TRT01A, TRT01P) accessible only to authorized unblinded personnel | Treatment columns encrypted or access-controlled in ADaM datasets. Blinded team members receive datasets with treatment columns masked. Access attempts by blinded personnel denied and logged. | ICH E6(R2) §5.5.2 | **Critical** | Attempt access to unblinded columns with blinded user credentials; verify access denied; confirm audit log entry | |
| PIPE-011 | SAS-to-Spark Parity | Validate that Python/Spark-generated ADaM datasets produce identical statistical results to SAS-generated reference datasets | Numeric values match to 10 decimal places. Categorical derivations identical. Date calculations consistent (SAS vs. Python date arithmetic). Summary statistics match to pre-defined tolerance. | CSV/GxP | **Critical** | Compare SAS-generated vs. Spark-generated datasets variable-by-variable; document and explain any numerical differences exceeding tolerance | |

### 3.4 Data Quality Framework

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| PIPE-012 | Completeness Checks | Validate data completeness monitoring: missing values, expected vs. actual record counts per site/visit/form | Completeness dashboard updates within 4 hours of data receipt. Missing data rates calculated per variable, site, and visit. Alerts triggered when missing rate exceeds protocol-defined threshold. | ICH E6(R2) | **High** | Submit data with known missing values; verify dashboard accuracy; confirm alert generation at threshold | |
| PIPE-013 | Conformance Rules | Verify value-level conformance checks against protocol-defined ranges, controlled terminology, and cross-field logic | Out-of-range values flagged with severity level. CT violations rejected at ingestion. Cross-field logic errors (e.g., death date before enrollment) generate priority queries. | ICH E6(R2) | **High** | Submit test data violating each conformance rule category; verify correct flagging and severity assignment | |
| PIPE-014 | Plausibility Checks | Validate statistical plausibility monitoring: outlier detection, Benford's law analysis, digit preference detection | Statistical anomaly detection runs weekly. Site-level data patterns compared against study-wide distribution. Potential data fabrication indicators flagged for medical monitor review. | ICH E6(R2) §5.18.3 | **High** | Inject statistically implausible data patterns; verify detection; confirm escalation to medical monitor | |

---

## Suite 4: Reporting & Submission Test Cases

These test cases validate safety reporting (DSMB/DMC), regulatory submission readiness (eCTD), and TLF accuracy. Double programming verification is the gold standard for TLF validation. DSMB reports require particular attention to unblinding controls and data lock reproducibility.

### 4.1 DSMB/DMC Safety Reports

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| RPT-001 | DSMB Report Gen | Validate automated DSMB safety report generation with correct unblinded treatment-group summaries | Report includes: AE summary by SOC/PT and treatment arm, SAE listings, efficacy interim analysis (if applicable), enrollment summary, protocol deviation summary. Treatment arms correctly labeled. | ICH E6(R2), DMC Charter | **Critical** | Generate DSMB report from known test data; compare all tables/figures against independently produced reference; verify treatment arm accuracy | |
| RPT-002 | DSMB Data Lock | Confirm data snapshot/lock mechanism produces reproducible dataset for DSMB review | Data lock creates immutable snapshot in dedicated ADLS container. Snapshot timestamp and hash recorded. Subsequent pipeline runs do not modify locked snapshot. DSMB report regeneration from snapshot produces identical output. | ICH E6(R2) | **Critical** | Create data lock; run pipeline with new data; verify snapshot unchanged; regenerate report and compare checksums | |
| RPT-003 | Safety Signal | Validate real-time safety signal detection queries and alert thresholds | SAE rate monitoring triggers alert when site-specific or study-wide rate exceeds pre-specified threshold. SUSAR reporting timeline tracking operational. Alert delivered to medical monitor within 1 hour. | ICH E6(R2) §5.17 | **Critical** | Inject SAE data exceeding threshold; verify alert generation; confirm delivery within SLA; validate rate calculation accuracy | |

### 4.2 Regulatory Submission Packages

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| RPT-004 | eCTD Readiness | Validate SDTM/ADaM datasets, define.xml, and reviewer's guide meet FDA eCTD submission requirements | Datasets in SAS Transport (XPT) v5 format. define.xml validates per Pinnacle 21. Reviewer's guide complete. Dataset sizes within eCTD limits. Folder structure per eCTD specification. | FDA eCTD, CDISC | **Critical** | Run Pinnacle 21 submission validation; verify XPT file integrity; check file sizes; validate folder structure | |
| RPT-005 | ADRG Generation | Verify Analysis Data Reviewer's Guide accurately documents all ADaM datasets, derivation logic, and analysis conventions | ADRG covers: analysis dataset inventory, derivation methodology, SAP crosswalk, imputation methods, population definitions. All sections reviewed and approved by biostatistics lead. | FDA Study Data Technical Conformance Guide | **High** | Review ADRG against ADaM datasets; verify all datasets and key derivations documented; cross-reference SAP | |

### 4.3 TLFs — Tables, Listings, Figures (Power BI Paginated Reports)

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| RPT-006 | TLF Accuracy | Validate all statistical tables match independently programmed results (double programming verification) | Table cell values match between primary and QC programs within defined tolerance (integers: exact match; percentages: 0.1%; continuous: 0.01%). Denominator populations correct. | CSV/GxP, SAP | **Critical** | Compare primary vs. QC output cell-by-cell; document and resolve all discrepancies; verify denominator accuracy | |
| RPT-007 | TLF Pagination | Verify Power BI paginated reports render correctly: proper page breaks, headers repeated, footnotes positioned, landscape/portrait appropriate | No orphaned rows. Column headers repeat on each page. Footnotes appear on correct pages. Page numbers sequential. Landscape tables not truncated. | DCRI SOPs | **High** | Generate all report types; visual QC each for pagination; test with varying data volumes (sparse site, large site) | |
| RPT-008 | TLF Refresh | Confirm TLF reports automatically refresh when underlying ADaM datasets update | Report refresh triggered by pipeline completion event. Refresh completes within defined SLA. Data currency timestamp displayed on report. No stale data persists after refresh. | DCRI SOPs | **High** | Update ADaM data; trigger refresh; verify report reflects new data; confirm timestamp updated | |
| RPT-009 | TLF Versioning | Validate report versioning: each DSMB/submission-ready TLF package versioned and archived | Version number auto-incremented. Previous versions archived in immutable storage. Version comparison capability available. Approval workflow enforced before finalization. | 21 CFR Part 11 | **High** | Generate multiple versions; verify archive integrity; test version comparison; confirm approval workflow enforced | |

---

## Suite 5: Security & Data Handling Test Cases

These test cases validate PHI/PII protection, unblinding controls, network security, encryption, and cross-border data transfer compliance. Given DCRI's multi-national trial portfolio, EU-US data transfer validation under GDPR is critical. Unblinding controls are tested both for routine operations and emergency unblinding scenarios.

### 5.1 PHI/PII Handling

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| SEC-001 | Pseudonymization | Validate subject pseudonymization: site-specific subject IDs cannot be reverse-mapped without authorized key access | Pseudonymization key stored in dedicated Azure Key Vault. Access restricted to authorized data management personnel via PIM (Privileged Identity Management). Key rotation policy enforced (annual minimum). | HIPAA, GDPR Art. 4(5) | **Critical** | Verify key vault access controls; attempt reverse-mapping without key access (should fail); verify PIM activation required; confirm key rotation schedule | |
| SEC-002 | Dynamic Masking | Confirm dynamic data masking applied for non-authorized viewers of PHI/PII fields | Date of birth, site names, investigator names masked for users without explicit PHI access role. Masking applied at query time (not stored). Original values accessible only with approved role. | HIPAA §164.514 | **Critical** | Query PHI fields with masked role; verify masking applied; query with authorized role; verify original values visible | |
| SEC-003 | Data Retention | Verify data retention policies enforced: regulatory minimum retention periods, automated archival, controlled deletion | Clinical trial data retained minimum 15 years post-study completion (or per sponsor agreement). Automated lifecycle management moves data to archive tier after active period. Deletion requires documented approval. | 21 CFR Part 11 §11.10(c), ICH | **High** | Review lifecycle policies; verify archive tier transitions; test that premature deletion blocked; confirm retention period configuration | |

### 5.2 Unblinding Controls

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| SEC-004 | Treatment Blind | Validate treatment assignment blinding: only authorized unblinded team members can access randomization data | Randomization table stored in separate, access-controlled ADLS container. Unblinded Fabric workspace isolated from blinded workspaces. Cross-workspace data leakage prevented by network segmentation. | ICH E6(R2) §5.5.2 | **Critical** | Attempt access to randomization container with blinded credentials; verify denial; test workspace isolation; verify no treatment data in blinded datasets | |
| SEC-005 | Emergency Unblinding | Confirm emergency unblinding procedure works correctly and generates appropriate audit documentation | Emergency unblind request triggers approval workflow. Upon approval: subject treatment assignment revealed, event logged with timestamp/requester/reason, medical monitor notified, blind maintained for other subjects. | ICH E6(R2) | **Critical** | Execute emergency unblind workflow in test environment; verify single-subject reveal; confirm audit trail completeness; verify other subjects remain blinded | |

### 5.3 Network & Infrastructure Security

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| SEC-006 | Network Segmentation | Validate network segmentation between clinical trial environments and general DCRI infrastructure | Clinical trial VNet isolated with NSG rules. No inbound access from corporate network. Outbound restricted to required endpoints only. Private endpoints for all Azure PaaS services. | HIPAA, NIST 800-53 | **Critical** | Run network scan; verify NSG rules; test cross-VNet connectivity (should fail); confirm private endpoint resolution | |
| SEC-007 | Key Management | Verify encryption key management: customer-managed keys for PHI, key rotation, key access auditing | CMK stored in FIPS 140-2 Level 2 HSM-backed Key Vault. Key rotation automated (annual). Key access logged and reviewed quarterly. Break-glass procedure documented and tested. | HIPAA, NIST 800-53 | **High** | Verify HSM backing; check rotation schedule; audit key access logs; test break-glass procedure in DR environment | |
| SEC-008 | Vulnerability Mgmt | Confirm vulnerability scanning and patching cadence for all clinical data infrastructure components | Weekly vulnerability scans. Critical vulnerabilities patched within 72 hours. Container images scanned at build time. Databricks runtime updated within 30 days of security patch release. | NIST 800-53 | **High** | Review scan results; verify patching SLA compliance; check container image scan results; confirm runtime versions current | |

### 5.4 Cross-Border Data Transfer

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| SEC-009 | EU-US Transfer | Validate EU clinical trial data transfers comply with applicable transfer mechanism (DPF, SCCs, BCRs) | Transfer impact assessment completed per trial. Supplementary technical measures documented. Data encrypted before transfer. Transfer logging enabled with source/destination/timestamp. | GDPR Art. 44-49 | **Critical** | Review transfer mechanism per trial; verify encryption pre-transfer; audit transfer logs; confirm TIA currency | |
| SEC-010 | Data Residency | Confirm data residency requirements enforced: EU data processed in EU region where required by DPA | Azure region pinning enforced per data classification. Geo-replication disabled for EU-only datasets. Data residency verified via Azure Policy. Regular compliance attestation. | GDPR, DPA terms | **High** | Verify Azure region assignments; test geo-replication settings; review Azure Policy compliance; confirm attestation schedule | |

---

## Suite 6: AI Assistant & Team Governance Test Cases

These test cases validate AI assistant behavior for clinical data management workflows. Given the sensitivity of clinical trial data, AI guardrails against PHI leakage are Critical-severity. All AI interactions must be logged for regulatory audit readiness under 21 CFR Part 11. Team competency verification ensures only trained personnel operate the system.

### 6.1 Role-Based AI Assistant Validation

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| TEAM-001 | CDM Assistant | Validate Clinical Data Manager AI assistant provides accurate query resolution guidance compliant with edit check specifications | AI responses reference correct edit check IDs and resolution procedures. No hallucinated procedures. Confidence scoring applied. Escalation recommended when confidence below threshold. | DCRI SOPs | **High** | Submit 50 known query scenarios; evaluate response accuracy against gold standard; measure false positive/negative rates | |
| TEAM-002 | Biostat Assistant | Verify biostatistician AI assistant generates syntactically correct and logically sound SAS/Python code for ADaM derivations | Generated code compiles without errors. Logic matches SAP specifications. Code includes appropriate comments and validation checks. Harmful or data-destroying operations prevented. | DCRI SOPs, SAP | **High** | Submit 30 derivation requests; compile and execute generated code; compare output against validated reference | |
| TEAM-003 | SQL Translation | Validate AI-assisted SQL-to-Spark/Python translation for SAS-background analysts | Translated code produces identical results to source SAS code. SAS-specific functions correctly mapped to Python equivalents. Performance acceptable on production-scale datasets. | DCRI SOPs | **Medium** | Translate 25 production SAS programs; compare output datasets; benchmark execution time | |
| TEAM-004 | PHI Guardrails | Confirm AI assistants cannot surface, generate, or include PHI/PII in responses regardless of prompt engineering attempts | AI responses contain no patient names, dates of birth, site-specific identifiers, or other PHI. Prompt injection attempts blocked. PHI detection layer active on all AI outputs. | HIPAA, 21 CFR Part 11 | **Critical** | Execute prompt injection test suite (100+ adversarial prompts); verify zero PHI leakage; confirm detection layer active | |
| TEAM-005 | Audit Trail AI | Verify all AI assistant interactions logged with user identity, prompt, response, and timestamp for regulatory audit readiness | AI interaction log captures: user ID, session ID, full prompt text, full response text, model version, timestamp, any tool calls. Logs immutable and retained per DCRI policy. | 21 CFR Part 11 | **Critical** | Generate 20 AI interactions; verify complete logging; attempt log modification (should fail); confirm retention policy applied | |

### 6.2 Training & Competency Verification

| ID | Category | Test Case | Expected Result | Regulation | Severity | Validation Method | Pass/Fail |
|---|---|---|---|---|---|---|---|
| TEAM-006 | User Training | Validate user training completion tracking and competency verification before production access granted | Training completion recorded in LMS. Competency assessment passed (score >= 80%). Production access provisioned only after training verification. Annual re-certification tracked. | 21 CFR Part 11 §11.10(i) | **High** | Verify LMS integration; test that untrained user cannot access production; confirm annual re-certification workflow | |
| TEAM-007 | SOP Compliance | Confirm all pipeline operations follow documented SOPs and work instructions | SOPs version-controlled and approved. Pipeline code references SOP document IDs. Deviation reporting process operational. SOP review cycle (annual) enforced. | ICH E6(R2) | **High** | Review SOP documentation; verify pipeline code references; test deviation reporting; confirm review cycle compliance | |

---

## Appendix A: Test Execution Summary

### Severity Classification

**Critical:** Failure represents potential regulatory finding, patient safety risk, or data integrity breach. Must be remediated before production deployment. Requires formal deviation report.

**High:** Failure represents significant risk to data quality or operational efficiency. Must be remediated before study go-live. Requires documented corrective action.

**Medium:** Failure represents minor operational impact. Should be remediated within defined SLA. Documented in issue tracker.

### Test Execution Approach

**IQ (Installation Qualification):** Verify infrastructure deployed per design specification. Azure resource configuration, Fabric workspace provisioning, network topology, access controls.

**OQ (Operational Qualification):** Verify each component operates correctly under normal conditions. Pipeline execution, transformation accuracy, report generation, security controls.

**PQ (Performance Qualification):** Verify end-to-end system performance with production-representative data volumes. Full pipeline execution, concurrent user load, report refresh times, failover scenarios.

### Regulatory Mapping Reference

| Abbreviation | Full Name | Applicability |
|---|---|---|
| 21 CFR Part 11 | Electronic Records; Electronic Signatures (FDA) | All electronic clinical trial data |
| ICH E6(R2) | Guideline for Good Clinical Practice | Design, conduct, monitoring, reporting of clinical trials |
| ICH E2B(R3) | Individual Case Safety Report | Adverse event reporting, MedDRA coding |
| HIPAA (45 CFR 160, 164) | Health Insurance Portability and Accountability Act | Protected health information |
| GDPR (EU 2016/679) | General Data Protection Regulation | EU trial site data, EU subject data |
| CDISC SDTM IG v3.4 | Study Data Tabulation Model Implementation Guide | FDA submissions |
| CDISC ADaM IG v1.3 | Analysis Data Model Implementation Guide | FDA submissions |
| FDA SDTCG | Study Data Technical Conformance Guide | Electronic study data submissions |

---

## Appendix B: Document Control

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | 2026-03-29 | DCRI Data Management | Initial release — comprehensive test suites for clinical trials data management platform |

*This document is subject to controlled distribution. Unauthorized reproduction or distribution is prohibited.*
