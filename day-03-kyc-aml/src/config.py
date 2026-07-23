"""
Central configuration. Every Azure dependency is optional — absence triggers a
local fallback (ChromaDB, NetworkX, PyMuPDF) so the full pipeline runs with no
cloud account, mirroring the Day 02 progressive-fallback pattern.
"""
import os
import tempfile
from dataclasses import dataclass, field


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


@dataclass
class Config:
    data_dir: str = field(default_factory=lambda: _get("DATA_DIR", "data"))

    # Azure AI Foundry
    ai_foundry_endpoint: str = field(default_factory=lambda: _get("AI_FOUNDRY_ENDPOINT"))
    openai_deployment: str = field(default_factory=lambda: _get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1"))
    embed_deployment: str = field(default_factory=lambda: _get("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-large"))

    # Azure AI Search
    search_endpoint: str = field(default_factory=lambda: _get("AZURE_SEARCH_ENDPOINT"))
    search_index: str = field(default_factory=lambda: _get("AZURE_SEARCH_INDEX", "kyc-regulatory-kb"))
    search_key: str = field(default_factory=lambda: _get("AZURE_SEARCH_KEY"))

    # Document Intelligence
    doc_intel_endpoint: str = field(default_factory=lambda: _get("DOC_INTELLIGENCE_ENDPOINT"))
    doc_intel_key: str = field(default_factory=lambda: _get("DOC_INTELLIGENCE_KEY"))

    # Neo4j
    neo4j_uri: str = field(default_factory=lambda: _get("NEO4J_URI"))
    neo4j_user: str = field(default_factory=lambda: _get("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: _get("NEO4J_PASSWORD"))

    # Local fallbacks
    chroma_persist_dir: str = field(default_factory=lambda: _get("CHROMA_PERSIST_DIR", os.path.join(tempfile.gettempdir(), "chroma", "kyc")))

    # Retrieval
    top_k_retrieve: int = field(default_factory=lambda: int(_get("TOP_K_RETRIEVE", "10")))
    top_k_rerank: int = field(default_factory=lambda: int(_get("TOP_K_RERANK", "5")))
    reranker: str = field(default_factory=lambda: _get("RERANKER", "azure"))
    cross_encoder_model: str = field(default_factory=lambda: _get("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))

    # Guardrails
    nli_threshold: float = field(default_factory=lambda: float(_get("HALLUCINATION_NLI_THRESHOLD", "0.5")))
    enable_pii_redaction: bool = field(default_factory=lambda: _get("ENABLE_PII_REDACTION", "true") == "true")

    # Decision thresholds
    edd_threshold: float = field(default_factory=lambda: float(_get("EDD_RISK_THRESHOLD", "0.60")))
    reject_threshold: float = field(default_factory=lambda: float(_get("REJECT_RISK_THRESHOLD", "0.85")))

    environment: str = field(default_factory=lambda: _get("ENVIRONMENT", "dev"))

    # ─── Capability flags — drive fallback decisions across the pipeline ───
    @property
    def use_azure_search(self) -> bool:
        return bool(self.search_endpoint)

    @property
    def use_doc_intelligence(self) -> bool:
        return bool(self.doc_intel_endpoint)

    @property
    def use_neo4j(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_password)

    @property
    def use_azure_openai(self) -> bool:
        return bool(self.ai_foundry_endpoint)


config = Config()
