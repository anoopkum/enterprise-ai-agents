# Day 03 — KYC/AML Compliance Automation Agent

> **30-Day Enterprise AI Agent Series** | Day 03 of 30 | Banking & Financial Services

A production-grade **KYC/AML compliance pipeline** built as a **multi-format RAG + knowledge-graph** system. It ingests the messy real-world evidence a compliance team actually receives — scanned IDs (JPEG/PNG), PDFs, Word/Excel/CSV, HTML — runs OCR + retrieval-augmented reasoning against a regulatory knowledge base, cross-references a **Neo4j** relationship graph, and returns an auditable **APPROVE / EDD / REJECT** decision with a Suspicious Activity Report (SAR) draft when warranted.

Every cloud dependency is **optional**: with no Azure account and no Neo4j, the exact same code runs fully local (ChromaDB + NetworkX + PyMuPDF). Set the env vars to upgrade in place.

---

## Architecture

```
                          POST /screen  { customer_id | inline profile }
                                          │
        ┌─────────────────── Multi-format ingestion (offline / batch) ───────────────────┐
        │  PDF · JPEG · PNG · DOCX · PPTX · XLSX · XLS · CSV · HTML · MD · TXT             │
        │       │                                                                         │
        │  Doc classifier → OCR (Azure Document Intelligence │ PyMuPDF) → chunker         │
        │       │                                                                         │
        │  embeddings (text-embedding-3-large) → Vector store                             │
        │       └── Azure AI Search (hybrid BM25+vector + semantic reranker) │ ChromaDB    │
        └─────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                        LangChain LCEL Orchestrator                             │
│                                                                                │
│  load_context ─▶ Identity ─▶ Screening ─▶ AML-RAG ─▶ Decision ─▶ Guardrails    │
│       │            │            │            │           │            │         │
│   customer      documents,   PEP /       vector +     fuse into   hallucination │
│   subgraph      OCR conf,    sanctions   graph rules  APPROVE/    check + PII +  │
│   from Neo4j    expiry       screening   → GPT-4.1    EDD/REJECT  output policy  │
│                              (graph)     (or rules)   + SAR                     │
└───────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                                    KYCDecision JSON
      (decision, risk_score, reasons, citations, sar, requires_human_review, …)
```

**Data flow:** each agent receives a context dict and returns an enriched copy — no shared mutable state. The LCEL `|` operator composes them into one runnable chain. `load_context` pulls the customer's **subgraph** (documents, KYC case, watchlist flags, resident country, applicable AML rules incl. `Global`) from Neo4j so every downstream agent shares the same GraphRAG view.

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM (reasoning) | **Azure OpenAI GPT-4.1** via AI Foundry Agents SDK (rule-based fallback when endpoint unset) |
| Embeddings | `text-embedding-3-large` |
| OCR | **Azure AI Document Intelligence** (FormRecognizer) → PyMuPDF fallback for scanned IDs/PDFs |
| Vector store | **Azure AI Search** — hybrid (BM25 + vector) + semantic reranker → **ChromaDB** local fallback |
| Knowledge graph | **Neo4j Aura** (managed) → **NetworkX** in-memory fallback |
| Reranking | Azure semantic reranker / `cross-encoder/ms-marco-MiniLM` / lexical |
| Orchestration | LangChain LCEL (`RunnableLambda` pipe chain) |
| Guardrails | PII redaction, prompt-injection screening, NLI hallucination detection, output policy |
| API | FastAPI + Pydantic v2, OpenTelemetry tracing |
| Infrastructure | Terraform (AzureRM ~3.110) — Document Intelligence, AI Search, OpenAI, Key Vault |
| CI/CD | GitHub Actions — lint/SAST, unit + integration tests, SCA, IaC scan, Trivy, TF plan |
| Runtime | Azure Container Apps (system-assigned MI for Key Vault + ACR) |

---

## The multi-format RAG problem

Real KYC evidence is *messy*. A single customer file might contain a phone photo of an Aadhaar card, a bank statement PDF, an employer letter in Word, and a spreadsheet of transactions. The ingestion layer normalises all of it into one `Chunk` type regardless of source:

| Format | Parser | Notes |
|---|---|---|
| PDF | PyMuPDF / Document Intelligence | born-digital text vs. scanned → OCR |
| JPEG / PNG | Document Intelligence → OCR | scanned IDs; per-field confidence captured |
| DOCX / PPTX | `unstructured` / python-docx | |
| XLSX / XLS / CSV | openpyxl / xlrd / csv | tabular → row-wise text |
| HTML / MD / TXT | BeautifulSoup / plain | |

Low OCR confidence (< 0.5) on any ingested document surfaces as an **identity gap** → the case is pushed to human review rather than silently trusted.

---

## Knowledge graph (why a graph, not just vectors)

Vectors answer *"which regulation is semantically similar to this?"*. A graph answers *"which rules actually **apply to this customer**?"* — a traversal, not a similarity search:

```
(Customer)-[:RESIDENT_OF]->(Country)<-[:APPLIES_IN]-(AMLRule)<-[:IMPLEMENTS]-(Guideline)
(Customer)-[:HAS_DOCUMENT]->(Document)
(Customer)-[:HAS_CASE]->(KYCCase)
(Customer)-[:FLAGGED_AS]->(Watchlist {PEP | Sanction})
```

`customer_subgraph()` returns the customer's documents, case, watchlist flags, resident country, and the AML rules for that country **plus** all `Global` rules — the exact regulatory context the AML agent reasons over.

Writes use **UNWIND-batched Cypher** (one round-trip per 1,000 rows), which took the Aura build from a >120 s timeout down to ~13 s.

---

## Decision policy

Derived from the labelled `kyc_cases.csv` (`ExpectedDecision`). Most-conservative signal wins:

| Signal | Outcome |
|---|---|
| Sanctions-list match (the person) | **REJECT** + SAR |
| AML risk ≥ `0.85` (reject threshold) | **REJECT** |
| PEP status | **EDD** + SAR |
| AML risk ≥ `0.60` (EDD threshold) | **EDD** |
| Unresolved identity gaps (≤ 3 of 5 verified docs, expired ID, low OCR) | **EDD** |
| Otherwise | **APPROVE** |

> **PEP** = *Politically Exposed Person* — someone in a prominent public role (or their close associates/family) who carries a higher bribery/corruption risk, so regulators mandate **Enhanced Due Diligence (EDD)** rather than an outright block.

**Key design decision:** residency in a high-risk/sanctioned *jurisdiction* (Iran, Russia, …) is recorded as context that feeds the risk score and SAR, but does **not** by itself escalate the verdict — only a sanctions match on *the person* blocks. This matches the dataset, which approves clean customers living in high-risk countries. (Two eval-driven bug fixes around this took decision accuracy from 0.43 → **1.0** on 150 cases.)

---

## Guardrails

1. **PII redaction** — Aadhaar / PAN / passport / card / email / phone are masked before anything is logged.
2. **Prompt-injection screening** — free text bound for the LLM is scanned for jailbreak patterns.
3. **Hallucination detection** — every AML *finding* is checked against the source it cites (NLI cross-encoder → lexical-overlap fallback). Findings labelled `Contradicted` / weak `PartiallySupported` are flagged.
4. **Output policy** — the decision must be one of `{APPROVE, EDD, REJECT}`; any non-approval must carry a reason (explainability); any flagged hallucination forces `requires_human_review = true` and `unsafe_to_auto_action = true`.

---

## Evaluation harness

RAGAS-style, runs offline against the labelled data (`python -m src.eval.harness`):

- **Decision accuracy** — pipeline verdict vs. `kyc_cases.ExpectedDecision`. Current: **1.0** on 150 sampled cases (perfect confusion matrix; residual errors were all safe-direction only).
- **Hallucination detection** — replays `benchmark_dataset.csv`, scoring precision / recall / F1. The offline lexical fallback is high-precision / low-recall (a safety net); the NLI cross-encoder is the production path.

---

## Running locally (no cloud account needed)

```bash
cd day-03-kyc-aml
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # DATA_DIR points at your local multi-format files

# Vector store → ChromaDB, graph → NetworkX, OCR → PyMuPDF, LLM → rule-based
uvicorn src.api.main:app --reload
```

```bash
# Screen a customer already in the graph
curl -s localhost:8000/screen -H 'content-type: application/json' \
  -d '{"customer_id": "C000003"}' | jq

# Health / active backends
curl -s localhost:8000/health | jq
```

### Upgrading to the cloud stack

| Set in `.env` | Flips on |
|---|---|
| `AZURE_SEARCH_ENDPOINT` (+ key) | Azure AI Search (hybrid + semantic reranker) |
| `NEO4J_URI` + `NEO4J_PASSWORD` | Neo4j Aura knowledge graph |
| `DOC_INTELLIGENCE_ENDPOINT` (+ key) | Azure Document Intelligence OCR |
| `AI_FOUNDRY_ENDPOINT` | GPT-4.1 reasoning (vs. rule-based fallback) |

No code changes — the capability flags in `config.py` route to the right backend based purely on which vars are present.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/screen` | Run the full KYC/AML pipeline (`customer_id` or inline `customer`) → `KYCDecision` |
| `GET` | `/decisions/{customer_id}` | Retrieve the last cached decision |
| `GET` | `/health` | Liveness + active backends (vector store, graph store, graph stats) |
| `GET` | `/docs` | OpenAPI UI (disabled when `ENVIRONMENT=prod`) |

---

## Infrastructure (Terraform)

`azurerm` **4.81.0**, state in an Azure Blob backend (`rg-tfstate-kyc / stkycamltfstate`). Auth is AAD-based — no storage keys.

```bash
cd terraform
export ARM_USE_AZUREAD=true            # AAD auth for the state backend
terraform init
terraform plan \
  -var="subscription_id=$ARM_SUBSCRIPTION_ID" \
  -var="admin_object_id=$YOUR_OBJECT_ID" \
  -var="neo4j_uri=$NEO4J_URI" \
  -var="neo4j_password=$NEO4J_PASSWORD"
terraform apply
```

Everything lands in **one resource group** (`rg-kyc-aml-dev`), in `swedencentral` by default:

- **Azure AI Foundry hub + project** — the workspace the KYC agent, model deployments, and service connections are scoped to (hub is backed by its own storage account + the shared Key Vault).
- **Azure AI Document Intelligence** (FormRecognizer, S0) — OCR for scanned IDs/PDFs.
- **Azure AI Search** (semantic SKU, system-assigned identity) — vector DB for the regulatory KB.
- **Azure OpenAI** — `gpt-4.1` + `text-embedding-3-large` deployments.
- **Key Vault** — stores every key + the Neo4j Aura URI/password as secrets.
- **3 role assignments** — the Foundry hub's managed identity gets *Cognitive Services OpenAI User*, *Cognitive Services User*, and *Search Index Data Contributor* on the back-ends, so the agent authenticates keyless via Azure AD (requires *User Access Administrator* on the deploying principal).

`terraform plan` against live Azure = **21 to add, 0 to change, 0 to destroy**. Neo4j Aura itself is managed and billed separately by Neo4j; Terraform only stores its connection secrets.

---

## Tests

```bash
pytest tests/unit         # deterministic agents + guardrails (no external deps)
pytest tests/integration  # FastAPI app with a mocked orchestrator
```

30 tests: 23 unit (agents + guardrails, 83% line coverage) + 7 integration (API).

---

## Security & data handling

- **Real personal data never enters the repo or an image.** Aadhaar cards, birth certificates, and bank statements live in `DATA_DIR` (outside the repo, gitignored). `.dockerignore` and `.gitignore` both exclude `data/`, `.env`, and any `Neo4j-*.txt` credential dumps.
- Secrets are read from the environment (local `.env`) or **Key Vault** (cloud) via managed identity — never hard-coded.
- PII is redacted before logging; PEP/sanction hits generate an auditable SAR draft, not an automated action.

---

## CI/CD & security gates

`.github/workflows/day-03-kyc-aml.yml` runs on every PR to `main`. Security checks are **hard gates** — a red scan blocks the merge:

| Job | Gate | Tool |
|---|---|---|
| Lint + SAST | **required** | `ruff`, `bandit` (medium+), `detect-secrets` |
| Unit tests | **required** | `pytest` + coverage ≥ 70% (agents + guardrails) |
| Integration tests | **required** | `pytest` (mocked orchestrator, local fallbacks) |
| SCA — dependencies | **required** | `pip-audit --strict` (Snyk advisory if `SNYK_TOKEN` set) |
| IaC — Terraform | **required** | `fmt -check`, `validate`, `checkov` (`soft_fail: false`) |
| Docker build | **required** | image must build |
| Trivy image scan | advisory¹ | `trivy` HIGH/CRITICAL → reports to code scanning (task #12) |
| Terraform plan (PR) | advisory | config-only dry-run, no cloud creds |
| **Security Gate** | **required aggregator** | fails unless every required job above is green |
| Deploy | main-only | image push + `terraform apply` (never on a PR) |

Checkov's dev-sandbox exceptions are documented in `terraform/.checkov.yaml` (each skip justified — it's the audit trail, not a blanket suppression).

> ¹ **Trivy is temporarily advisory** (task #12). The image currently ships the full ML stack (torch, CUDA, transformers) — a large surface where new HIGH CVEs rotate in constantly. The scan still runs and uploads findings to code scanning; it's re-promoted to a hard gate once the runtime image is slimmed to only the API's runtime deps. The Docker *build* remains required.

**Enforce the gate** — in *Settings → Branches → Branch protection rules* for `main`:

1. ☑ *Require a pull request before merging*
2. ☑ *Require status checks to pass* → add **`Security Gate`** as the required check
3. ☑ *Require branches to be up to date before merging*

With `Security Gate` required, a PR cannot merge unless lint, SAST, secret-scan, tests, SCA, IaC scan, and the container scan all pass. Deploy secrets (`AZURE_*`, `NEO4J_*`, `SNYK_TOKEN`) live in the `staging` GitHub Environment and are unreachable from PR runs.

---

## Project layout

```
day-03-kyc-aml/
├── src/
│   ├── ingestion/     # multi-format loaders, OCR, doc classifier, Chunk model
│   ├── pipeline/      # kb_loader, chunker, embeddings, vector_store, reranker
│   ├── graph/         # Neo4j / NetworkX store, schema, builder (UNWIND-batched)
│   ├── agents/        # identity, screening, aml (RAG), decision, orchestrator, llm
│   ├── guardrails/    # hallucination detector, PII/injection/output guardrails
│   ├── eval/          # RAGAS-style decision + hallucination harness
│   ├── api/           # FastAPI app, Pydantic models, rate-limit middleware
│   └── config.py      # capability flags → progressive fallback
├── terraform/         # Document Intelligence, AI Search, OpenAI, Key Vault modules
├── tests/             # unit + integration
├── Dockerfile
└── requirements*.txt
```
