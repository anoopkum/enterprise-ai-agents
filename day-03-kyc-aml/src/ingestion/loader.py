"""
Ingestion dispatcher. Routes each file to the correct parser by extension:
  scanned/image → OCR (Document Intelligence | PyMuPDF)
  office/text   → free local parsers
CSV knowledge-base files (aml_rules, kyc_guidelines) are handled separately by
the KB loader, so they are skipped here to avoid dumping 100k-row tables as text.
"""
import logging
import os
from collections.abc import Iterator

from src.ingestion.models import ParsedDocument
from src.ingestion import office_parsers as op
from src.ingestion.ocr import extract_document

logger = logging.getLogger(__name__)

# Large structured CSVs are loaded by kb_loader / graph builder, not as free text.
_SKIP_CSVS = {
    "aml_rules.csv", "kyc_guidelines.csv", "customer_profiles.csv",
    "customer_documents.csv", "kyc_cases.csv", "kyc_questions.csv",
    "ground_truth_answers.csv", "hallucinated_answers.csv",
    "hallucination_labels.csv", "hallucination_training_dataset.csv",
    "hallucination_training_dataset_v2.csv", "benchmark_dataset.csv",
    "nli_dataset.csv", "nli_dataset_dedup.csv",
}

_DISPATCH = {
    ".pdf": extract_document,
    ".jpg": extract_document,
    ".jpeg": extract_document,
    ".png": extract_document,
    ".docx": op.parse_docx,
    ".pptx": op.parse_pptx,
    ".html": op.parse_html,
    ".htm": op.parse_html,
    ".md": op.parse_markdown,
    ".txt": op.parse_text,
    ".xlsx": op.parse_excel,
    ".xls": op.parse_excel,
}


def parse_file(path: str) -> ParsedDocument | None:
    ext = os.path.splitext(path)[1].lower()
    parser = _DISPATCH.get(ext)
    if parser is None:
        logger.debug("No parser for %s — skipping", path)
        return None
    try:
        parsed = parser(path)
        logger.info("Parsed %s [%s/%s] → %d chars (ocr=%s conf=%.2f)",
                    os.path.basename(path), parsed.source_format, parsed.doc_type,
                    len(parsed.text), parsed.ocr_used, parsed.confidence)
        return parsed
    except Exception as exc:
        logger.error("Failed to parse %s: %s", path, exc)
        return None


def iter_documents(data_dir: str) -> Iterator[ParsedDocument]:
    """Walk data_dir and yield a ParsedDocument for every supported non-KB file."""
    for entry in sorted(os.listdir(data_dir)):
        full = os.path.join(data_dir, entry)
        if not os.path.isfile(full):
            continue
        if entry.lower().endswith(".csv") and entry in _SKIP_CSVS:
            continue
        parsed = parse_file(full)
        if parsed and parsed.text.strip():
            yield parsed
