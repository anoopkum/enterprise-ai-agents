"""
Hallucination detector — grounds each AML finding against the retrieved context.

For every finding the AML agent produced, we check whether the cited claim is
actually supported by the text of the source it cites. This mirrors the dataset's
labelling scheme (Supported / Contradicted / PartiallySupported) from
hallucination_labels.csv & nli_dataset.csv.

Two backends:
  Production : cross-encoder NLI model (entailment / contradiction / neutral).
  Fallback   : lexical entailment — token overlap between claim and evidence.

A finding whose claim is not supported by its cited source is flagged as a
potential hallucination and downgraded before it can influence the decision.
"""
import logging

from src.config import config

logger = logging.getLogger(__name__)

SUPPORTED = "Supported"
CONTRADICTED = "Contradicted"
PARTIAL = "PartiallySupported"


class HallucinationDetector:
    def __init__(self) -> None:
        self._model = None
        self.threshold = config.nli_threshold

    def _nli_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            # NLI cross-encoder: outputs [contradiction, entailment, neutral] logits.
            self._model = CrossEncoder("cross-encoder/nli-deberta-v3-base")
        return self._model

    def check_findings(self, findings: list[dict], context: list[dict]) -> dict:
        """Label each finding against its cited context item; return a report."""
        by_id = {str(c.get("id")): c.get("text", "") for c in context}
        joined = " ".join(c.get("text", "") for c in context)

        checked = []
        flagged = 0
        for f in findings:
            claim = f.get("finding", "")
            citation = str(f.get("citation", ""))
            evidence = by_id.get(citation, joined)  # fall back to whole context
            label, score = self._entails(evidence, claim)
            is_hallucination = label == CONTRADICTED or (
                label == PARTIAL and score < self.threshold
            )
            if is_hallucination:
                flagged += 1
            checked.append({
                **f,
                "grounding_label": label,
                "grounding_score": round(score, 3),
                "hallucination": is_hallucination,
            })

        return {
            "findings": checked,
            "flagged_count": flagged,
            "total": len(findings),
            "any_hallucination": flagged > 0,
        }

    def _entails(self, premise: str, hypothesis: str) -> tuple[str, float]:
        if not hypothesis.strip():
            return SUPPORTED, 1.0
        if config.reranker == "cross_encoder" or self._model is not None:
            try:
                return self._entails_nli(premise, hypothesis)
            except Exception as exc:
                logger.warning("NLI model failed (%s) — lexical fallback", exc)
        return self._entails_lexical(premise, hypothesis)

    def _entails_nli(self, premise: str, hypothesis: str) -> tuple[str, float]:
        import numpy as np
        scores = self._nli_model().predict([(premise, hypothesis)])[0]
        labels = ["contradiction", "entailment", "neutral"]
        probs = np.exp(scores) / np.exp(scores).sum()
        idx = int(probs.argmax())
        conf = float(probs[idx])
        if labels[idx] == "entailment":
            return SUPPORTED, conf
        if labels[idx] == "contradiction":
            return CONTRADICTED, conf
        return PARTIAL, conf

    @staticmethod
    def _entails_lexical(premise: str, hypothesis: str) -> tuple[str, float]:
        p_tokens = set(premise.lower().split())
        h_tokens = set(hypothesis.lower().split())
        if not h_tokens:
            return SUPPORTED, 1.0
        overlap = len(p_tokens & h_tokens) / len(h_tokens)
        if overlap >= 0.6:
            return SUPPORTED, overlap
        if overlap >= 0.3:
            return PARTIAL, overlap
        return CONTRADICTED, 1.0 - overlap


hallucination_detector = HallucinationDetector()
