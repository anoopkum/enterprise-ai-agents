"""
FastAPI application — REST entry point for the Loan Credit Intelligence Agent.
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from src.agents.orchestrator import LoanIntelligenceOrchestrator
from src.api.models import LoanApplication, LoanDecision
from src.api.middleware import RateLimitMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_orchestrator: LoanIntelligenceOrchestrator | None = None
_decisions_store: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator

    if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor()

    _orchestrator = LoanIntelligenceOrchestrator()
    logger.info("Loan Intelligence Orchestrator initialized")
    yield
    logger.info("Shutting down Loan Intelligence Orchestrator")


app = FastAPI(
    title="Loan Credit Intelligence Agent API",
    description="Multi-agent ML + LLM + RAG loan underwriting pipeline powered by Azure AI Foundry",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENVIRONMENT") != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://*.azurewebsites.net", "https://*.azurecontainerapps.io"],
    allow_methods=["POST", "GET"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)

FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
async def health():
    status_info = {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
    if _orchestrator:
        status_info["agents"] = _orchestrator.health_check()
    return status_info


@app.post("/applications", response_model=LoanDecision, status_code=status.HTTP_200_OK)
async def submit_application(application: LoanApplication, request: Request):
    """
    Submit a loan application for automated credit intelligence assessment.
    Returns a full decision with risk score, plain-English explanation, and compliance check.
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    logger.info("Processing application for: %s", application.applicant_name)

    result = _orchestrator.process_application(application.model_dump())

    # Cache for GET retrieval — in production, persist to Cosmos DB / Azure Table Storage
    application_id = result["application_id"]
    _decisions_store[application_id] = result

    compliance = result.get("compliance", {})
    explanation = result.get("explanation", {})

    response_payload = {
        "application_id": application_id,
        "final_decision": result.get("final_decision", "REFER"),
        "risk_score": result.get("risk_score", 0.5),
        "risk_band": result.get("risk_band", "MEDIUM"),
        "explanation": explanation,
        "compliance_flags": compliance.get("compliance_flags", []),
        "gdpr_disclosure_required": compliance.get("gdpr_article_22_disclosure_required", False),
        "fca_consumer_duty_met": compliance.get("fca_consumer_duty_met", True),
        "mlflow_run_id": result.get("mlflow_run_id"),
        "audit_run_id": result.get("audit_run_id"),
        "audited_at": result.get("audited_at", datetime.now(timezone.utc).isoformat()),
    }

    if result.get("final_decision") == "DECLINE":
        logger.warning(
            "DECLINE for application %s (risk_score=%.4f, risk_band=%s)",
            application_id,
            result.get("risk_score"),
            result.get("risk_band"),
        )

    return JSONResponse(content=response_payload)


@app.get("/applications/{application_id}")
async def get_decision(application_id: str):
    """Retrieve a previously computed decision by application ID."""
    if application_id not in _decisions_store:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    return JSONResponse(content=_decisions_store[application_id])


@app.exception_handler(ValueError)
async def validation_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
