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


# text-embedding-3-large emits 3072-dim vectors; the index vector field must match
# whatever the embedder actually produces (see upsert → ensure_index).
AZURE_EMBED_DIM = 3072
SEMANTIC_CONFIG = "kyc-semantic"
VECTOR_PROFILE = "kyc-hnsw"
UPLOAD_BATCH = 1000  # Azure AI Search hard cap: 1000 docs per upload_documents call


class VectorStore:
    def __init__(self, index_name: str | None = None,
                 collection_name: str = "kyc_regulatory_kb") -> None:
        # index_name / collection_name let a second corpus (e.g. the travel PDFs)
        # reuse this store against a different Azure index / Chroma collection.
        # Defaults reproduce the regulatory-KB behaviour every existing caller relies on.
        self.backend = "azure_search" if config.use_azure_search else "chromadb"
        self.index_name = index_name or config.search_index
        self.collection_name = collection_name
        self._client = None
        self._index_client = None
        self._index_ready = False
        self._collection = None
        logger.info("Vector store backend: %s (index=%s)", self.backend, self.index_name)

    def _credential(self):
        from azure.core.credentials import AzureKeyCredential
        from azure.identity import DefaultAzureCredential

        return (
            AzureKeyCredential(config.search_key)
            if config.search_key else DefaultAzureCredential()
        )

    # ─── Azure AI Search ───
    def _search_client(self):
        if self._client is None:
            from azure.search.documents import SearchClient

            self._client = SearchClient(
                endpoint=config.search_endpoint,
                index_name=self.index_name,
                credential=self._credential(),
            )
        return self._client

    def _search_index_client(self):
        if self._index_client is None:
            from azure.search.documents.indexes import SearchIndexClient

            self._index_client = SearchIndexClient(
                endpoint=config.search_endpoint, credential=self._credential()
            )
        return self._index_client

    def ensure_index(self, vector_dim: int = AZURE_EMBED_DIM) -> None:
        """Create the regulatory-KB index if it doesn't exist.

        Hybrid retrieval needs a schema Azure AI Search can't infer from uploads:
        a vector field of the right dimensionality + an HNSW profile, plus the
        `kyc-semantic` configuration the reranker path references. create_or_update
        is idempotent, so this is safe to call on every startup. Requires the app
        identity to hold *Search Service Contributor* (control-plane).
        """
        from azure.core.exceptions import ResourceExistsError
        from azure.search.documents.indexes.models import (
            SearchField, SearchFieldDataType, SearchIndex,
            SemanticConfiguration, SemanticField, SemanticPrioritizedFields,
            SemanticSearch, SimpleField, SearchableField,
            VectorSearch, VectorSearchProfile, HnswAlgorithmConfiguration,
        )

        fields = [
            SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="text", type=SearchFieldDataType.String),
            SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="source_format", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="reference", type=SearchFieldDataType.String),
            SimpleField(name="framework", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="confidence", type=SearchFieldDataType.Double, filterable=True),
            SearchField(
                name="vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=vector_dim,
                vector_search_profile_name=VECTOR_PROFILE,
            ),
        ]
        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="kyc-hnsw-algo")],
            profiles=[VectorSearchProfile(
                name=VECTOR_PROFILE, algorithm_configuration_name="kyc-hnsw-algo")],
        )
        semantic_search = SemanticSearch(configurations=[SemanticConfiguration(
            name=SEMANTIC_CONFIG,
            prioritized_fields=SemanticPrioritizedFields(
                content_fields=[SemanticField(field_name="text")],
                keywords_fields=[SemanticField(field_name="reference")],
            ),
        )])
        index = SearchIndex(
            name=self.index_name, fields=fields,
            vector_search=vector_search, semantic_search=semantic_search,
        )
        try:
            self._search_index_client().create_or_update_index(index)
            logger.info("Ensured Azure AI Search index '%s' (%d-dim vectors)",
                        self.index_name, vector_dim)
        except ResourceExistsError:
            logger.info("Azure AI Search index '%s' already exists", self.index_name)
        self._index_ready = True

    def document_count(self) -> int:
        """Docs already in the index (Azure) / collection (Chroma). -1 if unknown."""
        try:
            if self.backend == "azure_search":
                return self._search_client().get_document_count()
            return self._chroma_collection().count()
        except Exception as exc:
            logger.warning("Could not read document count: %s", exc)
            return -1

    # ─── ChromaDB ───
    def _chroma_collection(self):
        if self._collection is None:
            import chromadb
            client = chromadb.PersistentClient(path=config.chroma_persist_dir)
            self._collection = client.get_or_create_collection(
                name=self.collection_name, metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        vectors = embedder.embed([c.text for c in chunks])
        if self.backend == "azure_search":
            if not self._index_ready:
                # Match the index vector dim to what the embedder actually produced,
                # so a local-fallback embedding (LOCAL_DIM) still yields a usable index.
                self.ensure_index(len(vectors[0]) if vectors else AZURE_EMBED_DIM)
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
        # Azure AI Search caps a single upload at 1000 docs — batch to stay under it.
        client = self._search_client()
        for i in range(0, len(docs), UPLOAD_BATCH):
            client.upload_documents(documents=docs[i:i + UPLOAD_BATCH])
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
