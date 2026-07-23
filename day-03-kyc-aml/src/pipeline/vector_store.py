"""
Vector store abstraction.
  Production : Azure AI Search — hybrid (BM25 + vector) + semantic reranker.
  Fallback   : ChromaDB (local, cosine) when AZURE_SEARCH_ENDPOINT is unset.

Both expose the same upsert()/search() interface returning a list of hit dicts:
  {chunk_id, text, score, metadata}
"""
import logging

from src.config import config
from src.ingestion.models import Chunk
from src.pipeline.embeddings import embedder

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self) -> None:
        self.backend = "azure_search" if config.use_azure_search else "chromadb"
        self._client = None
        self._collection = None
        logger.info("Vector store backend: %s", self.backend)

    # ─── Azure AI Search ───
    def _search_client(self):
        if self._client is None:
            from azure.search.documents import SearchClient
            from azure.core.credentials import AzureKeyCredential
            from azure.identity import DefaultAzureCredential

            credential = (
                AzureKeyCredential(config.search_key)
                if config.search_key else DefaultAzureCredential()
            )
            self._client = SearchClient(
                endpoint=config.search_endpoint,
                index_name=config.search_index,
                credential=credential,
            )
        return self._client

    # ─── ChromaDB ───
    def _chroma_collection(self):
        if self._collection is None:
            import chromadb
            client = chromadb.PersistentClient(path=config.chroma_persist_dir)
            self._collection = client.get_or_create_collection(
                name="kyc_regulatory_kb", metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        vectors = embedder.embed([c.text for c in chunks])
        if self.backend == "azure_search":
            return self._upsert_azure(chunks, vectors)
        return self._upsert_chroma(chunks, vectors)

    def _upsert_azure(self, chunks, vectors) -> int:
        docs = []
        for c, v in zip(chunks, vectors):
            docs.append({
                "chunk_id": c.chunk_id,
                "text": c.text,
                "doc_type": c.doc_type,
                "source_format": c.source_format,
                "reference": str(c.metadata.get("reference", "")),
                "framework": str(c.metadata.get("framework", "")),
                "confidence": float(c.confidence),
                "vector": v,
            })
        self._search_client().upload_documents(documents=docs)
        logger.info("Uploaded %d docs to Azure AI Search", len(docs))
        return len(docs)

    def _upsert_chroma(self, chunks, vectors) -> int:
        col = self._chroma_collection()
        col.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=vectors,
            metadatas=[{
                "doc_type": c.doc_type,
                "source_format": c.source_format,
                "reference": str(c.metadata.get("reference", "")),
                "framework": str(c.metadata.get("framework", "")),
                "confidence": float(c.confidence),
            } for c in chunks],
        )
        logger.info("Upserted %d docs to ChromaDB", len(chunks))
        return len(chunks)

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        top_k = top_k or config.top_k_retrieve
        if self.backend == "azure_search":
            return self._search_azure(query, top_k)
        return self._search_chroma(query, top_k)

    def _search_azure(self, query: str, top_k: int) -> list[dict]:
        from azure.search.documents.models import VectorizedQuery

        vector = embedder.embed([query])[0]
        vq = VectorizedQuery(vector=vector, k_nearest_neighbors=top_k, fields="vector")
        # Hybrid: text query + vector query; semantic reranker if configured.
        kwargs = dict(search_text=query, vector_queries=[vq], top=top_k)
        if config.reranker == "azure":
            kwargs.update(query_type="semantic", semantic_configuration_name="kyc-semantic")
        results = self._search_client().search(**kwargs)
        hits = []
        for r in results:
            hits.append({
                "chunk_id": r.get("chunk_id"),
                "text": r.get("text", ""),
                "score": r.get("@search.reranker_score") or r.get("@search.score", 0.0),
                "metadata": {k: r.get(k) for k in ("doc_type", "reference", "framework", "confidence")},
            })
        return hits

    def _search_chroma(self, query: str, top_k: int) -> list[dict]:
        col = self._chroma_collection()
        count = col.count()
        if count == 0:
            return []
        qv = embedder.embed([query])[0]
        res = col.query(
            query_embeddings=[qv],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for doc, meta, dist in zip(
            res.get("documents", [[]])[0],
            res.get("metadatas", [[]])[0],
            res.get("distances", [[]])[0],
        ):
            hits.append({
                "chunk_id": None,
                "text": doc,
                "score": round(1 - dist, 4),
                "metadata": meta,
            })
        return hits


vector_store = VectorStore()
