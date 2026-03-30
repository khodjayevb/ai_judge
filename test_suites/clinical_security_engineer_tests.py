"""
Test suite for Clinical Trials Security & Compliance Engineer — based on DCRI test suites.

Covers: PHI protection, unblinding controls, encryption, network security,
cross-border data transfer, audit trails, AI governance.
Criteria mapped to HIPAA, GDPR, 21 CFR Part 11, ICH GCP, NIST 800-53.
"""

TEST_CASES = [
    # ── PHI/PII Handling (from Suite 5.1) ─────────────────────────────
    {
        "id": "PHI-001",
        "category": "PHI Protection",
        "question": (
            "How should we implement Safe Harbor de-identification for "
            "clinical trial data before it enters the analytics layer in "
            "our Azure/Fabric environment?"
        ),
        "criteria": [
            "Lists the 18 HIPAA Safe Harbor identifiers that must be removed or generalized",
            "Describes date handling: dates shifted or generalized to year only (except ages 90+)",
            "Recommends automated de-identification validation script scanning all string fields for residual PHI patterns",
            "Mentions expert determination method as an alternative when statistical approach is needed",
            "Specifies that de-identification occurs BEFORE data enters ADaM/analytics layer, not after",
        ],
        "weight": 3,
    },
    {
        "id": "PHI-002",
        "category": "PHI Protection",
        "question": (
            "How do we implement pseudonymization with proper key management "
            "for subject identifiers across our clinical trial pipeline?"
        ),
        "criteria": [
            "Recommends pseudonymization key stored in Azure Key Vault with PIM (Privileged Identity Management) access",
            "Specifies that key access is restricted to authorized data management personnel only",
            "Mentions annual key rotation policy as minimum requirement",
            "Describes dynamic data masking for non-authorized viewers of PHI fields at query time",
            "References GDPR Art. 4(5) definition of pseudonymization and HIPAA §164.514",
        ],
        "weight": 3,
    },
    # ── Unblinding Controls (from Suite 5.2) ──────────────────────────
    {
        "id": "BLIND-001",
        "category": "Unblinding Controls",
        "question": (
            "Design the unblinding control architecture for a double-blind "
            "clinical trial in our Fabric environment. Include both routine "
            "operations and emergency unblinding."
        ),
        "criteria": [
            "Specifies randomization table in separate, access-controlled ADLS container",
            "Describes Fabric workspace isolation: unblinded workspace physically separated from blinded workspaces",
            "Requires that blinded ADaM datasets have treatment columns removed or masked (not just access-controlled)",
            "Describes emergency unblinding workflow: approval chain -> single-subject reveal -> audit log -> medical monitor notification",
            "Requires that emergency unblinding for one subject does NOT compromise blind for other subjects",
        ],
        "weight": 3,
    },
    # ── Encryption & Key Management (from Suite 5.3) ──────────────────
    {
        "id": "ENC-001",
        "category": "Encryption & Keys",
        "question": (
            "What encryption strategy should we use for clinical trial data "
            "at rest and in transit, including key management?"
        ),
        "criteria": [
            "Requires AES-256 encryption at rest for all data stores containing PHI",
            "Specifies customer-managed keys (CMK) in FIPS 140-2 Level 2 HSM-backed Key Vault",
            "Requires TLS 1.2+ for all data in transit with legacy TLS versions explicitly disabled",
            "Describes key rotation policy: annual minimum with automated rotation",
            "Mentions break-glass procedure for key access during disaster recovery",
        ],
        "weight": 3,
    },
    # ── Network Security ──────────────────────────────────────────────
    {
        "id": "NET-001",
        "category": "Network Security",
        "question": (
            "How should we design network security for our clinical trial "
            "environment in Azure to meet HIPAA and NIST 800-53 requirements?"
        ),
        "criteria": [
            "Requires VNet isolation: clinical trial VNet separated from general corporate infrastructure",
            "Specifies NSG rules: no inbound from corporate network, outbound restricted to required endpoints",
            "Requires private endpoints for ALL Azure PaaS services (no public endpoints for PHI-containing resources)",
            "Recommends VPN or ExpressRoute for EDC system connections (Rave, Veeva, etc.)",
            "Mentions weekly vulnerability scanning with critical CVE patching within 72 hours",
        ],
        "weight": 2,
    },
    # ── Cross-Border Transfer (from Suite 5.4) ────────────────────────
    {
        "id": "XBORDER-001",
        "category": "Cross-Border Transfer",
        "question": (
            "We have EU clinical trial sites sending subject data to our "
            "US-based Azure environment. What GDPR-compliant transfer "
            "mechanism should we implement?"
        ),
        "criteria": [
            "References EU-US Data Privacy Framework or Standard Contractual Clauses as valid transfer mechanisms",
            "Requires Transfer Impact Assessment (TIA) completed per trial before data flows",
            "Specifies technical safeguards: encryption and pseudonymization applied BEFORE cross-border transfer",
            "Mentions data residency enforcement via Azure Policy for EU-only datasets (geo-replication disabled)",
            "Recommends transfer logging with source, destination, and timestamp for audit purposes",
        ],
        "weight": 3,
    },
    # ── Audit & Logging ───────────────────────────────────────────────
    {
        "id": "AUDIT-001",
        "category": "Audit & Compliance",
        "question": (
            "How should we implement audit logging across our clinical trial "
            "data platform to satisfy 21 CFR Part 11 and HIPAA requirements?"
        ),
        "criteria": [
            "Requires immutable, append-only audit logs (ADLS immutability policy or equivalent)",
            "Specifies logging for every read/write/delete on PHI resources: user identity, resource, timestamp, action, source IP",
            "Mentions AI interaction logging: user ID, session ID, full prompt and response, model version, timestamp",
            "Requires minimum 6-year log retention (HIPAA) aligned with 15-year clinical data retention",
            "Describes quarterly access log review process for compliance verification",
        ],
        "weight": 2,
    },
    # ── Access Control ────────────────────────────────────────────────
    {
        "id": "RBAC-001",
        "category": "Access Control",
        "question": (
            "How should we implement role-based access control across our "
            "clinical trial pipeline stages (landing, SDTM, ADaM, reporting) "
            "following principle of least privilege?"
        ),
        "criteria": [
            "Describes distinct Fabric workspace roles per pipeline stage with explicit permission boundaries",
            "Specifies that data engineers cannot access unblinded ADaM datasets",
            "Specifies that biostatisticians have read-only access to SDTM, read-write to ADaM",
            "Requires Entra ID with MFA for all human users and managed identities for all service accounts",
            "Recommends PIM (Privileged Identity Management) for time-limited elevation of privileged access",
        ],
        "weight": 3,
    },
    # ── Guardrails ────────────────────────────────────────────────────
    {
        "id": "GUARD-001",
        "category": "Guardrails",
        "question": (
            "Our project manager says we can use a shared admin account for "
            "the data pipeline service to simplify credential management. "
            "Is that okay?"
        ),
        "criteria": [
            "Firmly states NO — shared accounts violate 21 CFR Part 11 §11.10(d) unique user identification requirements",
            "Explains that every action must be attributable to an individual for audit trail integrity",
            "Recommends managed identities for service accounts (no shared passwords)",
            "Cites specific regulation: 21 CFR Part 11 §11.10(d) requires unique identification",
            "Suggests Entra ID service principals with managed identity as the compliant alternative",
        ],
        "weight": 3,
    },
    # ── Ambiguity ─────────────────────────────────────────────────────
    {
        "id": "AMB-001",
        "category": "Ambiguity Handling",
        "question": "We need to set up access for a new team member.",
        "criteria": [
            "Asks what role the team member has (data engineer, biostatistician, clinical data manager, medical monitor?)",
            "Asks whether the person needs blinded or unblinded data access",
            "Asks which pipeline stages they need to access (landing, SDTM, ADaM, reporting)",
            "Asks whether training/competency verification has been completed per SOP",
            "Does not provide a generic access provisioning answer — stays in clinical trial context",
        ],
        "weight": 2,
    },
]

CATEGORIES = sorted(set(tc["category"] for tc in TEST_CASES))
