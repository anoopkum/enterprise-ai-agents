# Day 02 — Loan Credit Intelligence Agent

> **30-Day Enterprise AI Agent Series** | Day 02 of 30 | Banking & Financial Services

A production-grade **multi-agent loan underwriting pipeline** combining scikit-learn ML, LLM-powered explainability, RAG-based compliance checking, and full MLflow audit trails — deployed on Azure AI Foundry.

---

## Architecture

```
POST /applications
        │
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     LangChain LCEL Orchestrator                       │
│                                                                       │
│  ┌──────────┐   ┌─────────────┐   ┌──────────────┐   ┌───────────┐  │
│  │   ETL    │──▶│Risk Scoring │──▶│Explainability│──▶│Compliance │  │
│  │  Agent   │   │   Agent     │   │    Agent     │   │  Agent    │  │
│  │          │   │             │   │              │   │           │  │
│  │Validate  │   │RandomForest │   │GPT-4o via    │   │RAG over   │  │
│  │Normalise │   │+ SHAP       │   │Azure AI      │   │FCA/GDPR/  │  │
│  │Engineer  │   │+ MLflow     │   │Foundry       │   │Basel III  │  │
│  │→ChromaDB │   │             │   │              │   │→ChromaDB  │  │
│  └──────────┘   └─────────────┘   └──────────────┘   └───────────┘  │
│                                                               │       │
│                                                               ▼       │
│                                                     ┌──────────────┐  │
│                                                     │ Audit Logger │  │
│                                                     │  (MLflow)    │  │
│                                                     └──────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
        │
        ▼
  LoanDecision JSON
  (risk_score, explanation, compliance_flags, audit_run_id)
```

**Data flow:** Each agent receives a context dict and returns an enriched version — no shared mutable state. The LCEL `|` operator composes them into a single runnable chain.

---

## JD Coverage Table

| Skill / Framework | Where Demonstrated | Why It Matters |
|---|---|---|
| **Azure AI Foundry Agents SDK** | `explainability_agent.py` — `AgentsClient`, `create_and_process`, tool execution | Core platform for enterprise AI workloads |
| **LangChain LCEL** | `orchestrator.py` — `RunnableLambda` pipe chain | Modern agent orchestration pattern; replaces legacy chains |
| **scikit-learn (ML)** | `train_model.py` — RandomForestClassifier, StratifiedKFold, ROC-AUC | Demonstrates ML fundamentals beyond LLM prompting |
| **SHAP explainability** | `model_inference.py` — TreeExplainer + fallback | Regulatory XAI requirement (GDPR Art. 22, ICO guidance) |
| **MLflow** | `risk_scoring_agent.py`, `audit_logger.py` — params/metrics/artifacts | ML experiment tracking and model governance |
| **RAG / ChromaDB** | `compliance_agent.py` — vector store + similarity query | Retrieval-augmented generation for knowledge-grounded decisions |
| **FastAPI + Pydantic v2** | `src/api/` — request validation, response models, middleware | Production REST API with type safety |
| **Azure Bicep IaC** | `infra/` — Key Vault, OpenAI, AI Foundry, Container Apps, Monitor | End-to-end Azure deployment without ARM JSON |
| **Prompt Engineering** | `explainability_agent.py` — system prompt with structured output, GDPR clause | Demonstrates LLM instruction following in regulated context |
| **Regulatory compliance** | `compliance_agent.py`, `data/regulatory_kb.json` | FCA CONC 5.2, GDPR Art. 22, Basel III, Consumer Duty |
| **Multi-stage Docker** | `Dockerfile` — deps → final, non-root user | Container security best practices |
| **OpenTelemetry** | `src/api/main.py` — FastAPIInstrumentor, Azure Monitor | Distributed tracing for production observability |

---

## Dataset

**UCI ML Repository — Default of Credit Card Clients**
- URL: https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients
- Authors: Yeh & Lien (2009), Expert Systems with Applications
- 30,000 Taiwan credit card holders, 23 features, binary default label
- Our pipeline maps UCI fields (LIMIT_BAL, PAY_0–6, BILL_AMT1–6) to enriched loan application features

The `scripts/train_model.py` trains on either the real UCI CSV or auto-generated synthetic data matching the same schema and ~22% base default rate.

---

## File Structure

```
day-02-loan-underwriting/
├── src/
│   ├── agents/
│   │   ├── etl_agent.py              # Validate → enrich → ChromaDB
│   │   ├── risk_scoring_agent.py     # RandomForest + SHAP + MLflow
│   │   ├── explainability_agent.py   # GPT-4o via Azure AI Foundry
│   │   ├── compliance_agent.py       # RAG over regulatory KB
│   │   └── orchestrator.py          # LangChain LCEL chain
│   ├── tools/
│   │   ├── data_ingestion.py         # Field validation + normalisation
│   │   ├── feature_engineering.py    # DTI, utilisation, payment score
│   │   ├── model_inference.py        # Feature vector + SHAP values
│   │   ├── compliance_checker.py     # Rule applicability filtering
│   │   └── audit_logger.py          # MLflow audit trail
│   ├── api/
│   │   ├── main.py                   # FastAPI app, lifespan, routes
│   │   ├── models.py                 # Pydantic v2 schemas
│   │   └── middleware.py             # Sliding-window rate limiter
│   └── pipeline/
│       └── loan_pipeline.py          # Batch runner + CLI entry point
├── scripts/
│   ├── train_model.py                # Train RandomForest, save pkl + feature names
│   └── generate_sample_data.py       # 100 synthetic applications
├── data/
│   ├── sample_applications.json      # 10 hand-crafted realistic applications
│   └── regulatory_kb.json           # 10 FCA/GDPR/Basel III/ICO rule chunks
├── models/                           # .gitkeep — populated by train_model.py
├── tests/
│   ├── test_agents.py                # Unit tests (no external deps)
│   └── test_api.py                   # Integration tests (mocked orchestrator)
├── infra/
│   ├── main.bicep
│   └── modules/
│       ├── keyvault.bicep
│       ├── openai.bicep
│       ├── foundry.bicep
│       ├── containerapp.bicep
│       └── monitoring.bicep
├── .env.example
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt
```

---

## How to Run Locally

### 1. Prerequisites

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 2. Train the model

```bash
# Synthetic data (no download needed):
python scripts/train_model.py

# Real UCI data (download from https://archive.ics.uci.edu/dataset/350):
python scripts/train_model.py --data-path data/uci_credit.csv
```

This creates `models/credit_risk_model.pkl`, `models/feature_names.json`, and `models/feature_importances.json`.

### 3. Set environment variables

```bash
cp .env.example .env
# Edit .env — at minimum set AI_FOUNDRY_ENDPOINT for the explainability agent
```

### 4. Start the API

```bash
uvicorn src.api.main:app --reload --port 8000
```

### 5. Submit an application

```bash
curl -s -X POST http://localhost:8000/applications \
  -H "Content-Type: application/json" \
  -d @data/sample_applications.json | python3 -m json.tool
```

Or use the interactive docs at http://localhost:8000/docs

### 6. Run tests

```bash
pytest tests/ -m unit -v
pytest tests/ -m integration -v
```

### 7. Batch processing

```bash
python -m src.pipeline.loan_pipeline data/sample_applications.json
```

---

## Deploy to Azure

### Prerequisites
- Azure CLI logged in: `az login`
- Bicep installed: `az bicep install`

### Step 1 — Deploy infrastructure

```bash
az group create --name rg-loan-agent-dev --location uksouth

az deployment group create \
  --resource-group rg-loan-agent-dev \
  --template-file infra/main.bicep \
  --parameters environment=dev adminObjectId=$(az ad signed-in-user show --query id -o tsv)
```

### Step 2 — Build and push container

```bash
ACR_NAME="acrloanagentdev"

az acr create --resource-group rg-loan-agent-dev --name $ACR_NAME --sku Basic
az acr login --name $ACR_NAME

docker build -t $ACR_NAME.azurecr.io/loan-agent:latest .
docker push $ACR_NAME.azurecr.io/loan-agent:latest
```

### Step 3 — Configure secrets

```bash
az keyvault secret set \
  --vault-name kv-loan-agent-dev \
  --name ai-foundry-endpoint \
  --value "https://your-openai.openai.azure.com/"
```

---

## Interview Talking Points

### ETL Agent
- "I chose ChromaDB because the enriched application data feeds the compliance RAG query — same vector store, different collections, zero extra infrastructure."
- "Validation happens at the ETL layer, not inside ML inference — clean separation of concerns."

### Risk Scoring Agent
- "MLflow tracks every scoring run with the full feature vector and SHAP values. If a model is retrained, you can diff any past decision against the new model."
- "The model is loaded lazily on first call — avoids import-time failures when the pkl hasn't been trained yet in dev."

### Explainability Agent
- "GDPR Article 22 requires that automated credit decisions be explainable to the data subject. I pass SHAP values into the GPT-4o prompt so the LLM grounds its explanation in actual feature contributions, not generic reasoning."
- "The rule-based fallback ensures zero downtime if Azure AI Foundry is unreachable — the API always returns a decision."

### Compliance Agent
- "RAG over the regulatory KB lets us add new rules (e.g., when FCA updates CONC guidance) by appending JSON — no code changes."
- "The hard-coded flag checks (DTI > 55%, approved with score < 550) are safety nets for cases the vector search might miss."

### Orchestrator
- "LCEL's pipe operator makes the data flow self-documenting. Each agent is independently testable as a `RunnableLambda`."
- "Context is immutable from each agent's perspective — `{**context, 'new_key': value}` pattern prevents subtle state bugs."

### MLflow Audit Trail
- "Every decision creates two MLflow runs: one for scoring (with the model's PD estimate) and one for audit (with the full decision record). The audit run links back to the scoring run via `scoring_run_id` param — gives you a complete chain of custody."
