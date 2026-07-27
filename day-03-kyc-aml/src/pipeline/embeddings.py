"""
Embedding generation. Azure OpenAI text-embedding-3-large in production;
a deterministic local hash-embedding when no endpoint is configured so the
pipeline (and its tests) run offline. The local vectors are NOT semantically
meaningful — they exist only to keep the vector store operational for dev.
"""
import hashlib
import logging

from src.config import config

logger = logging.getLogger(__name__)

LOCAL_DIM = 384


class Embedder:
    def __init__(self) -> None:
        self._client = None
        self._use_azure = config.use_azure_openai

    def _azure_client(self):
        if self._client is None:
            from openai import AzureOpenAI
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            )
            self._client = AzureOpenAI(
                azure_endpoint=config.azure_openai_endpoint,
                azure_ad_token_provider=token_provider,
                api_version="2024-10-21",
            )
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._use_azure:
            try:
                resp = self._azure_client().embeddings.create(
                    model=config.embed_deployment, input=texts
                )
                return [d.embedding for d in resp.data]
            except Exception as exc:
                logger.warning("Azure embedding failed (%s) — using local fallback", exc)
                self._use_azure = False
        return [self._local_embed(t) for t in texts]

    @staticmethod
    def _local_embed(text: str) -> list[float]:
        """Deterministic pseudo-embedding: hash tokens into a fixed-dim bag vector."""
        vec = [0.0] * LOCAL_DIM
        for token in text.lower().split():
            # Non-cryptographic: MD5 only buckets tokens into a fixed-dim vector.
            h = int(hashlib.md5(token.encode(), usedforsecurity=False).hexdigest(), 16)
            vec[h % LOCAL_DIM] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]


embedder = Embedder()
