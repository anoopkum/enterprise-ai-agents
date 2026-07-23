"""
Builds the KYC/AML knowledge graph from the entity CSVs:
  customer_profiles.csv  → (Customer), (Country), (Watchlist) + edges
  customer_documents.csv → (Document) + (Customer)-[:HAS_DOCUMENT]->
  kyc_cases.csv          → (KYCCase) + (Customer)-[:HAS_CASE]->
  aml_rules.csv          → (AMLRule)-[:APPLIES_IN]->(Country)
  kyc_guidelines.csv     → (Guideline)-[:IMPLEMENTS]->(AMLRule)

These CSVs are large (100k customers, 2M documents). We cap loads via env so the
graph builds quickly for a demo; raise the caps for a full ingest.

Writes go through the store's bulk_upsert_* (UNWIND batches) — one network
round-trip per BATCH_SIZE rows, not per row, which matters against cloud Neo4j.
"""
import csv
import logging
import os

from src.config import config
from src.graph import schema as S
from src.graph.store import graph_store

logger = logging.getLogger(__name__)

MAX_CUSTOMERS = int(os.environ.get("MAX_GRAPH_CUSTOMERS", "5000"))
MAX_DOCUMENTS = int(os.environ.get("MAX_GRAPH_DOCUMENTS", "20000"))
MAX_CASES = int(os.environ.get("MAX_GRAPH_CASES", "5000"))
MAX_RULES = int(os.environ.get("MAX_GRAPH_RULES", "3000"))
MAX_GUIDELINES = int(os.environ.get("MAX_GRAPH_GUIDELINES", "10000"))
BATCH_SIZE = int(os.environ.get("GRAPH_BATCH_SIZE", "1000"))


def _rows(path: str, limit: int):
    if not os.path.exists(path):
        logger.warning("Graph source missing: %s", path)
        return
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            yield row


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def _flush_nodes(label, key_prop, buf):
    graph_store.bulk_upsert_nodes(label, key_prop, buf)
    buf.clear()


def _flush_edges(src_label, rel, dst_label, buf):
    graph_store.bulk_upsert_edges(src_label, rel, dst_label, buf)
    buf.clear()


def build_graph(data_dir: str | None = None) -> dict:
    data_dir = data_dir or config.data_dir

    # 1) Customers → country, watchlist flags.
    loaded_customers: set[str] = set()
    cust_nodes, country_nodes, wl_nodes = [], [], []
    resident_edges, flag_edges = [], []
    seen_countries: set[str] = set()

    def flush_customers():
        _flush_nodes(S.CUSTOMER, "customer_id", cust_nodes)
        _flush_nodes(S.COUNTRY, "name", country_nodes)
        _flush_nodes(S.WATCHLIST, "name", wl_nodes)
        _flush_edges(S.CUSTOMER, S.RESIDENT_OF, S.COUNTRY, resident_edges)
        _flush_edges(S.CUSTOMER, S.FLAGGED_AS, S.WATCHLIST, flag_edges)

    # Ensure watchlist nodes exist once.
    wl_nodes.extend([
        {"key": "PEP", "props": {"name": "PEP", "kind": "PEP"}},
        {"key": "Sanction", "props": {"name": "Sanction", "kind": "Sanction"}},
    ])

    for row in _rows(os.path.join(data_dir, "customer_profiles.csv"), MAX_CUSTOMERS):
        cid = row.get("CustomerID", "").strip()
        if not cid:
            continue
        cust_nodes.append({"key": cid, "props": {
            "full_name": row.get("FullName", ""),
            "nationality": row.get("Nationality", ""),
            "occupation": row.get("Occupation", ""),
            "income": row.get("Income", ""),
            "risk_category": row.get("RiskCategory", ""),
            "pep_status": row.get("PEPStatus", ""),
            "sanction_status": row.get("SanctionStatus", ""),
            "aml_flag": row.get("AMLFlag", ""),
            "identity_verified": row.get("IdentityVerified", ""),
            "address_verified": row.get("AddressVerified", ""),
        }})
        loaded_customers.add(cid)

        country = row.get("Country", "").strip()
        if country:
            if country not in seen_countries:
                country_nodes.append({"key": country, "props": {"name": country}})
                seen_countries.add(country)
            resident_edges.append((cid, country))
        if _truthy(row.get("PEPStatus", "")):
            flag_edges.append((cid, "PEP"))
        if _truthy(row.get("SanctionStatus", "")):
            flag_edges.append((cid, "Sanction"))

        if len(cust_nodes) >= BATCH_SIZE:
            flush_customers()
    flush_customers()
    logger.info("Graph: loaded %d customers", len(loaded_customers))

    # 2) Documents
    doc_nodes, doc_edges = [], []
    doc_count = 0
    for row in _rows(os.path.join(data_dir, "customer_documents.csv"), MAX_DOCUMENTS):
        cid = row.get("CustomerID", "").strip()
        did = row.get("DocumentID", "").strip()
        if cid not in loaded_customers or not did:
            continue
        doc_nodes.append({"key": did, "props": {
            "document_type": row.get("DocumentType", ""),
            "document_number": row.get("DocumentNumber", ""),
            "issue_country": row.get("IssueCountry", ""),
            "expiry_date": row.get("ExpiryDate", ""),
            "verified": row.get("Verified", ""),
            "confidence": row.get("Confidence", ""),
        }})
        doc_edges.append((cid, did))
        doc_count += 1
        if len(doc_nodes) >= BATCH_SIZE:
            _flush_nodes(S.DOCUMENT, "document_id", doc_nodes)
            _flush_edges(S.CUSTOMER, S.HAS_DOCUMENT, S.DOCUMENT, doc_edges)
    _flush_nodes(S.DOCUMENT, "document_id", doc_nodes)
    _flush_edges(S.CUSTOMER, S.HAS_DOCUMENT, S.DOCUMENT, doc_edges)
    logger.info("Graph: loaded %d documents", doc_count)

    # 3) KYC cases
    case_nodes, case_edges = [], []
    case_count = 0
    for row in _rows(os.path.join(data_dir, "kyc_cases.csv"), MAX_CASES):
        cid = row.get("CustomerID", "").strip()
        case_id = row.get("CaseID", "").strip()
        if cid not in loaded_customers or not case_id:
            continue
        case_nodes.append({"key": case_id, "props": {
            "risk_category": row.get("RiskCategory", ""),
            "aml_flag": row.get("AMLFlag", ""),
            "expected_decision": row.get("ExpectedDecision", ""),
            "decision_reason": row.get("DecisionReason", ""),
            "verified_documents": row.get("VerifiedDocuments", ""),
        }})
        case_edges.append((cid, case_id))
        case_count += 1
        if len(case_nodes) >= BATCH_SIZE:
            _flush_nodes(S.KYC_CASE, "case_id", case_nodes)
            _flush_edges(S.CUSTOMER, S.HAS_CASE, S.KYC_CASE, case_edges)
    _flush_nodes(S.KYC_CASE, "case_id", case_nodes)
    _flush_edges(S.CUSTOMER, S.HAS_CASE, S.KYC_CASE, case_edges)
    logger.info("Graph: loaded %d cases", case_count)

    # 4) AML rules → country
    rule_nodes, applies_edges = [], []
    rule_count = 0
    for row in _rows(os.path.join(data_dir, "aml_rules.csv"), MAX_RULES):
        rid = row.get("RuleID", "").strip()
        if not rid:
            continue
        rule_nodes.append({"key": rid, "props": {
            "title": row.get("RuleTitle", ""),
            "category": row.get("RuleCategory", ""),
            "text": row.get("RuleText", ""),
            "country": row.get("Country", ""),
            "priority": row.get("Priority", ""),
        }})
        country = row.get("Country", "").strip() or "Global"
        if country not in seen_countries:
            country_nodes.append({"key": country, "props": {"name": country}})
            seen_countries.add(country)
        applies_edges.append((rid, country))
        rule_count += 1
        if len(rule_nodes) >= BATCH_SIZE:
            _flush_nodes(S.COUNTRY, "name", country_nodes)
            _flush_nodes(S.AML_RULE, "rule_id", rule_nodes)
            _flush_edges(S.AML_RULE, S.APPLIES_IN, S.COUNTRY, applies_edges)
    _flush_nodes(S.COUNTRY, "name", country_nodes)
    _flush_nodes(S.AML_RULE, "rule_id", rule_nodes)
    _flush_edges(S.AML_RULE, S.APPLIES_IN, S.COUNTRY, applies_edges)
    logger.info("Graph: loaded %d AML rules", rule_count)

    # 5) Guidelines → rule
    guide_nodes, impl_edges = [], []
    guide_count = 0
    for row in _rows(os.path.join(data_dir, "kyc_guidelines.csv"), MAX_GUIDELINES):
        gid = row.get("GuidelineID", "").strip()
        rid = row.get("RuleID", "").strip()
        if not gid:
            continue
        guide_nodes.append({"key": gid, "props": {
            "section": row.get("Section", ""),
            "paragraph": row.get("Paragraph", ""),
            "rule_id": rid,
            "effective_date": row.get("EffectiveDate", ""),
        }})
        if rid:
            impl_edges.append((gid, rid))
        guide_count += 1
        if len(guide_nodes) >= BATCH_SIZE:
            _flush_nodes(S.GUIDELINE, "guideline_id", guide_nodes)
            _flush_edges(S.GUIDELINE, S.IMPLEMENTS, S.AML_RULE, impl_edges)
    _flush_nodes(S.GUIDELINE, "guideline_id", guide_nodes)
    _flush_edges(S.GUIDELINE, S.IMPLEMENTS, S.AML_RULE, impl_edges)
    logger.info("Graph: loaded %d guidelines", guide_count)

    stats = graph_store.stats()
    logger.info("Graph build complete: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_graph()
