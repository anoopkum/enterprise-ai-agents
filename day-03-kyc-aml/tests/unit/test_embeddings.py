"""
Unit tests for the embedder's batching. Seeding the KB embeds thousands of chunks
in one embed() call, which must be split into batches Azure OpenAI will accept
(single-request input cap). The local fallback path needs no Azure and lets us
assert dims/count deterministically.
"""
from unittest.mock import MagicMock

import pytest

from src.pipeline.embeddings import Embedder, EMBED_BATCH, LOCAL_DIM


@pytest.mark.unit
class TestLocalEmbedding:
    def test_empty_input_returns_empty(self):
        assert Embedder().embed([]) == []

    def test_local_fallback_shape(self):
        emb = Embedder()
        emb._use_azure = False
        vecs = emb.embed(["a rule about pep", "another guideline"])
        assert len(vecs) == 2
        assert all(len(v) == LOCAL_DIM for v in vecs)

    def test_local_is_deterministic(self):
        emb = Embedder()
        emb._use_azure = False
        assert emb.embed(["same text"]) == emb.embed(["same text"])


@pytest.mark.unit
class TestAzureBatching:
    def test_embed_batches_large_input(self):
        """A 600-item embed must issue ceil(600/256)=3 Azure calls, in order."""
        emb = Embedder()
        emb._use_azure = True

        def fake_create(model, input):
            # Echo one embedding per input item so we can verify ordering/count.
            resp = MagicMock()
            resp.data = [MagicMock(embedding=[float(len(t))]) for t in input]
            return resp

        client = MagicMock()
        client.embeddings.create.side_effect = fake_create
        emb._client = client
        emb._azure_client = lambda: client

        texts = [f"t{i}" for i in range(600)]
        out = emb.embed(texts)

        assert len(out) == 600
        assert client.embeddings.create.call_count == 3
        # Every call stayed within the batch cap.
        for call in client.embeddings.create.call_args_list:
            assert len(call.kwargs["input"]) <= EMBED_BATCH

    def test_azure_failure_falls_back_to_local(self):
        emb = Embedder()
        emb._use_azure = True
        client = MagicMock()
        client.embeddings.create.side_effect = RuntimeError("429 rate limit")
        emb._azure_client = lambda: client

        out = emb.embed(["x", "y"])
        assert len(out) == 2
        assert all(len(v) == LOCAL_DIM for v in out)  # switched to local
        assert emb._use_azure is False
