"""
Standalone pipeline runner — useful for batch processing and CLI invocation.
"""
import json
import logging
import sys

logger = logging.getLogger(__name__)


def run_pipeline(application_path: str) -> dict:
    """Load a JSON application file and run it through the full pipeline."""
    from src.agents.orchestrator import LoanIntelligenceOrchestrator

    with open(application_path) as f:
        application = json.load(f)

    orchestrator = LoanIntelligenceOrchestrator()
    result = orchestrator.process_application(application)
    return result


def run_batch(applications_path: str) -> list[dict]:
    """Process all applications in a JSON array file."""
    from src.agents.orchestrator import LoanIntelligenceOrchestrator

    with open(applications_path) as f:
        applications = json.load(f)

    orchestrator = LoanIntelligenceOrchestrator()
    results = []
    for i, app in enumerate(applications):
        try:
            result = orchestrator.process_application(app)
            results.append(result)
            logger.info(
                "[%d/%d] %s → %s (score=%.4f)",
                i + 1, len(applications),
                result.get("application_id"),
                result.get("final_decision"),
                result.get("risk_score", 0),
            )
        except Exception as exc:
            logger.error("[%d/%d] Failed to process application %s: %s", i + 1, len(applications), app.get("application_id"), exc)
            results.append({"application_id": app.get("application_id"), "error": str(exc)})

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python -m src.pipeline.loan_pipeline <application.json|applications_array.json>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path) as f:
        data = json.load(f)

    if isinstance(data, list):
        results = run_batch(path)
        print(json.dumps(results, indent=2))
    else:
        result = run_pipeline(path)
        print(json.dumps(result, indent=2))
