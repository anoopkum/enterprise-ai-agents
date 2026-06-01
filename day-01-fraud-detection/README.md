# Day 01 — Fraud Detection & Real-Time Alert Agent

**Industry:** Banking &nbsp;|&nbsp; **Platform:** Azure AI Foundry + Event Hubs + Container Apps &nbsp;|&nbsp; **Status:** ✅ Complete

---

## What This Agent Does

A bank transaction arrives (POS, online, ATM, mobile). Within **200ms** this agent:
1. Enriches it with 30-day history, velocity patterns, geolocation, and blacklist signals
2. Sends all signals to GPT-4o via Azure AI Foundry for reasoning
3. Returns an explainable decision: **APPROVE / REVIEW / BLOCK**
4. Writes an immutable audit record and fires alerts to ops and customer

---

## End-to-End Transaction Flow

```mermaid
sequenceDiagram
    autonumber
    participant Bank as Bank Core System<br/>(POS / API / Mobile)
    participant EH as Azure Event Hub<br/>(transactions stream)
    participant FN as Azure Function<br/>(trigger + enrichment)
    participant API as Container App<br/>(FastAPI)
    participant Agent as AI Foundry Agent<br/>(GPT-4o)
    participant TH as Tool: TransactionHistory<br/>(Cosmos DB)
    participant VC as Tool: VelocityCheck<br/>(Cosmos DB)
    participant GR as Tool: GeolocationRisk<br/>(in-memory + FATF list)
    participant BL as Tool: BlacklistCheck<br/>(Cosmos DB)
    participant SB as Azure Service Bus
    participant CM as Case Management<br/>(Cosmos DB decisions)
    participant ACS as Azure Communication<br/>(SMS / Email)

    Bank->>EH: Publish transaction event (JSON)
    EH->>FN: Trigger on new event
    FN->>FN: Validate schema, extract fields
    FN->>API: POST /analyze (transaction payload)
    API->>API: Pydantic validation + rate-limit check
    API->>Agent: create_thread() + send transaction JSON

    rect rgb(230, 245, 255)
        note over Agent,BL: Agent Reasoning Loop — tool calls in parallel
        Agent->>TH: get_transaction_history(customer_id, limit=30)
        TH-->>Agent: last 30 txns with amounts, merchants, locations
        Agent->>VC: check_velocity(customer_id, amount, timestamp)
        VC-->>Agent: velocity_score, flags (HIGH_FREQUENCY / AMOUNT_SPIKE)
        Agent->>GR: assess_geolocation_risk(current_loc, previous_loc, timestamps)
        GR-->>Agent: geo_score, flags (IMPOSSIBLE_TRAVEL / HIGH_RISK_COUNTRY)
        Agent->>BL: check_blacklist(merchant_id, ip, device, card_hash)
        BL-->>Agent: blacklist_hits, blacklist_score
    end

    Agent-->>API: JSON decision {fraud_score, risk_level, decision, signals, reasoning}
    API-->>FN: FraudDecision response
    FN->>CM: Write immutable audit record (Cosmos DB)

    alt decision == BLOCK or REVIEW
        FN->>SB: Enqueue fraud-alert message
        SB->>ACS: Send SMS + Email to customer
        SB->>CM: Create analyst review case
    end

    FN-->>Bank: Return decision + transaction_id
```

---

## Agent Tool Orchestration

How GPT-4o reasons over the 4 tools to produce a final risk score:

```mermaid
flowchart TD
    TX([Transaction Event\ntxn_id · customer_id · amount\ncurrency · merchant · location\nchannel · device · ip]) --> AGENT

    subgraph AGENT["Azure AI Foundry Agent — GPT-4o"]
        REASON[Agent Reasoning\nReads transaction context\nDecides which tools to call]

        REASON -->|customer_id + limit=30| TH
        REASON -->|customer_id + amount + timestamp| VC
        REASON -->|current_loc + previous_loc + timestamps| GR
        REASON -->|merchant_id + ip + device + card_hash| BL

        TH[TransactionHistoryTool\nLast 30 txns from Cosmos DB\nAmounts · merchants · locations]
        VC[VelocityCheckTool\nTxns per hour & per day\nAmount spike vs 30-day avg]
        GR[GeolocationRiskTool\nHaversine impossible travel\nFATF high-risk country list]
        BL[BlacklistCheckTool\nMerchant · IP · Device · Card\nSeverity-weighted score]

        TH -->|history context| SCORE
        VC -->|velocity_score 0-100\nvelocity_flags| SCORE
        GR -->|geo_risk_score 0-100\ngeo_flags| SCORE
        BL -->|blacklist_score 0-100\nhit_count| SCORE

        SCORE[Final Reasoning\nCombined signal analysis\nExplainable decision]
    end

    SCORE --> DEC{fraud_score}

    DEC -->|0 – 29| APPROVE([APPROVE\nLOW risk\nAuto-proceed])
    DEC -->|30 – 59| REVIEW1([REVIEW\nMEDIUM risk\nEscalate to analyst])
    DEC -->|60 – 79| REVIEW2([REVIEW\nHIGH risk\nUrgent escalation])
    DEC -->|80 – 100| BLOCK([BLOCK\nCRITICAL risk\nAuto-block card])

    style APPROVE fill:#51cf66,color:#000
    style REVIEW1 fill:#ffd43b,color:#000
    style REVIEW2 fill:#ff922b,color:#fff
    style BLOCK fill:#fa5252,color:#fff
```

---

## Azure Infrastructure Architecture

```mermaid
graph TB
    subgraph BANK["Bank Systems (External)"]
        POS[POS Terminal]
        MOB[Mobile App]
        WEB[Online Banking]
        ATM[ATM Network]
    end

    subgraph VNET["Azure Private VNet — eastus2"]

        subgraph INGEST["Ingestion Layer"]
            EH[Azure Event Hub\n8 partitions · 7-day retention\nAvro capture to Blob]
        end

        subgraph FNAPP["Azure Functions — Consumption Plan"]
            FN[event_hub_trigger.py\nSchema validation\nAPI orchestration]
        end

        subgraph ACA["Azure Container Apps Environment"]
            CA[fraud-detection API\nFastAPI · 2–20 replicas\nHTTP scaling]
        end

        subgraph AI["Azure AI Foundry"]
            HUB[AI Hub\nPrivate endpoint\nManaged network]
            PROJ[AI Project\nFraud Detection]
            MODEL[GPT-4o deployment\n50K TPM · GlobalStandard]
            HUB --> PROJ --> MODEL
        end

        subgraph DATA["Data Layer"]
            COSMOS[(Cosmos DB\nfrauddb database\n3 containers:\ntransactions\nblacklists\ndecisions\n4000 RU autoscale)]
            SB[Service Bus Premium\nfraud-alerts queue\nreview-queue\nDuplicate detection]
        end

        subgraph PLATFORM["Platform Services"]
            KV[Key Vault Standard\nSoft-delete 90d\nPurge protection ON\nPrivate endpoint]
            APPI[Application Insights\nOTel tracing\nCustom metrics]
            LAW[Log Analytics\n90-day retention]
            ACS[Azure Communication\nSMS + Email alerts]
        end

    end

    subgraph CICD["GitHub — CI/CD"]
        GHA[GitHub Actions\n9-stage pipeline]
        GHCR[GHCR\nContainer Registry]
    end

    POS & MOB & WEB & ATM -->|JSON events| EH
    EH -->|trigger| FN
    FN -->|POST /analyze| CA
    CA -->|Agents SDK| PROJ
    CA <-->|read/write| COSMOS
    CA -->|enqueue alert| SB
    SB -->|notify| ACS
    KV -.->|MI auth| CA
    KV -.->|MI auth| FN
    CA -.->|traces| APPI
    FN -.->|traces| APPI
    APPI --> LAW
    GHA -->|Bicep deploy| VNET
    GHA --> GHCR --> CA

    style AI fill:#e3f2fd,stroke:#1976d2
    style DATA fill:#f3e5f5,stroke:#7b1fa2
    style PLATFORM fill:#e8f5e9,stroke:#388e3c
```

---

## Security Architecture

```mermaid
flowchart TD
    subgraph PIPELINE["CI/CD Security Gates"]
        P1[Ruff — Lint] --> P2[Bandit + Semgrep\nSAST]
        P2 --> P3[detect-secrets\nCredential scan]
        P3 --> P4[Snyk + OWASP DC\nDependency CVEs]
        P4 --> P5[Checkov\nBicep IaC scan]
        P5 --> P6[Trivy\nContainer image CVEs]
        P6 --> P7[OWASP ZAP\nDAST on staging API]
        P7 --> P8[Manual approval\nProd deploy gate]
    end

    subgraph RUNTIME["Runtime Security Controls"]
        R1[Managed Identity\nNo stored credentials]
        R2[Key Vault references\nSecrets never in env vars]
        R3[Private Endpoints\nNo public Cosmos / EH]
        R4[TLS 1.3 only\nAll endpoints]
        R5[RBAC — least privilege\nrole assignments in Bicep]
        R6[Azure Defender\nThreat detection]
        R7[Non-root container\nRead-only filesystem]
    end

    subgraph DATA_SEC["Data Security"]
        D1[Cosmos DB encryption\nat rest + in transit]
        D2[Card data — SHA-256 hash\nPAN never stored]
        D3[Audit log immutable\nTTL 1 year in Cosmos]
        D4[GDPR compliant\nPII minimisation]
    end

    P8 -->|gates deployment| RUNTIME
    RUNTIME --> DATA_SEC
```

---

## Data Flow & Decision Logic

```mermaid
stateDiagram-v2
    [*] --> Received : Transaction arrives via Event Hub

    Received --> Validating : Schema + rate limit check
    Validating --> Rejected : Invalid payload (422)
    Validating --> Enriching : Valid transaction

    Enriching --> AgentReasoning : 4 tools called in parallel
    AgentReasoning --> Scoring : All tool responses collected

    Scoring --> Low : fraud_score 0–29
    Scoring --> Medium : fraud_score 30–59
    Scoring --> High : fraud_score 60–79
    Scoring --> Critical : fraud_score 80–100

    Low --> Approved : Auto-approve
    Medium --> AnalystQueue : Escalate to analyst
    High --> UrgentQueue : Urgent analyst escalation
    Critical --> AutoBlock : Block card immediately

    Approved --> AuditLog : Write decision record
    AnalystQueue --> AuditLog
    UrgentQueue --> AuditLog
    AutoBlock --> CustomerAlert : SMS + Email notification
    AutoBlock --> AuditLog

    AuditLog --> [*]
    CustomerAlert --> [*]
    Rejected --> [*]
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | Azure AI Foundry Agents SDK |
| LLM | GPT-4o (deployed via Azure AI Foundry) |
| Stream Ingestion | Azure Event Hubs (8 partitions) |
| Compute | Azure Container Apps + Azure Functions |
| Database | Azure Cosmos DB (NoSQL, 3 containers) |
| Alerting | Azure Service Bus Premium + Azure Communication Services |
| Secrets | Azure Key Vault (Private Endpoint, Purge Protection) |
| Observability | Azure Monitor + Application Insights + OpenTelemetry |
| IaC | Bicep (7 modules) |
| CI/CD | GitHub Actions (9 stages) |
| Security | Trivy · Bandit · Semgrep · OWASP ZAP · Snyk · Checkov |

---

## Key Features

- **Real-time scoring** — <200ms p99 latency end-to-end
- **Explainable AI** — every decision includes human-readable reasoning + signal list
- **Multi-signal fusion** — velocity, geolocation (Haversine), merchant category, device, IP blacklist
- **Risk tiers** — LOW auto-approve, MEDIUM/HIGH analyst queues, CRITICAL auto-block
- **Immutable audit trail** — 1-year retention in Cosmos DB for regulatory compliance
- **RBAC** — all role assignments provisioned via Bicep, Managed Identity throughout

---

## Deployment

```bash
cd day-01-fraud-detection
cp .env.example .env       # fill in subscription, resource group, AI Foundry conn string
az login
./deploy.sh                # provisions all 7 Bicep modules + deploys Container App
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/unit -v --cov=src --cov-report=term-missing
pytest tests/integration -v
```

## Security Controls Summary

| Control | Implementation |
|---------|---------------|
| Zero stored credentials | Azure Key Vault + Managed Identity |
| Network isolation | Private Endpoints on Cosmos DB, Key Vault, Event Hub |
| Encryption | TLS 1.3 in transit, AES-256 at rest (Cosmos) |
| Card data | SHA-256 hash only — raw PAN never touches this system |
| Audit | Immutable decisions container, 1-year TTL |
| IaC security | Checkov scan on every PR, SARIF uploaded to GitHub |
| Container | Non-root user, no unnecessary packages, Trivy-clean |
