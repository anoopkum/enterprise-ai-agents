"""
Unit tests for the natural-language RAG query service (Streamlit UI's read path).
Retrieval, rerank and LLM are all mocked so these run offline and deterministically.
"""
from unittest.mock import MagicMock

import pytest

import src.pipeline.rag_query as rq


HITS = [
    {"chunk_id": "c1", "text": "Enhanced due diligence applies to PEPs.",
     "score": 0.9, "metadata": {"reference": "AML-R100", "doc_type": "regulation"}},
    {"chunk_id": "c2", "text": "Standard due diligence covers ordinary customers.",
     "score": 0.5, "metadata": {"reference": "AML-R101", "doc_type": "regulation"}},
]


@pytest.fixture
def patched(monkeypatch):
    """Stub the corpus store + reranker; leave llm patchable per-test."""
    store = MagicMock()
    store.backend = "chromadb"
    store.search.return_value = list(HITS)
    corpus = rq.Corpus("regulatory", "Regulatory", store)
    monkeypatch.setattr(rq, "get_corpus", lambda key: corpus)
    monkeypatch.setattr(rq.reranker, "rerank", lambda q, hits, top_k=None: hits[:top_k or len(hits)])
    return store


@pytest.mark.unit
class TestAnswerQuery:
    def test_llm_answer_is_used_when_available(self, patched, monkeypatch):
        monkeypatch.setattr(rq.llm, "complete_json", MagicMock(return_value={
            "answer": "EDD applies to PEPs [1].", "citations": [1], "grounded": True,
        }))
        out = rq.answer_query("When does EDD apply?", "regulatory")
        assert out["assessment_source"] == "llm"
        assert out["answer"] == "EDD applies to PEPs [1]."
        assert out["citations"] == [1]
        assert out["grounded"] is True
        assert len(out["sources"]) == 2
        assert out["sources"][0]["reference"] == "AML-R100"

    def test_falls_back_to_extractive_when_llm_unavailable(self, patched, monkeypatch):
        monkeypatch.setattr(rq.llm, "complete_json", MagicMock(return_value=None))
        out = rq.answer_query("When does EDD apply?", "regulatory")
        assert out["assessment_source"] == "fallback"
        # extractive answer is the top-ranked chunk
        assert out["answer"].startswith("Enhanced due diligence applies to PEPs")
        assert out["citations"] == [1]

    def test_no_hits_returns_graceful_message(self, patched, monkeypatch):
        patched.search.return_value = []
        out = rq.answer_query("obscure query", "regulatory")
        assert out["assessment_source"] == "none"
        assert out["grounded"] is False
        assert out["sources"] == []


@pytest.mark.unit
class TestTravelIngest:
    def test_ingest_skips_when_already_populated(self, monkeypatch):
        store = MagicMock()
        store.document_count.return_value = 42
        corpus = rq.Corpus("travel", "Travel", store)
        monkeypatch.setattr(rq, "get_corpus", lambda key: corpus)
        assert rq.ingest_travel_corpus() == 42
        store.upsert.assert_not_called()

    def test_ingest_upserts_when_empty(self, monkeypatch):
        store = MagicMock()
        store.document_count.return_value = 0
        store.upsert.return_value = 3
        corpus = rq.Corpus("travel", "Travel", store)
        monkeypatch.setattr(rq, "get_corpus", lambda key: corpus)
        chunk = MagicMock()
        monkeypatch.setattr(rq, "_load_travel_chunks", lambda: [chunk, chunk, chunk])
        assert rq.ingest_travel_corpus() == 3
        store.upsert.assert_called_once()


@pytest.mark.unit
class TestCorpusRegistry:
    def test_unknown_corpus_raises(self):
        with pytest.raises(ValueError):
            rq.get_corpus("nonexistent")

    def test_available_corpora_lists_both(self):
        keys = {c["key"] for c in rq.available_corpora()}
        assert keys == {"regulatory", "travel"}
