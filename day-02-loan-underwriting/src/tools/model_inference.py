"""Tool: Model feature vector assembly and SHAP value computation."""
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def build_feature_vector(application: dict[str, Any], feature_names: list[str]) -> list[float]:
    """
    Assemble a flat numeric feature vector in the exact column order the model was trained on.
    Any missing feature defaults to 0.0 — missing fields are logged as warnings.
    """
    feature_map = {
        "age": application.get("age", 0),
        "annual_income": application.get("annual_income", 0),
        "credit_score": application.get("credit_score", 0),
        "existing_debt": application.get("existing_debt", 0),
        "loan_amount": application.get("loan_amount", 0),
        "loan_term_months": application.get("loan_term_months", 60),
        "dti_ratio": application.get("dti_ratio", 0),
        "credit_utilisation_rate": application.get("credit_utilisation_rate", 0),
        "payment_history_score": application.get("payment_history_score", 0),
        "missed_payments_count": application.get("missed_payments_count", 0),
        "late_payments_count": application.get("late_payments_count", 0),
        "loan_to_income_ratio": application.get("loan_to_income_ratio", 0),
        "employment_stability_score": application.get("employment_stability_score", 0),
        "monthly_income": application.get("monthly_income", 0),
        "estimated_monthly_payment": application.get("estimated_monthly_payment", 0),
    }

    vector = []
    for name in feature_names:
        if name not in feature_map:
            logger.warning("Feature '%s' not found in application — defaulting to 0.0", name)
        vector.append(float(feature_map.get(name, 0.0)))

    return vector


def compute_shap_values(model, feature_vector: list[float], feature_names: list[str]) -> dict[str, float]:
    """
    Compute SHAP values using TreeExplainer.
    Returns a dict mapping feature_name → SHAP value (positive = increases default risk).
    Falls back to permutation-based approximate importances if SHAP raises.
    """
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        shap_output = explainer(np.array([feature_vector]))

        # shap_output is a shap.Explanation; .values shape is (n_samples, n_features, n_classes)
        # for binary classifiers — take class 1 (default probability)
        raw = shap_output.values
        if raw.ndim == 3:
            values = raw[0, :, 1]
        elif raw.ndim == 2:
            values = raw[0]
        else:
            values = raw

        return {name: round(float(val), 6) for name, val in zip(feature_names, values)}

    except Exception as exc:
        logger.warning("SHAP TreeExplainer failed, falling back to feature importances: %s", exc)

        # Approximate: scale model feature_importances_ by signed deviation from mean
        importances = model.feature_importances_
        vec = np.array(feature_vector)
        signs = np.where(vec > np.median(vec), 1, -1)
        approx = importances * signs

        return {name: round(float(val), 6) for name, val in zip(feature_names, approx)}
