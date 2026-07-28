"""
FastAPI application — REST entry point for the KYC/AML Compliance Agent.

Startup (lifespan) seeds the regulatory KB into the vector store and builds the
knowledge graph, so /screen is ready to serve GraphRAG-backed decisions. All of it
degrades gracefully to local ChromaDB + NetworkX when no Azure/Neo4j is configured.
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import config
from src.api.models import ScreenRequest, KYCDecision
from src.api.middleware import RateLimitMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_orchestrator = None
_decisions_store: dict[str, dict] = {}


def _bootstrap_knowledge() -> None:
    """Seed the vector store + graph once at startup (idempotent-ish for a demo)."""
    from src.pipeline.kb_loader import load_regulatory_chunks
    from src.pipeline.vector_store import vector_store
    from src.graph.builder import build_graph

    try:
        chunks = load_regulatory_chunks()
        if chunks:
            vector_store.upsert(chunks)
            logger.info("Seeded %d regulatory chunks into %s", len(chunks), vector_store.backend)
    except Exception as exc:
        logger.warning("KB seeding skipped: %s", exc)

    try:
        stats = build_graph()
        logger.info("Knowledge graph ready: %s", stats)
    except Exception as exc:
        logger.warning("Graph build skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator
    if _orchestrator is None:
        if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
            try:
                from azure.monitor.opentelemetry import configure_azure_monitor
                configure_azure_monitor()
            except Exception as exc:
                logger.warning("App Insights not configured: %s", exc)
        if os.environ.get("SEED_ON_STARTUP", "true").lower() == "true":
            _bootstrap_knowledge()
        from src.agents.orchestrator import KYCOrchestrator
        _orchestrator = KYCOrchestrator()
        logger.info("KYC Orchestrator initialized")
    yield
    logger.info("Shutting down KYC Orchestrator")


app = FastAPI(
    title="KYC/AML Compliance Agent API",
    description="Multi-format RAG + knowledge-graph KYC/AML pipeline on Azure AI Foundry (GPT-4o)",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if config.environment != "prod" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://*.azurecontainerapps.io", "https://*.azurewebsites.net"],
    allow_methods=["POST", "GET"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)


@app.get("/health")
async def health():
    # Liveness: always 200 while the process is up. Optional backends (e.g. an
    # idle Neo4j Aura instance) surface as status="degraded" in the body rather
    # than failing the probe, so a paused dependency can't wedge the deploy gate.
    info: dict[str, Any] = {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
    if _orchestrator:
        components = _orchestrator.health_check()
        info["components"] = components
        if any(isinstance(v, dict) and v.get("status") == "unavailable" for v in components.values()):
            info["status"] = "degraded"
    return info


@app.post("/screen", response_model=KYCDecision, status_code=status.HTTP_200_OK)
async def screen_customer(req: ScreenRequest, request: Request):
    """Run the full KYC/AML pipeline for a customer and return the disposition."""
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    if not req.customer_id and not req.customer:
        raise HTTPException(status_code=422, detail="Provide customer_id or customer")

    result = _orchestrator.run(customer_id=req.customer_id, customer=req.customer)
    decision = result.get("decision", {})
    hallu = result.get("hallucination_report", {})
    aml = result.get("aml", {})

    payload = {
        "customer_id": result.get("customer_id"),
        "decision": decision.get("decision", "EDD"),
        "risk_level": decision.get("risk_level", "UNKNOWN"),
        "risk_score": decision.get("risk_score", 0.0),
        "reasons": decision.get("reasons", []),
        "identity_confidence": decision.get("identity_confidence", 0.0),
        "screening_verdict": decision.get("screening_verdict", "CLEAR"),
        "citations": decision.get("citations", []),
        "requires_human_review": decision.get("requires_human_review", True),
        "unsafe_to_auto_action": decision.get("unsafe_to_auto_action", True),
        "guardrail_violations": decision.get("guardrail_violations", []),
        "hallucination_flagged": hallu.get("flagged_count", 0),
        "sar": decision.get("sar"),
        "assessment_source": aml.get("assessment_source", "fallback"),
    }
    if payload["customer_id"]:
        _decisions_store[payload["customer_id"]] = payload
    if payload["decision"] == "REJECT":
        logger.warning("REJECT for %s (risk=%.2f)", payload["customer_id"], payload["risk_score"])
    return JSONResponse(content=payload)


@app.get("/decisions/{customer_id}")
async def get_decision(customer_id: str):
    if customer_id not in _decisions_store:
        raise HTTPException(status_code=404, detail=f"No decision cached for {customer_id}")
    return JSONResponse(content=_decisions_store[customer_id])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    if config.environment != "prod":
        import traceback
        return JSONResponse(status_code=500, content={"detail": str(exc), "traceback": traceback.format_exc()})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
