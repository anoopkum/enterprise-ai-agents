"""
Loads the regulatory knowledge base from the two structured CSVs:
  aml_rules.csv       — RuleID, RuleTitle, RuleCategory, RuleText, Country, Priority, Version
  kyc_guidelines.csv  — GuidelineID, RuleID, Section, Paragraph, Version, EffectiveDate

Each row is one natural chunk (a rule / a guideline paragraph), so no splitting is
needed — this is the "header-aware chunking" the regulatory corpus wants.
"""
import csv
import logging
import os

from src.config import config
from src.ingestion.models import Chunk

logger = logging.getLogger(__name__)

# Some CSVs are large; cap rows loaded into the vector KB for a responsive demo.
MAX_RULES = int(os.environ.get("MAX_KB_RULES", "3000"))
MAX_GUIDELINES = int(os.environ.get("MAX_KB_GUIDELINES", "5000"))


def _read_csv(path: str, limit: int):
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            yield row


def load_regulatory_chunks(data_dir: str | None = None) -> list[Chunk]:
    data_dir = data_dir or config.data_dir
    chunks: list[Chunk] = []

    rules_path = os.path.join(data_dir, "aml_rules.csv")
    if os.path.exists(rules_path):
        for row in _read_csv(rules_path, MAX_RULES):
            rule_id = row.get("RuleID", "")
            text = (
                f"{row.get('RuleTitle', '')} ({row.get('RuleCategory', '')}). "
                f"{row.get('RuleText', '')}"
            ).strip()
            chunks.append(Chunk(
                chunk_id=f"aml-{rule_id}", text=text,
                source_path=rules_path, source_format="csv", doc_type="regulation",
                confidence=1.0,
                metadata={
                    "rule_id": rule_id,
                    "framework": "AML",
                    "category": row.get("RuleCategory", ""),
                    "country": row.get("Country", ""),
                    "priority": row.get("Priority", ""),
                    "version": row.get("Version", ""),
                    "reference": row.get("RuleTitle", ""),
                },
            ))
        logger.info("Loaded %d AML rule chunks", len(chunks))

    guide_path = os.path.join(data_dir, "kyc_guidelines.csv")
    if os.path.exists(guide_path):
        before = len(chunks)
        for row in _read_csv(guide_path, MAX_GUIDELINES):
            gid = row.get("GuidelineID", "")
            text = f"{row.get('Section', '')}: {row.get('Paragraph', '')}".strip()
            chunks.append(Chunk(
                chunk_id=f"guide-{gid}", text=text,
                source_path=guide_path, source_format="csv", doc_type="regulation",
                confidence=1.0,
                metadata={
                    "guideline_id": gid,
                    "rule_id": row.get("RuleID", ""),
                    "framework": "KYC",
                    "section": row.get("Section", ""),
                    "version": row.get("Version", ""),
                    "effective_date": row.get("EffectiveDate", ""),
                    "reference": row.get("Section", ""),
                },
            ))
        logger.info("Loaded %d KYC guideline chunks", len(chunks) - before)

    return chunks
