"""
Chunking for parsed documents (the non-CSV files). Regulatory CSV rows are already
one-chunk-each (see kb_loader); this handles free-text documents.

Strategy:
  markdown/html → header-aware split, then size-bound recursive split
  everything else → recursive character split with overlap
"""
import logging

from src.ingestion.models import Chunk, ParsedDocument

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def chunk_document(doc: ParsedDocument) -> list[Chunk]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if not doc.text.strip():
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
    )
    pieces = splitter.split_text(doc.text)

    chunks: list[Chunk] = []
    for i, piece in enumerate(pieces):
        piece = piece.strip()
        if not piece:
            continue
        chunks.append(Chunk(
            chunk_id=Chunk.make_id(doc.source_path, i, piece),
            text=piece,
            source_path=doc.source_path,
            source_format=doc.source_format,
            doc_type=doc.doc_type,
            confidence=doc.confidence,
            metadata={
                "chunk_index": i,
                "ocr_engine": doc.ocr_engine,
                "reference": doc.doc_type,
                **{f"field_{k}": v for k, v in list(doc.fields.items())[:10]},
            },
        ))
    logger.debug("Chunked %s into %d pieces", doc.source_path, len(chunks))
    return chunks
