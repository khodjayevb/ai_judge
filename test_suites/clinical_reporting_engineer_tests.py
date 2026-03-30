"""
Test suite for Clinical Trials Reporting Engineer — based on DCRI test suites.

Covers: TLFs, DSMB safety reports, eCTD submissions, Power BI paginated
reports, safety signal detection, and report versioning.
Criteria mapped to FDA requirements, ICH GCP, CDISC ADaM, SAP.
"""

TEST_CASES = [
    # ── DSMB/DMC Safety Reports (from Suite 4.1) ─────────────────────
    {
        "id": "RPT-001",
        "category": "DSMB Reporting",
        "question": (
            "How should we automate DSMB safety report generation with "
            "unblinded treatment-group summaries while maintaining data "
            "integrity and reproducibility?"
        ),
        "criteria": [
            "Describes required DSMB report contents: AE summary by SOC/PT per treatment arm, SAE listings, enrollment summary, protocol deviations",
            "Recommends data lock/snapshot mechanism creating an immutable copy in a dedicated ADLS container",
            "Specifies that snapshot must have timestamp and hash recorded for reproducibility verification",
            "Addresses unblinding isolation: DSMB report generation runs in unblinded workspace only",
            "Requires that report regeneration from the same snapshot produces identical output (checksum match)",
        ],
        "weight": 3,
    },
    {
        "id": "RPT-002",
        "category": "DSMB Reporting",
        "question": (
            "Design a real-time safety signal detection system that alerts "
            "the medical monitor when SAE rates exceed thresholds."
        ),
        "criteria": [
            "Describes SAE rate monitoring with both site-specific and study-wide thresholds",
            "Specifies alert delivery to medical monitor within 1 hour per ICH E6(R2) §5.17",
            "Mentions SUSAR (Suspected Unexpected Serious Adverse Reaction) reporting timeline tracking",
            "Recommends per-protocol threshold configuration (not hardcoded values)",
            "Addresses audit trail for all safety alerts: who was notified, when, what action taken",
        ],
        "weight": 3,
    },
    # ── TLFs (from Suite 4.3) ─────────────────────────────────────────
    {
        "id": "TLF-001",
        "category": "TLF Generation",
        "question": (
            "How do we implement double-programming verification for our "
            "statistical TLFs to ensure accuracy? What tolerance thresholds "
            "should we use?"
        ),
        "criteria": [
            "Describes double-programming: primary programmer and independent QC programmer produce outputs separately",
            "Specifies tolerance thresholds: integers exact match, percentages within 0.1%, continuous values within 0.01%",
            "Requires cell-by-cell comparison between primary and QC outputs",
            "Mentions denominator population verification (correct N for each treatment arm/subgroup)",
            "Recommends documenting and resolving all discrepancies to root cause before sign-off",
        ],
        "weight": 3,
    },
    {
        "id": "TLF-002",
        "category": "TLF Generation",
        "question": (
            "How should we build Power BI paginated reports for clinical "
            "trial TLFs that meet GxP requirements? What are the key "
            "rendering and pagination considerations?"
        ),
        "criteria": [
            "Describes paginated reports as pixel-perfect format suitable for TLFs (not interactive Power BI)",
            "Specifies pagination requirements: no orphaned rows, column headers repeat on each page, footnotes positioned correctly",
            "Recommends parameterization by study, site, visit, and treatment arm",
            "Requires automatic refresh triggered by pipeline completion with data currency timestamp displayed",
            "Mentions testing with varying data volumes (sparse site vs large site) to verify rendering",
        ],
        "weight": 2,
    },
    # ── eCTD Submission (from Suite 4.2) ──────────────────────────────
    {
        "id": "SUB-001",
        "category": "Regulatory Submission",
        "question": (
            "What steps are needed to prepare SDTM/ADaM datasets and "
            "supporting documentation for an FDA eCTD submission?"
        ),
        "criteria": [
            "Requires SAS Transport (XPT) v5 format for all submission datasets",
            "Specifies define.xml v2.1 validated via Pinnacle 21 with zero errors",
            "Describes ADRG (Analysis Data Reviewer's Guide) with dataset inventory, derivation methodology, SAP crosswalk",
            "Mentions eCTD folder structure requirements and file size limits",
            "Recommends Pinnacle 21 full submission validation as final gate before packaging",
        ],
        "weight": 3,
    },
    # ── Report Versioning & Distribution ──────────────────────────────
    {
        "id": "VER-001",
        "category": "Versioning & Distribution",
        "question": (
            "How should we implement report versioning and distribution "
            "for DSMB and submission-ready TLF packages to maintain "
            "21 CFR Part 11 compliance?"
        ),
        "criteria": [
            "Recommends auto-incremented version numbers for each TLF package",
            "Specifies immutable archive storage for all previous versions",
            "Describes approval workflow before finalization (electronic signature with meaning per §11.50)",
            "Mentions version comparison capability to show differences between versions",
            "Requires distribution logging: who received which version, when, via what channel",
        ],
        "weight": 2,
    },
    # ── Safety Signal from Pipeline ───────────────────────────────────
    {
        "id": "SAF-001",
        "category": "Safety Monitoring",
        "question": (
            "Our medical monitor needs a dashboard showing AE and SAE "
            "rates by site, updated daily. How should we architect this "
            "in Fabric/Power BI with proper access controls?"
        ),
        "criteria": [
            "Describes data flow: ADaM AE dataset -> incremental refresh -> Power BI semantic model -> dashboard",
            "Addresses access control: only authorized safety team members can view unblinded AE summaries",
            "Recommends conditional alerting when site-specific SAE rates exceed study-wide mean by N standard deviations",
            "Mentions that dashboard must show data currency (last refresh timestamp) for GCP compliance",
            "Specifies Row-Level Security to restrict site-level views by role (site monitor sees only their sites)",
        ],
        "weight": 2,
    },
    # ── Guardrails ────────────────────────────────────────────────────
    {
        "id": "GUARD-001",
        "category": "Guardrails",
        "question": (
            "Can we just email the DSMB report as a PDF attachment to "
            "the committee members?"
        ),
        "criteria": [
            "Flags that DSMB reports contain unblinded data requiring secure distribution channels",
            "Recommends secure portal or encrypted file share over email attachments",
            "Mentions that email delivery lacks audit trail for regulatory compliance",
            "Suggests version control and access logging for all DSMB deliverables",
            "References 21 CFR Part 11 requirements for electronic record distribution",
        ],
        "weight": 2,
    },
    {
        "id": "GUARD-002",
        "category": "Guardrails",
        "question": (
            "One of our TLF tables doesn't match the QC output but the "
            "difference is tiny — just 0.3% on one percentage. Can we "
            "skip investigating and submit?"
        ),
        "criteria": [
            "Firmly states that ALL discrepancies must be investigated to root cause, regardless of magnitude",
            "References the tolerance thresholds (0.1% for percentages) — 0.3% exceeds tolerance",
            "Explains that unexplained discrepancies could indicate systematic errors affecting other outputs",
            "Recommends formal deviation documentation if any tolerance is waived",
            "Mentions that FDA reviewers may flag unexplained differences during review",
        ],
        "weight": 3,
    },
    # ── Ambiguity ─────────────────────────────────────────────────────
    {
        "id": "AMB-001",
        "category": "Ambiguity Handling",
        "question": "I need to create a report for the committee.",
        "criteria": [
            "Asks which committee (DSMB/DMC, IRB/EC, steering committee, sponsor)?",
            "Asks whether this is a scheduled interim or ad-hoc request",
            "Asks whether unblinded treatment data is required (determines security requirements)",
            "Asks about the data cut-off date and whether a data lock is needed",
            "Stays within clinical trial reporting context (does not give generic BI advice)",
        ],
        "weight": 2,
    },
]

CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))
