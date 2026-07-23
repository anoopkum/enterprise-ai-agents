"""
OCR / document understanding for scanned PDFs and images (JPEG/PNG).

Primary : Azure AI Document Intelligence (prebuilt-layout / prebuilt-idDocument)
          — real OCR, structured fields, per-field confidence.
Fallback: PyMuPDF text extraction (born-digital PDFs) — no cloud account needed.

This is the genuinely "multimodal" leg of the pipeline: scanned Aadhaar, passports,
and bank-statement images become structured text here.
"""
import logging
import os

from src.config import config
from src.ingestion.models import ParsedDocument
from src.ingestion.doc_classifier import classify

logger = logging.getLogger(__name__)

_ID_DOC_TYPES = {"passport", "aadhaar", "voter_id", "pan_card", "driving_licence"}


def extract_document(path: str) -> ParsedDocument:
    """Route an image/PDF through Document Intelligence, else PyMuPDF."""
    fmt = "jpeg" if path.lower().endswith((".jpg", ".jpeg", ".png")) else "pdf"

    if config.use_doc_intelligence:
        try:
            return _extract_with_document_intelligence(path, fmt)
        except Exception as exc:
            logger.warning("Document Intelligence failed for %s (%s) — falling back to PyMuPDF", path, exc)

    return _extract_with_pymupdf(path, fmt)


def _extract_with_document_intelligence(path: str, fmt: str) -> ParsedDocument:
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
    from azure.identity import DefaultAzureCredential

    credential = (
        AzureKeyCredential(config.doc_intel_key)
        if config.doc_intel_key
        else DefaultAzureCredential()
    )
    client = DocumentIntelligenceClient(config.doc_intel_endpoint, credential)

    # Pre-classify by filename to choose the ID model where appropriate.
    prelim_type = classify(os.path.basename(path))
    model_id = "prebuilt-idDocument" if prelim_type in _ID_DOC_TYPES else "prebuilt-layout"

    with open(path, "rb") as f:
        poller = client.begin_analyze_document(model_id, body=f, content_type="application/octet-stream")
    result = poller.result()

    text = result.content or ""
    fields: dict = {}
    confidences: list[float] = []

    for doc in getattr(result, "documents", []) or []:
        for name, fld in (doc.fields or {}).items():
            value = getattr(fld, "content", None) or getattr(fld, "value_string", None)
            if value is not None:
                fields[name] = value
            if getattr(fld, "confidence", None) is not None:
                confidences.append(fld.confidence)

    confidence = sum(confidences) / len(confidences) if confidences else 0.9
    doc_type = classify(os.path.basename(path), text)

    logger.info("Document Intelligence [%s] parsed %s → %d chars, %d fields, conf=%.2f",
                model_id, os.path.basename(path), len(text), len(fields), confidence)

    return ParsedDocument(
        source_path=path, source_format=fmt, text=text, doc_type=doc_type,
        ocr_used=True, ocr_engine="document_intelligence",
        confidence=round(confidence, 3), fields=fields,
        metadata={"model_id": model_id},
    )


def _extract_with_pymupdf(path: str, fmt: str) -> ParsedDocument:
    text = ""
    engine = "pymupdf"
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(path)
        parts = [page.get_text() for page in doc]
        text = "\n".join(parts).strip()
        doc.close()
    except Exception as exc:
        logger.warning("PyMuPDF extraction failed for %s: %s", path, exc)
        engine = "none"

    doc_type = classify(os.path.basename(path), text)
    # Born-digital text is high confidence; empty text (scanned image, no OCR) is low.
    confidence = 0.95 if text else 0.2

    if not text:
        logger.warning(
            "No text extracted from %s. It is likely a scanned image — set "
            "DOC_INTELLIGENCE_ENDPOINT to enable real OCR.", os.path.basename(path)
        )

    return ParsedDocument(
        source_path=path, source_format=fmt, text=text, doc_type=doc_type,
        ocr_used=bool(text), ocr_engine=engine, confidence=confidence,
    )
