# Day 01 — Fraud Detection & Real-Time Alert Agent

**Industry:** Banking  
**Platform:** Azure AI Foundry + Azure Event Hubs + Azure Container Apps  
**Status:** ✅ Complete

---

## Overview

Real-time transaction fraud detection using Azure AI Foundry Agents (GPT-4o). Ingests transaction events, reasons over anomaly patterns, and triggers alerts with explainable decisions.

## Architecture

```
Bank Transaction API / POS Systems
         │
         ▼
  Azure Event Hub  (real-time stream)
         │
         ▼
  Azure Function  (feature extraction + enrichment)
         │
         ▼
  Azure AI Foundry Agent  (fraud reasoning)
   ├── Tool: TransactionHistoryTool
   ├── Tool: VelocityCheckTool
   ├── Tool: GeolocationRiskTool
   └── Tool: BlacklistCheckTool
         │
         ▼
  Azure Service Bus  (alert queue)
         │
    ┌────┴────┐
    ▼         ▼
  Case Mgmt  Azure Communication Services
  (Cosmos DB)  (SMS/Email alert to customer)
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | Azure AI Foundry Agents SDK |
| LLM | GPT-4o (deployed via Azure AI Foundry) |
| Stream Ingestion | Azure Event Hubs |
| Compute | Azure Container Apps + Azure Functions |
| Database | Azure Cosmos DB (NoSQL) |
| Alerting | Azure Service Bus + Azure Communication Services |
| Secrets | Azure Key Vault |
| Observability | Azure Monitor + Application Insights |
| IaC | Bicep |
| CI/CD | GitHub Actions |
| Security | Trivy + Bandit + OWASP ZAP + Checkov |

## Key Features

- **Real-time scoring** — <200ms p99 latency
- **Explainable AI** — every decision includes reasoning
- **Multi-signal analysis** — velocity, geolocation, merchant category, device fingerprint
- **Human-in-loop** — high-confidence auto-block, medium escalates to analyst
- **Full audit trail** — immutable log in Cosmos DB
- **RBAC** — Azure AD + role assignments via Bicep

## Deployment

```bash
cd day-01-fraud-detection
cp .env.example .env          # fill in your values
az login
./deploy.sh                   # provisions all infra + deploys app
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AZURE_SUBSCRIPTION_ID` | Azure subscription |
| `AZURE_RESOURCE_GROUP` | Target resource group |
| `AZURE_LOCATION` | e.g. eastus2 |
| `AI_FOUNDRY_PROJECT_NAME` | AI Foundry project name |
| `AI_FOUNDRY_CONNECTION_STRING` | From AI Foundry portal |
| `EVENT_HUB_NAMESPACE` | Event Hub namespace |
| `COSMOS_DB_ENDPOINT` | Cosmos DB endpoint |

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/unit -v
pytest tests/integration -v --env staging
```

## Security Controls

- All secrets in Azure Key Vault (zero plain-text credentials)
- Managed Identity for service-to-service auth
- TLS 1.3 on all endpoints
- Cosmos DB encryption at rest
- Network isolation via VNet + Private Endpoints
- Checkov IaC scan on every PR
