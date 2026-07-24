"""
Evaluation harness — two RAGAS-style scores over the benchmark data.

1) Decision accuracy: run the pipeline on sampled customers and compare the
   pipeline's APPROVE/EDD/REJECT to kyc_cases.ExpectedDecision.

2) Hallucination-detection quality: replay benchmark_dataset.csv (which pairs a
   GeneratedAnswer with a ground-truth Hallucinated flag) through the detector and
   score precision / recall / F1 — does our guardrail catch the planted
   hallucinations without over-flagging the good answers?

Both sample-cap by default so eval runs in seconds; raise EVAL_* to scale up.
"""
import csv
import logging
import os

from src.config import config
from src.guardrails.hallucination import hallucination_detector, SUPPORTED

logger = logging.getLogger(__name__)

EVAL_DECISION_N = int(os.environ.get("EVAL_DECISION_N", "50"))
EVAL_HALLU_N = int(os.environ.get("EVAL_HALLU_N", "200"))

# Map the dataset's expected decisions onto our three-way verdict.
_DECISION_ALIASES = {
    "APPROVE": "APPROVE", "APPROVED": "APPROVE", "ACCEPT": "APPROVE",
    "REJECT": "REJECT", "REJECTED": "REJECT", "DECLINE": "REJECT",
    "EDD": "EDD", "REVIEW": "EDD", "MANUAL_REVIEW": "EDD",
    "ENHANCED_DUE_DILIGENCE": "EDD", "REFER": "EDD",
}


def _norm_decision(value: str) -> str:
    return _DECISION_ALIASES.get(str(value).strip().upper().replace(" ", "_"), "EDD")


def _truthy(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def eval_decisions(data_dir: str | None = None, n: int | None = None) -> dict:
    from src.agents.orchestrator import orchestrator

    data_dir = data_dir or config.data_dir
    n = n or EVAL_DECISION_N
    path = os.path.join(data_dir, "kyc_cases.csv")
    if not os.path.exists(path):
        return {"error": f"missing {path}"}

    total = correct = 0
    confusion: dict[str, int] = {}
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if total >= n:
                break
            cid = row.get("CustomerID", "").strip()
            expected = _norm_decision(row.get("ExpectedDecision", ""))
            if not cid:
                continue
            try:
                result = orchestrator.run(customer_id=cid)
            except Exception as exc:
                logger.warning("Eval run failed for %s: %s", cid, exc)
                continue
            predicted = result.get("decision", {}).get("decision", "EDD")
            total += 1
            correct += int(predicted == expected)
            key = f"{expected}->{predicted}"
            confusion[key] = confusion.get(key, 0) + 1

    return {
        "metric": "decision_accuracy",
        "n": total,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "confusion": confusion,
    }


def eval_hallucination(data_dir: str | None = None, n: int | None = None) -> dict:
    data_dir = data_dir or config.data_dir
    n = n or EVAL_HALLU_N
    path = os.path.join(data_dir, "benchmark_dataset.csv")
    if not os.path.exists(path):
        return {"error": f"missing {path}"}

    tp = fp = tn = fn = 0
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if tp + fp + tn + fn >= n:
                break
            gen = row.get("GeneratedAnswer", "")
            truth = row.get("GroundTruthAnswer", "")
            is_hallucinated = _truthy(row.get("Hallucinated", ""))
            # Treat the ground-truth answer as the "retrieved evidence" the
            # generated answer must be grounded in.
            label, _ = hallucination_detector._entails(truth, gen)
            predicted_hallucination = label != SUPPORTED

            if predicted_hallucination and is_hallucinated:
                tp += 1
            elif predicted_hallucination and not is_hallucinated:
                fp += 1
            elif not predicted_hallucination and not is_hallucinated:
                tn += 1
            else:
                fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    total = tp + fp + tn + fn
    return {
        "metric": "hallucination_detection",
        "n": total,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round((tp + tn) / total, 4) if total else 0.0,
        "counts": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
    }


def run_all(data_dir: str | None = None) -> dict:
    return {
        "decisions": eval_decisions(data_dir),
        "hallucination": eval_hallucination(data_dir),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.WARNING)
    print(json.dumps(run_all(), indent=2))
