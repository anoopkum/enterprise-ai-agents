"""
Knowledge-graph schema — the labels and relationships the KYC/AML graph uses.

    (Customer)-[:HAS_DOCUMENT]->(Document)
    (Customer)-[:HAS_CASE]->(KYCCase)
    (Customer)-[:RESIDENT_OF]->(Country)
    (Customer)-[:FLAGGED_AS]->(Watchlist)      # PEP / Sanction
    (AMLRule)-[:APPLIES_IN]->(Country)
    (Guideline)-[:IMPLEMENTS]->(AMLRule)

GraphRAG uses these to walk from a customer to the regulations that govern them:
    Customer → RESIDENT_OF → Country ← APPLIES_IN ← AMLRule ← IMPLEMENTS ← Guideline
"""

# Node labels
CUSTOMER = "Customer"
DOCUMENT = "Document"
KYC_CASE = "KYCCase"
COUNTRY = "Country"
WATCHLIST = "Watchlist"
AML_RULE = "AMLRule"
GUIDELINE = "Guideline"

# Relationship types
HAS_DOCUMENT = "HAS_DOCUMENT"
HAS_CASE = "HAS_CASE"
RESIDENT_OF = "RESIDENT_OF"
FLAGGED_AS = "FLAGGED_AS"
APPLIES_IN = "APPLIES_IN"
IMPLEMENTS = "IMPLEMENTS"

# Uniqueness constraints created on the Neo4j backend (id property per label).
CONSTRAINTS = [
    (CUSTOMER, "customer_id"),
    (DOCUMENT, "document_id"),
    (KYC_CASE, "case_id"),
    (COUNTRY, "name"),
    (WATCHLIST, "name"),
    (AML_RULE, "rule_id"),
    (GUIDELINE, "guideline_id"),
]
