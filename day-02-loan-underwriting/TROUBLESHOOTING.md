# Troubleshooting — Loan Credit Intelligence Agent

---

## Model not found: `FileNotFoundError: models/credit_risk_model.pkl`

**Cause:** The model has not been trained yet. The pkl is excluded from git (binary file).

**Fix:**
```bash
python scripts/train_model.py
```

This generates `models/credit_risk_model.pkl`, `models/feature_names.json`, and `models/feature_importances.json` in under 2 minutes using synthetic data.

---

## `AI_FOUNDRY_ENDPOINT` not set — explainability agent fails

**Cause:** The explainability agent requires the Azure OpenAI endpoint (not the AI Foundry Hub connection string).

**Fix:** The endpoint format is:
```
https://<your-resource-name>.openai.azure.com/
```
Not the Hub connection string format `<region>.api.azureml.ms;...`.

The agent uses `DefaultAzureCredential` — run `az login` locally. In CI/CD, assign the Container App's managed identity the **Cognitive Services OpenAI User** role on the Azure OpenAI resource.

The `_rule_based_fallback` method in `ExplainabilityAgent` ensures decisions still return even without Azure connectivity.

---

## SHAP TreeExplainer raises `ValueError: multiclass format is not supported`

**Cause:** SHAP's TreeExplainer for multi-output classifiers requires explicit output index selection.

**Fix:** Already handled in `model_inference.py` — when `shap_values` is a list, index `[1]` (class=default) is selected. If you swap to a different model type (GBM, XGBoost), verify the SHAP output shape and update accordingly.

---

## ChromaDB `sqlite3.OperationalError: no such table`

**Cause:** The ChromaDB persist directory was created with a different ChromaDB version and the schema is incompatible.

**Fix:**
```bash
rm -rf /tmp/chroma/applications
# Restart the app — collections will be recreated automatically
```

---

## MLflow `MlflowException: Run with UUID not found`

**Cause:** The MLflow tracking URI points to a remote server that's unreachable, or `mlruns/` directory was deleted mid-run.

**Fix:**
```bash
# Confirm local tracking works:
export MLFLOW_TRACKING_URI=mlruns
mlflow ui --port 5000
```

For Azure ML tracking URI, ensure the workspace exists and your identity has the **AzureML Data Scientist** role.

---

## `pytest` fails with `ModuleNotFoundError: No module named 'src'`

**Cause:** The tests must be run from the `day-02-loan-underwriting/` directory, not the repo root.

**Fix:**
```bash
cd day-02-loan-underwriting
pytest tests/ -m unit -v
```

Or add a `conftest.py` to insert the project root into `sys.path`:
```python
# conftest.py (already handled by pytest.ini testpaths)
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
```

---

## High memory usage during SHAP computation

**Cause:** `shap.TreeExplainer` builds a background dataset from all training trees — can use 1–2 GB for large forests.

**Fix:** Reduce `n_estimators` in `train_model.py` from 300 to 100 for development, or use the approximate SHAP fallback by setting `SHAP_DISABLED=true` in `.env` (add an env check to `model_inference.py`).

---

## Container App returns 503 on first request after cold start

**Cause:** The model is loaded lazily and ChromaDB collection is seeded on first access — cold start takes ~5-10 seconds.

**Fix:** The `HEALTHCHECK` in `Dockerfile` uses `--start-period=20s`. In Azure Container Apps, set `minReplicas=1` in production to avoid cold starts entirely (already set in `containerapp.bicep` when `isProduction=true`).

---

## `FCA Consumer Duty CRITICAL flag` triggered for an approval

**Cause:** The compliance agent flags approvals where `credit_score < 550` as a CRITICAL Consumer Duty concern.

**This is intentional.** The flag does not block the decision — it requires escalation to a senior underwriter. Review `compliance_agent.py` `_evaluate_flags()` to adjust the threshold if your institution's policy differs.
