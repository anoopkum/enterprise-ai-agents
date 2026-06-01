"""
FastAPI application — REST entry point for the Fraud Detection Agent.
Exposes POST /analyze endpoint consumed by Azure Function / Event Hub trigger.
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from azure.monitor.opentelemetry import configure_azure_monitor

from src.agent import FraudDetectionAgent
from src.api.models import TransactionEvent, FraudDecision
from src.api.middleware import RateLimitMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_agent: FraudDetectionAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        configure_azure_monitor()
    _agent = FraudDetectionAgent()
    logger.info("Fraud Detection Agent initialized")
    yield
    logger.info("Shutting down Fraud Detection Agent")


app = FastAPI(
    title="Fraud Detection Agent API",
    description="Real-time transaction fraud analysis powered by Azure AI Foundry",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENVIRONMENT") != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://*.azurewebsites.net"],
    allow_methods=["POST", "GET"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/analyze", response_model=FraudDecision, status_code=status.HTTP_200_OK)
async def analyze_transaction(event: TransactionEvent, request: Request):
    """
    Analyze a transaction for fraud risk.
    Returns a fraud decision with score, risk level, and reasoning.
    """
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    logger.info("Analyzing transaction: %s", event.transaction_id)

    decision = _agent.analyze_transaction(event.model_dump())

    if decision.get("decision") == "BLOCK":
        logger.warning(
            "BLOCK decision for transaction %s (score: %s)",
            event.transaction_id,
            decision.get("fraud_score"),
        )

    return JSONResponse(content=decision)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "transaction_id": None},
    )
