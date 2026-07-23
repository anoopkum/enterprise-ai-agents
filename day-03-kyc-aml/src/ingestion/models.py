"""Unified document/chunk models emitted by every parser, regardless of source format."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedDocument:
    """One source file after parsing — before chunking."""
    source_path: str
    source_format: str            # pdf | jpeg | docx | pptx | html | md | xlsx | xls | csv
    text: str
    doc_type: str = "unknown"     # passport | aadhaar | voter_id | bank_statement | regulation | ...
    ocr_used: bool = False
    ocr_engine: str = ""          # document_intelligence | pymupdf | none
    confidence: float = 1.0       # mean OCR confidence; 1.0 for born-digital text
    fields: dict[str, Any] = field(default_factory=dict)   # structured fields from Document Intelligence
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """A retrievable unit written to the vector store."""
    chunk_id: str
    text: str
    source_path: str
    source_format: str
    doc_type: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def make_id(source_path: str, index: int, text: str) -> str:
        h = hashlib.sha1(f"{source_path}:{index}:{text[:64]}".encode()).hexdigest()[:16]
        return f"chunk-{h}"
