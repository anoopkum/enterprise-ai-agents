"""
Natural-language RAG query service — the read path behind the Streamlit UI.

Two selectable corpora, each backed by its own vector-store index/collection:
  - "regulatory" : the live kyc-regulatory-kb (AML rules + KYC guidelines) that
                   also serves /screen. Read-only here; already seeded elsewhere.
  - "travel"     : the six OCR'd travel brochures under data/extracted/. Ingested
                   on demand into a SEPARATE index so it never pollutes screening.

answer_query() runs the standard retrieve → rerank → synthesize chain and returns
the answer plus the exact source chunks it was grounded in. When no Foundry LLM is
configured it degrades to an extractive answer built from the top chunks, so the UI
is useful with zero cloud reasoning — the Day 01/02 progressive-fallback contract.
"""
import glob
import logging
import os
from dataclasses import dataclass
from typing import Any

from src.config import config
from src.agents.llm import llm
from src.ingestion.models import Chunk
from src.pipeline.chunker import chunk_document
from src.pipeline.reranker import reranker
from src.pipeline.vector_store import VectorStore

logger = logging.getLogger(__name__)

TRAVEL_INDEX = os.environ.get("TRAVEL_SEARCH_INDEX", "travel-kb")
TRAVEL_COLLECTION = "travel_kb"
EXTRACTED_DIR = os.path.join(config.data_dir, "extracted")

RAG_SYSTEM_PROMPT = """
You answer questions using ONLY the numbered sources provided. Ground every claim
in a source and cite it inline as [n] using the source's number. If the sources do
not contain the answer, say so plainly — do not invent facts.

Output ONLY this JSON object:
{
  "answer": "<concise answer, 1-4 sentences, with inline [n] citations>",
  "citations": [<source numbers actually used, e.g. 1, 3>],
  "grounded": <true if the answer is supported by the sources, else false>
}
NEVER output anything except the JSON object.
"""


@dataclass
class Corpus:
    key: str
    label: str
    store: VectorStore
    description: str = ""


# Lazily-constructed stores keyed by corpus. VectorStore() itself is cheap (no
# network until first use), but we still memoise so the UI reuses one client.
_corpora: dict[str, Corpus] = {}


def get_corpus(key: str) -> Corpus:
    if key not in _corpora:
        if key == "regulatory":
            _corpora[key] = Corpus(
                key, "Regulatory KB (AML rules + KYC guidelines)",
                VectorStore(),  # defaults → kyc-regulatory-kb / kyc_regulatory_kb
                "The compliance knowledge base that also powers /screen.",
            )
        elif key == "travel":
            _corpora[key] = Corpus(
                key, "Travel brochures (Document Intelligence OCR)",
                VectorStore(index_name=TRAVEL_INDEX, collection_name=TRAVEL_COLLECTION),
                "Margie's Travel brochures, OCR'd with Azure Document Intelligence.",
            )
        else:
            raise ValueError(f"Unknown corpus: {key!r}")
    return _corpora[key]


def available_corpora() -> list[dict[str, str]]:
    return [
        {"key": "regulatory", "label": "Regulatory KB (AML rules + KYC guidelines)"},
        {"key": "travel", "label": "Travel brochures (Document Intelligence OCR)"},
    ]


def _load_travel_chunks() -> list[Chunk]:
    """Chunk the OCR'd travel .txt files under data/extracted/ for indexing."""
    from src.ingestion.models import ParsedDocument

    chunks: list[Chunk] = []
    for path in sorted(glob.glob(os.path.join(EXTRACTED_DIR, "*.txt"))):
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
        if not text:
            continue
        title = os.path.splitext(os.path.basename(path))[0]
        doc = ParsedDocument(
            source_path=path, source_format="pdf", text=text,
            doc_type="travel_brochure", ocr_used=True,
            ocr_engine="document_intelligence", confidence=0.95,
            metadata={"reference": title},
        )
        for c in chunk_document(doc):
            c.metadata["reference"] = title
            chunks.append(c)
    return chunks


def ingest_travel_corpus() -> int:
    """Index the travel extractions into their own store. Idempotent-ish: skips
    when the corpus already has documents (same guard the startup seed uses)."""
    corpus = get_corpus("travel")
    existing = corpus.store.document_count()
    if existing and existing > 0:
        logger.info("Travel corpus already has %d docs — skipping ingest", existing)
        return existing
    chunks = _load_travel_chunks()
    if not chunks:
        logger.warning("No travel extractions found under %s", EXTRACTED_DIR)
        return 0
    return corpus.store.upsert(chunks)


def _format_sources(hits: list[dict]) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        ref = (h.get("metadata") or {}).get("reference") or h.get("chunk_id") or ""
        tag = f" ({ref})" if ref else ""
        lines.append(f"[{i}]{tag} {h.get('text', '').strip()}")
    return "\n\n".join(lines)


def _extractive_answer(hits: list[dict]) -> dict[str, Any]:
    """No-LLM fallback: surface the top chunk verbatim as the answer."""
    if not hits:
        return {"answer": "No relevant content found in this corpus.",
                "citations": [], "grounded": False}
    top = hits[0].get("text", "").strip()
    snippet = top if len(top) <= 600 else top[:600].rsplit(" ", 1)[0] + "…"
    return {"answer": snippet, "citations": [1], "grounded": True}


def answer_query(question: str, corpus_key: str = "regulatory",
                 top_k_retrieve: int | None = None,
                 top_k_rerank: int | None = None) -> dict[str, Any]:
    """Retrieve → rerank → synthesize a grounded answer for a natural-language query."""
    corpus = get_corpus(corpus_key)
    hits = corpus.store.search(question, top_k=top_k_retrieve or config.top_k_retrieve)
    ranked = reranker.rerank(question, hits, top_k=top_k_rerank or config.top_k_rerank)

    if not ranked:
        return {
            "question": question, "corpus": corpus_key,
            "answer": "No relevant content found in this corpus.",
            "citations": [], "grounded": False, "assessment_source": "none",
            "sources": [],
        }

    payload = {"question": question, "sources": _format_sources(ranked)}
    result = llm.complete_json("kyc-rag-qa", RAG_SYSTEM_PROMPT, payload)
    source = "llm"
    if result is None or "answer" not in result:
        result = _extractive_answer(ranked)
        source = "fallback"

    return {
        "question": question,
        "corpus": corpus_key,
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "grounded": bool(result.get("grounded", False)),
        "assessment_source": source,
        "sources": [
            {
                "n": i,
                "text": h.get("text", ""),
                "score": round(float(h.get("rerank_score", h.get("score", 0.0)) or 0.0), 4),
                "reference": (h.get("metadata") or {}).get("reference", ""),
                "doc_type": (h.get("metadata") or {}).get("doc_type", ""),
            }
            for i, h in enumerate(ranked, 1)
        ],
    }
