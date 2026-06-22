"""
ETL Agent — ingests loan applications, validates fields, enriches with derived features,
and stores normalised records in ChromaDB for downstream agents.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import chromadb

from src.tools.data_ingestion import validate_and_normalise
from src.tools.feature_engineering import engineer_features

logger = logging.getLogger(__name__)


class ETLAgent:
    def __init__(self) -> None:
        self._chroma_client: chromadb.Client | None = None
        self._collection: chromadb.Collection | None = None

    @property
    def collection(self) -> chromadb.Collection:
        if self._collection is None:
            import os
            persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "/tmp/chroma/applications")
            self._chroma_client = chromadb.PersistentClient(path=persist_dir)
            self._collection = self._chroma_client.get_or_create_collection(
                name="loan_applications",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def process(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Validate, normalise, enrich, and persist a raw loan application.
        Returns an enriched context dict consumed by RiskScoringAgent.
        """
        raw_application = context.get("application", context)

        application_id = raw_application.get("application_id") or f"APP-{uuid.uuid4().hex[:8].upper()}"

        try:
            normalised = validate_and_normalise(raw_application)
        except ValueError as exc:
            logger.error("Validation failed for application %s: %s", application_id, exc)
            raise

        enriched = engineer_features(normalised)
        enriched["application_id"] = application_id
        enriched["etl_processed_at"] = datetime.now(timezone.utc).isoformat()

        self._store_to_chroma(application_id, enriched)

        logger.info(
            "ETL complete for %s — DTI: %.2f, utilisation: %.2f, payment_score: %d",
            application_id,
            enriched.get("dti_ratio", 0),
            enriched.get("credit_utilisation_rate", 0),
            enriched.get("payment_history_score", 0),
        )

        return {**context, "application": enriched, "application_id": application_id}

    def _store_to_chroma(self, application_id: str, enriched: dict) -> None:
        summary = (
            f"applicant={enriched.get('applicant_name', 'unknown')} "
            f"income={enriched.get('annual_income', 0)} "
            f"loan_amount={enriched.get('loan_amount', 0)} "
            f"credit_score={enriched.get('credit_score', 0)} "
            f"dti={enriched.get('dti_ratio', 0):.3f} "
            f"purpose={enriched.get('loan_purpose', 'unknown')}"
        )
        try:
            self.collection.upsert(
                ids=[application_id],
                documents=[summary],
                metadatas=[{"application_id": application_id, "stored_at": enriched["etl_processed_at"]}],
            )
        except Exception as exc:
            # Storage failure must not block the pipeline — decisions still proceed
            logger.warning("ChromaDB upsert failed for %s: %s", application_id, exc)
