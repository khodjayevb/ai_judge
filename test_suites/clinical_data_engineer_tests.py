"""
Test suite for Clinical Trials Data Engineer — based on DCRI test suites.

Covers: EDC ingestion, SDTM/ADaM transformation, data quality,
medical coding, SAS-to-Spark parity, and regulatory compliance.
Criteria mapped to FDA 21 CFR Part 11, ICH GCP E6(R2), CDISC standards.
"""

TEST_CASES = [
    # ── Regulatory & Compliance (from Suite 1) ────────────────────────
    {
        "id": "REG-001",
        "category": "Regulatory Compliance",
        "question": (
            "How should we implement audit trails for our EDC-to-ADLS Gen2 "
            "landing zone pipeline to comply with FDA 21 CFR Part 11?"
        ),
        "criteria": [
            "Recommends immutable, append-only storage (e.g., ADLS immutability policies) for audit records",
            "Specifies audit trail must capture: original value, new value, user ID, UTC timestamp, and reason for change per §11.10(e)",
            "States that audit records must not be modifiable or deletable by any role including system administrators",
            "Recommends managed identities for service-level actions (no shared accounts) per §11.10(d)",
            "Mentions ALCOA+ principles (Attributable, Legible, Contemporaneous, Original, Accurate)",
        ],
        "weight": 3,
    },
    {
        "id": "REG-002",
        "category": "Regulatory Compliance",
        "question": (
            "We need to ensure our clinical data pipeline meets HIPAA requirements "
            "for PHI protection. What encryption and de-identification approach "
            "should we use in our Azure/Fabric environment?"
        ),
        "criteria": [
            "Recommends Safe Harbor de-identification method removing all 18 HIPAA identifiers before the analytics layer",
            "Specifies AES-256 encryption at rest for all data stores containing PHI",
            "Requires TLS 1.2+ for all data transfers (EDC-to-Azure, inter-service, user access)",
            "Recommends Azure Key Vault with customer-managed keys for PHI-containing storage",
            "Mentions comprehensive access logging for PHI resources with minimum 6-year retention",
        ],
        "weight": 3,
    },
    # ── CDISC Data Standards (from Suite 2) ───────────────────────────
    {
        "id": "CDISC-001",
        "category": "CDISC Standards",
        "question": (
            "How do we implement SDTM transformation in Databricks/Spark to "
            "ensure conformance with SDTM IG v3.4? What validation should we run?"
        ),
        "criteria": [
            "References SDTM IG v3.4 specifically and describes variable naming, labels, types, and length requirements",
            "Recommends Pinnacle 21 (OpenCDISC) validation with zero structural errors as the acceptance criterion",
            "Describes mapping specification documentation (source-to-target for each transformation rule)",
            "Mentions timing variable requirements: VISIT, VISITNUM, --DTC in ISO 8601, --DY calculated from RFSTDTC",
            "Recommends unit test coverage >95% of mapping rules with reconciliation counts between source and target",
        ],
        "weight": 3,
    },
    {
        "id": "CDISC-002",
        "category": "CDISC Standards",
        "question": (
            "Explain how to build ADaM datasets (ADSL, BDS, OCCDS) from SDTM "
            "in our Fabric/Databricks environment. What derived variables and "
            "population flags are required?"
        ),
        "criteria": [
            "Describes ADaM IG v1.3 dataset structures: ADSL (subject-level), BDS (basic data structure), OCCDS (occurrence)",
            "Lists key derived variables: AVAL, AVALC, CHG, PCHG, BASE, ABLFL, ANL01FL with correct derivation logic",
            "Describes population flags: SAFFL, ITTFL, FASFL, PPROTFL, COMPLFL and that they must match SAP definitions",
            "Requires define.xml v2.1 with computational algorithms for all derived variables",
            "Recommends double-programming (independent re-derivation) for 100% validation of ADaM outputs",
        ],
        "weight": 3,
    },
    {
        "id": "CDISC-003",
        "category": "CDISC Standards",
        "question": (
            "How should we implement MedDRA coding for adverse events and "
            "WHODrug coding for concomitant medications in our data pipeline?"
        ),
        "criteria": [
            "Describes MedDRA hierarchy correctly: LLT (Lowest Level Term), PT (Preferred Term), HLT, HLGT, SOC (System Organ Class)",
            "Mentions WHODrug Global with ATC classification for concomitant medication coding",
            "Recommends tracking dictionary version in dataset metadata and documenting auto-coding vs manual coding",
            "Addresses dictionary version upgrades: remapping existing terms, before/after comparison, no loss of granularity",
            "References ICH E2B(R3) for adverse event reporting standards",
        ],
        "weight": 2,
    },
    # ── Data Pipeline (from Suite 3) ──────────────────────────────────
    {
        "id": "PIPE-001",
        "category": "Data Pipeline",
        "question": (
            "Design an EDC ingestion pipeline from Medidata Rave to ADLS Gen2 "
            "that handles incremental loads, schema evolution, and error "
            "quarantine for a multi-site clinical trial."
        ),
        "criteria": [
            "Describes incremental/delta load based on EDC audit trail timestamps (not full reload)",
            "Recommends error quarantine pattern: malformed records routed to error lakehouse, pipeline continues for valid data",
            "Addresses schema evolution: new fields from protocol amendments handled without data loss or pipeline failure",
            "Requires record count reconciliation between EDC source and landing zone (within 0.01% tolerance)",
            "Specifies that landing zone must preserve full history (original records never overwritten, per ALCOA+ 'Original')",
        ],
        "weight": 3,
    },
    {
        "id": "PIPE-002",
        "category": "Data Pipeline",
        "question": (
            "Our team is migrating SAS programs to PySpark for ADaM generation. "
            "How do we validate that Spark-generated datasets match SAS reference "
            "outputs?"
        ),
        "criteria": [
            "Recommends numeric precision comparison to 10 decimal places minimum",
            "Addresses SAS vs Python date arithmetic differences and how to handle them",
            "Describes double-programming approach: independent re-derivation as gold-standard validation",
            "Recommends variable-by-variable comparison with pre-defined tolerance thresholds",
            "Mentions documenting any numerical differences exceeding tolerance with root cause explanation",
        ],
        "weight": 3,
    },
    {
        "id": "PIPE-003",
        "category": "Data Pipeline",
        "question": (
            "How should we implement data quality checks at each pipeline stage "
            "(landing, SDTM, ADaM) for our clinical trial data?"
        ),
        "criteria": [
            "Describes checks across four dimensions: completeness, conformance, plausibility, and uniqueness",
            "Recommends critical DQ failures halt downstream processing (no propagation of bad data)",
            "Mentions DQ dashboards with missing data rates per variable, site, and visit",
            "Describes conformance rules: range checks, controlled terminology validation, cross-field logic",
            "Recommends plausibility monitoring: outlier detection, site-level pattern comparison against study-wide distribution",
        ],
        "weight": 2,
    },
    # ── Security & Unblinding ─────────────────────────────────────────
    {
        "id": "SEC-001",
        "category": "Security & Blinding",
        "question": (
            "How should we architect unblinding controls in Fabric/Azure to "
            "ensure only authorized unblinded personnel can access treatment "
            "assignment data?"
        ),
        "criteria": [
            "Recommends separate ADLS container for randomization data with dedicated access controls",
            "Describes workspace isolation: unblinded Fabric workspace separated from blinded workspaces",
            "Specifies that blinded team members receive ADaM datasets with treatment columns masked or removed",
            "Describes emergency unblinding workflow: approval chain, single-subject reveal, audit documentation",
            "Requires access attempts by blinded personnel to be denied and logged per ICH E6(R2) §5.5.2",
        ],
        "weight": 3,
    },
    # ── Cross-Border / GDPR ───────────────────────────────────────────
    {
        "id": "GDPR-001",
        "category": "GDPR & Cross-Border",
        "question": (
            "Our trial has EU sites. How do we handle EU-to-US clinical data "
            "transfer and subject withdrawal (right to erasure) in our "
            "Azure pipeline?"
        ),
        "criteria": [
            "References EU-US Data Privacy Framework or Standard Contractual Clauses as transfer mechanism",
            "Requires Transfer Impact Assessment (TIA) documented per trial",
            "Specifies pseudonymization and encryption applied before cross-border transfer",
            "Describes right-to-erasure workflow: withdrawal propagates through all pipeline stages, anonymization within 30 days",
            "Mentions data minimization: only protocol-required data elements collected and processed per GDPR Art. 5(1)(c)",
        ],
        "weight": 2,
    },
    # ── AI Governance ─────────────────────────────────────────────────
    {
        "id": "AI-001",
        "category": "AI Governance",
        "question": (
            "How should we ensure AI assistants used by our clinical data "
            "team don't leak PHI and that all interactions are audit-ready "
            "under 21 CFR Part 11?"
        ),
        "criteria": [
            "Recommends PHI detection layer on all AI outputs to prevent surface, generation, or inclusion of PHI",
            "Requires logging of all AI interactions: user ID, session ID, full prompt, full response, model version, timestamp",
            "Specifies AI interaction logs must be immutable and retained per DCRI policy",
            "Recommends prompt injection testing (adversarial prompts) to validate PHI guardrails",
            "Mentions confidence scoring for AI responses with escalation when confidence is below threshold",
        ],
        "weight": 2,
    },
    # ── Ambiguity Handling ────────────────────────────────────────────
    {
        "id": "AMB-001",
        "category": "Ambiguity Handling",
        "question": "How do we load the data?",
        "criteria": [
            "Asks clarifying questions about which data source (EDC system, lab feed, safety database?)",
            "Asks about destination (landing zone, SDTM, ADaM?) and whether this is initial or incremental",
            "Does not assume a single interpretation — offers multiple clinical trial data loading scenarios",
            "Stays within clinical trials context (not generic data engineering advice)",
            "May offer common patterns but emphasizes the need for protocol-specific requirements",
        ],
        "weight": 2,
    },
]

CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))
