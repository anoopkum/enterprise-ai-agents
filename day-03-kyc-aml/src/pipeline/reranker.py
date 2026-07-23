"""
Reranking stage — reorders the vector-store hits by true query relevance before
they reach the LLM, and trims to top_k_rerank.

Three modes (config.reranker):
  "azure"         → Azure AI Search already applied its semantic reranker in the
                    search() call, so hits arrive ordered; we just trim.
  "cross_encoder" → local cross-encoder (bge / ms-marco MiniLM) re-scores pairs.
  "none"/other    → lexical token-overlap fallback (no model needed).

The cross-encoder path is the pluggable alternative to Azure's reranker, so the
pipeline gets high-quality reranking even with no cloud account.
"""
import logging

from src.config import config

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self) -> None:
        self.mode = config.reranker
        self._model = None

    def _cross_encoder(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(config.cross_encoder_model)
        return self._model

    def rerank(self, query: str, hits: list[dict], top_k: int | None = None) -> list[dict]:
        top_k = top_k or config.top_k_rerank
        if not hits:
            return []

        if self.mode == "azure":
            ordered = hits  # already reranked server-side
        elif self.mode == "cross_encoder":
            ordered = self._rerank_cross_encoder(query, hits)
        else:
            ordered = self._rerank_lexical(query, hits)

        return ordered[:top_k]

    def _rerank_cross_encoder(self, query: str, hits: list[dict]) -> list[dict]:
        try:
            model = self._cross_encoder()
            scores = model.predict([(query, h["text"]) for h in hits])
            for h, s in zip(hits, scores):
                h["rerank_score"] = float(s)
            return sorted(hits, key=lambda h: h["rerank_score"], reverse=True)
        except Exception as exc:
            logger.warning("Cross-encoder rerank failed (%s) — using lexical fallback", exc)
            return self._rerank_lexical(query, hits)

    @staticmethod
    def _rerank_lexical(query: str, hits: list[dict]) -> list[dict]:
        q_tokens = set(query.lower().split())
        for h in hits:
            h_tokens = set(h["text"].lower().split())
            overlap = len(q_tokens & h_tokens)
            # blend lexical overlap with the retriever's own score as a tiebreaker
            h["rerank_score"] = overlap + 0.01 * float(h.get("score", 0.0) or 0.0)
        return sorted(hits, key=lambda h: h["rerank_score"], reverse=True)


reranker = Reranker()
