"""
Unit tests for the startup seed guard. With min_replicas=0 the container cold-starts
on every wake and re-runs _bootstrap_knowledge(); it must skip the costly re-embed
when the vector store is already populated, and seed when it's empty.
"""
from unittest.mock import MagicMock

import pytest

import src.api.main as main
import src.pipeline.vector_store as vs_mod
import src.pipeline.kb_loader as kb_mod
import src.graph.builder as gb_mod


@pytest.fixture
def patched(monkeypatch):
    vector_store = MagicMock()
    load_chunks = MagicMock(return_value=[])
    build_graph = MagicMock(return_value={"nodes": 0})
    monkeypatch.setattr(vs_mod, "vector_store", vector_store)
    monkeypatch.setattr(kb_mod, "load_regulatory_chunks", load_chunks)
    monkeypatch.setattr(gb_mod, "build_graph", build_graph)
    return vector_store, load_chunks


@pytest.mark.unit
class TestSeedGuard:
    def test_skips_seeding_when_already_populated(self, patched):
        vector_store, load_chunks = patched
        vector_store.document_count.return_value = 500

        main._bootstrap_knowledge()

        load_chunks.assert_not_called()
        vector_store.upsert.assert_not_called()

    def test_seeds_when_store_empty(self, patched):
        vector_store, load_chunks = patched
        vector_store.document_count.return_value = 0
        chunk = MagicMock()
        load_chunks.return_value = [chunk]

        main._bootstrap_knowledge()

        load_chunks.assert_called_once()
        vector_store.upsert.assert_called_once_with([chunk])

    def test_no_upsert_when_no_kb_found(self, patched):
        vector_store, load_chunks = patched
        vector_store.document_count.return_value = 0
        load_chunks.return_value = []

        main._bootstrap_knowledge()

        vector_store.upsert.assert_not_called()
