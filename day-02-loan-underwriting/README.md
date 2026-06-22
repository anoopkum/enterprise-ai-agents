# Day 02 — Loan Underwriting Copilot

> **30-Day Enterprise AI Agent Series** | Day 02 of 30 | Banking & Financial Services

A production-grade **multi-agent loan underwriting pipeline** combining scikit-learn ML, LLM-powered explainability, RAG-based compliance checking, and full MLflow audit trails — deployed on Azure via Terraform + GitHub Actions CI/CD.

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
│  │Normalise │   │+ SHAP       │   │Azure OpenAI  │   │FCA/GDPR/  │  │
│  │Engineer  │   │+ MLflow     │   │(rule-based   │   │Basel III  │  │
│  │→ChromaDB │   │             │   │fallback)     │   │→ChromaDB  │  │
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

## Tech Stack

| Layer | Technology |
|---|---|
| ML model | scikit-learn RandomForestClassifier, SHAP TreeExplainer |
| Orchestration | LangChain LCEL (`RunnableLambda` pipe chain) |
| LLM | Azure OpenAI GPT-4o (rule-based fallback when endpoint not set) |
| Vector store | ChromaDB — 2 collections: `loan_applications`, `regulatory_kb` |
| Experiment tracking | MLflow 3.x — SQLite backend locally, remote on Azure |
| API | FastAPI + Pydantic v2, OpenTelemetry tracing |
| Infrastructure | Terraform (AzureRM ~3.110) + remote backend (Azure Blob) |
| CI/CD | GitHub Actions — PR checks, infra deploy, ML/app deploy |
| Security scanning | Snyk (SCA + IaC + container), SonarCloud (SAST), Checkov |
| Container registry | Azure Container Registry (system-assigned MI, no stored creds) |
| Runtime | Azure Container Apps (system-assigned MI for KV + ACR access) |

---

## Azure Resources (dev)

All provisioned by Terraform in `rg-loan-underwriting-dev`:

| Resource | Name | Module |
|---|---|---|
| Resource Group | `rg-loan-underwriting-dev` | root |
| Key Vault | `kv-loan-underwriting-dev` | keyvault |
| Azure Container Registry | `acrloanunderwritingdev` | acr |
| Azure OpenAI | `oai-loan-underwriting-dev` + GPT-4o deployment | openai |
| AML Workspace | `aihub-lu-dev` | foundry |
| Container App Environment | `cae-loan-underwriting-dev` | containerapp |
| Container App | `ca-loan-underwriting-dev` | containerapp |
| Log Analytics Workspace | `appi-loan-underwriting-dev-workspace` | monitoring |
| Application Insights | `appi-loan-underwriting-dev` | monitoring |
| TF State Storage | `stloanunderwritingtf` / `rg-tfstate-loan` | bootstrap |

---

## File Structure

```
day-02-loan-underwriting/
├── src/
│   ├── agents/
│   │   ├── etl_agent.py              # Validate → enrich → ChromaDB
│   │   ├── risk_scoring_agent.py     # RandomForest + SHAP + MLflow
│   │   ├── explainability_agent.py   # GPT-4o / rule-based fallback
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
│   ├── generate_sample_data.py       # 100 synthetic applications
│   └── bootstrap_tf_backend.sh      # One-time: create Azure Blob TF state backend
├── data/
│   ├── sample_applications.json      # 10 hand-crafted realistic applications
│   └── regulatory_kb.json           # 10 FCA/GDPR/Basel III/ICO rule chunks
├── models/                           # .gitkeep — populated by train_model.py
├── tests/
│   ├── test_agents.py                # Unit tests (no external deps)
│   └── test_api.py                   # Integration tests (mocked orchestrator)
├── terraform/
│   ├── main.tf                       # Root: RG + 6 modules wired together
│   ├── locals.tf                     # prefix, is_production, tags
│   ├── variables.tf                  # environment, location, project_name, etc.
│   ├── outputs.tf                    # container_app_url, acr_login_server, etc.
│   ├── environments/
│   │   ├── dev.tfvars
│   │   └── prod.tfvars               # skeleton
│   └── modules/
│       ├── acr/                      # Azure Container Registry
│       ├── keyvault/                 # Key Vault (RBAC-enabled)
│       ├── openai/                   # Azure OpenAI + GPT-4o deployment
│       ├── foundry/                  # AML Workspace
│       ├── monitoring/               # Log Analytics + App Insights
│       └── containerapp/             # Container App Environment + App
├── .github/workflows/
│   ├── pr-checks.yml                 # pytest, tf plan, Snyk, SonarCloud, Checkov
│   ├── infra-deploy.yml              # bootstrap backend + terraform apply dev
│   └── ml-deploy.yml                 # train → build/push ACR → deploy
├── sonar-project.properties
├── .env.example
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt
```

---

## How to Run Locally

### 1. Prerequisites

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

> Python 3.11 required — MLflow 3.x and ChromaDB are incompatible with 3.14+

### 2. Train the model

```bash
MLFLOW_TRACKING_URI=sqlite:///mlruns/mlflow.db python scripts/train_model.py
```

Creates `models/credit_risk_model.pkl`, `models/feature_names.json`, ROC-AUC ~0.95.

### 3. Set environment variables

```bash
cp .env.example .env
# AI_FOUNDRY_ENDPOINT is optional — explainability falls back to rule-based if unset
```

### 4. Run the pipeline

```bash
MLFLOW_TRACKING_URI=sqlite:///mlruns/mlflow.db \
  python -m src.pipeline.loan_pipeline data/sample_applications.json
```

### 5. Start the API

```bash
MLFLOW_TRACKING_URI=sqlite:///mlruns/mlflow.db uvicorn src.api.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

### 6. Run tests

```bash
pytest tests/ -v --tb=short
```

### 7. MLflow UI

```bash
mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db --port 5001
```

---

## Deploy to Azure

### Prerequisites

- GitHub secrets configured: `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_ADMIN_OBJECT_ID`, `SNYK_TOKEN`, `SONAR_TOKEN`, `SONAR_HOST`
- SP needs: `Contributor` + `User Access Administrator` on the dev resource group, `Key Vault Secrets Officer` on `kv-loan-underwriting-dev`

### Step 1 — Trigger infra deploy

```bash
gh workflow run infra-deploy.yml --repo anoopkum/enterprise-ai-agents -f environment=dev
```

Or push any change under `day-02-loan-underwriting/terraform/**` to main.

### Step 2 — Add ACR secret (after first apply)

The infra-deploy job summary prints the exact command:
```bash
gh secret set ACR_LOGIN_SERVER --body "<acr_login_server>" --repo anoopkum/enterprise-ai-agents
```

### Step 3 — Deploy app

```bash
gh workflow run ml-deploy.yml --repo anoopkum/enterprise-ai-agents -f retrain_model=true
```

### Terraform state mv (required after resource rename)

If upgrading from a previous deployment, run these before the next apply:

```bash
cd day-02-loan-underwriting/terraform
terraform state mv module.acr.azurerm_container_registry.this       module.acr.azurerm_container_registry.acr
terraform state mv module.keyvault.azurerm_key_vault.this            module.keyvault.azurerm_key_vault.kv
terraform state mv module.keyvault.azurerm_role_assignment.admin     module.keyvault.azurerm_role_assignment.kv_admin
terraform state mv module.foundry.azurerm_storage_account.hub        module.foundry.azurerm_storage_account.aml
terraform state mv module.foundry.azurerm_application_insights.hub   module.foundry.azurerm_application_insights.aml
terraform state mv module.foundry.azurerm_machine_learning_workspace.hub module.foundry.azurerm_machine_learning_workspace.aml
terraform state mv module.monitoring.azurerm_log_analytics_workspace.this module.monitoring.azurerm_log_analytics_workspace.law
terraform state mv module.monitoring.azurerm_application_insights.this   module.monitoring.azurerm_application_insights.appi
```

---

## CI/CD Pipelines

| Workflow | Trigger | Jobs |
|---|---|---|
| `pr-checks.yml` | PR to main (day-02 paths) | pytest · terraform plan · Snyk SCA+IaC · SonarCloud · Checkov |
| `infra-deploy.yml` | Push to main (terraform/**) or manual | Bootstrap TF backend · terraform apply dev |
| `ml-deploy.yml` | Push to main (src/**) or manual | Train model · Build+push ACR · Snyk container scan · Deploy dev |

---

## Interview Talking Points

### ETL Agent
- "ChromaDB stores enriched application data in one collection and regulatory rules in another — same vector store, zero extra infra, two different retrieval patterns."

### Risk Scoring Agent
- "MLflow tracks every scoring run with the full feature vector and SHAP values. If a model is retrained, you can diff any past decision against the new model."
- "The model is loaded lazily on first call — avoids import-time failures when the pkl hasn't been trained yet in dev."

### Explainability Agent
- "GDPR Article 22 requires automated credit decisions to be explainable. SHAP values are passed into the GPT-4o prompt so the LLM grounds its explanation in actual feature contributions, not generic reasoning."
- "Rule-based fallback ensures zero downtime if Azure OpenAI is unreachable — the API always returns a decision."

### Compliance Agent
- "RAG over the regulatory KB means adding new rules (e.g., FCA CONC update) is a JSON append — no code change."

### Orchestrator
- "LCEL's pipe operator makes the data flow self-documenting. Each agent is independently testable as a `RunnableLambda`."

### Infrastructure
- "Terraform remote backend in Azure Blob with state locking — no local state files, safe for concurrent CI runs."
- "Container App uses system-assigned managed identity for both ACR pull and Key Vault secret access — no stored credentials anywhere in the pipeline."
