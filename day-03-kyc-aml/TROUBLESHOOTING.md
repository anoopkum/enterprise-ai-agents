# Troubleshooting — KYC/AML Compliance Automation Agent

Issues encountered building and deploying Day 03. Ordered from most impactful (blocked the deploy) to least. Every item here surfaced at `terraform apply` or in CI — a green unit-test run does **not** catch any of them.

---

## Key Vault RBAC 403 — every secret write fails during `terraform apply`

**Error:** The deploy job fails on the first `azurerm_key_vault_secret` resource (and every one after it):
```
Error: checking for presence of existing Secret "neo4j-uri" ...
403: Caller is not authorized to perform action on resource.
Action: 'Microsoft.KeyVault/vaults/secrets/readMetadata/action'
Assignment: (not found)
Caller: appid=...;oid=c274590a-ec15-4a37-be8f-3e034655932e;...
Code: ForbiddenByRbac
```
All 8 secret writes fail: `neo4j-uri`, `neo4j-password`, `doc-intelligence-key`, `doc-intelligence-endpoint`, `azure-openai-api-key`, `azure-openai-endpoint`, `azure-search-endpoint`, `azure-search-admin-key`.

**Cause:** The Key Vault uses **RBAC authorization** (`enable_rbac_authorization = true`), not access policies. The module only granted `Key Vault Administrator` to `admin_object_id` — the human operator. The principal that actually runs `terraform apply` in CI is the **service principal** (`oid c274590a-...`), which had **no data-plane role** on the vault. Control-plane rights (Contributor) do **not** grant data-plane secret access on an RBAC vault.

**Fix (in `modules/keyvault/`):** Grant the deploying principal the `Key Vault Secrets Officer` role, then wait for RBAC propagation before any secret write:
```hcl
resource "azurerm_role_assignment" "kv_deployer_secrets" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.deployer_object_id   # = data.azurerm_client_config.current.object_id
}

resource "time_sleep" "kv_rbac_propagation" {
  depends_on      = [azurerm_role_assignment.kv_deployer_secrets, azurerm_role_assignment.kv_admin]
  create_duration = "120s"
  triggers = { kv_id = azurerm_key_vault.kv.id }
}
```
In `main.tf`, pass `deployer_object_id = data.azurerm_client_config.current.object_id` to the module.

**The gated-output trick (why there are two outputs):** RBAC role assignments take **~1–2 minutes to propagate**. A blanket `depends_on` would serialize *everything* behind the 120s wait. Instead, export a second, gated Key Vault ID that only secret-writers consume:
```hcl
# outputs.tf
output "id" {                      # ungated — control-plane consumers (AI Foundry hub) use this
  value = azurerm_key_vault.kv.id
}
output "secrets_key_vault_id" {    # gated behind the sleep — only secret writers use this
  value = time_sleep.kv_rbac_propagation.triggers["kv_id"]
}
```
Re-exporting `triggers["kv_id"]` (rather than referencing `time_sleep`'s own attributes) yields the *same* vault ID string but carries the sleep as a hidden dependency. Secret resources and back-end modules that write keys reference `module.keyvault.secrets_key_vault_id`; the AI Foundry hub (which only needs the vault as a control-plane association) references the ungated `module.keyvault.id` and creates in parallel.

**Verified:** After the fix, deploy logs show the 2m0s wait, then all 8 secrets write in 3–4s each. Requires the `hashicorp/time` provider (`~> 0.12`) in `required_providers`.

**Reuse for future days:** Any day that provisions an RBAC Key Vault + writes secrets from CI needs this deployer-role + `time_sleep` + gated-output pattern.

---

## `gpt-4.1` rejected — `ServiceModelDeprecating` for new deployments

**Error:** The OpenAI module fails to create the chat deployment:
```
400 - {"error":{"code":"ServiceModelDeprecating","message":
"The model 'Format:OpenAI,Name:gpt-4.1,Version:2025-04-14' is in
deprecating state and cannot be used for new deployments."}}
```

**Cause:** Model deprecation on Azure OpenAI is **subscription- and region-scoped** by enrollment. `gpt-4.1 / 2025-04-14` was still fine (status `None`) in other subscriptions checked locally, but was flagged deprecating in the CI subscription hosting `rg-kyc-aml-dev`. "Deprecating" means *existing* deployments keep working but *new* ones are blocked — so a version that worked yesterday can block a fresh `apply` today. You cannot rely on a hard-pinned version surviving.

**Fix:** Switched the chat model to **`gpt-4o` (version `2024-11-20`)** across Terraform and app config:
- `modules/foundry/variables.tf` — `chat_model_name = "gpt-4o"`, `chat_model_version = "2024-11-20"`, `chat_deployment_name = "gpt-4o"` (these lived in `modules/openai` before the Foundry consolidation below)
- `modules/foundry/main.tf` — chat deployment resource is named `chat`
- `src/config.py` — `openai_deployment` default `"gpt-4o"`
- `.env.example` — `AZURE_OPENAI_DEPLOYMENT=gpt-4o`

**Critical coupling — the app calls the deployment BY NAME:** The runtime looks up the deployment via `AZURE_OPENAI_DEPLOYMENT`. If the Terraform `chat_deployment_name` and the app's `AZURE_OPENAI_DEPLOYMENT` drift apart, you get a **404 DeploymentNotFound at runtime** with a perfectly green `apply`. Keep them identical.

**Reuse for future days:** Don't hard-pin a chat-model version that may be mid-deprecation in the target sub. If a version is rejected, `az cognitiveservices account list-models -n <account> -g <rg>` on the *target* subscription lists what is actually deployable there.

---

## Consolidated to one Foundry (FDP) resource — endpoint split is a runtime footgun

**Context:** The original design carried a standalone **Azure OpenAI** resource *plus* a classic **AI Foundry hub + project + backing storage account** — four resources where the model host (OpenAI) and the agent workspace (hub/project) were separate, wired by an (implicit, and actually missing) connection. That's redundant: a model can never be "deployed on the hub" — a deployment always lives on a Cognitive Services account. Consolidated to the modern **Foundry (FDP)** design: one `kind=AIServices` account with `project_management_enabled = true` that **both hosts the deployments and contains the project**. Dropped the standalone OpenAI resource, the classic hub, and the storage account. This is `modules/foundry/` (replaced `modules/openai` + `modules/ai_foundry`).

**Confirmed pure-AzureRM** (no AzAPI provider): `azurerm_cognitive_account` (kind `AIServices`) + `azurerm_cognitive_account_project` + `azurerm_cognitive_deployment`, all in azurerm 4.81. AzAPI is only needed for *connections* / *capability hosts* — which we don't use, precisely because the models are deployed **on** the same account the project lives in, so there's no cross-resource connection to declare.

**The footgun — two endpoints on the ONE resource, different formats:**
| Client | Env var | Endpoint form |
|---|---|---|
| Agents SDK (`AgentsClient`, chat) | `AI_FOUNDRY_ENDPOINT` | `https://<acct>.services.ai.azure.com/api/projects/<project>` |
| `AzureOpenAI` (embeddings) | `AZURE_OPENAI_ENDPOINT` | `https://<acct>.cognitiveservices.azure.com/` |

Both point at the *same* Foundry account but are **not interchangeable**. Set the project endpoint for embeddings → embeddings 404; set the account endpoint for the Agents client → agent calls fail. This is why `config.py` now has **two** vars (`ai_foundry_endpoint` + `azure_openai_endpoint`) and two capability flags (`use_foundry_agents` for chat, `use_azure_openai` for embeddings). Terraform surfaces both: outputs `ai_foundry_project_endpoint` and `azure_openai_endpoint`. The `azurerm_cognitive_account_project` resource does **not** expose the project endpoint attribute, so it's constructed from the documented form (`custom_subdomain_name` == account name).

**This is a destructive migration for an existing deploy.** On the next `terraform apply` after this change, Terraform destroys the old standalone OpenAI resource, the classic hub, the project, and the backing storage account, then creates the new Foundry account. Expect deletes in the plan. Acceptable here (no persisted agents/threads matter; the AI Search KB re-indexes), but don't run it blind against a stack you care about.

---

## Container App bootstrap — the image/secrets can't be declared in Terraform

**Symptom (would-be):** Declaring the real image, the ACR `registry {}` block, or Key Vault `secret {}` references directly on `azurerm_container_app` fails on the **first** apply — the app can't pull a private image or read a KV secret because the roles that permit it don't exist yet.

**Cause — a hard ordering cycle.** Every role the app needs (`AcrPull` to pull, `Key Vault Secrets User` to resolve a KV reference, the Cognitive/Search roles) is granted to the app identity's `principal_id`. That principal **does not exist until the app is created**. So the app must be created *before* its roles — meaning at create time it has none of them. A private-image pull or KV-secret resolution in that same apply therefore 403s.

**Fix — the shell + CLI pattern (cloned from Day 01/02):** Terraform provisions the app as a **shell**: a public placeholder image (`containerapps-helloworld`), no registry, no secrets, and `lifecycle { ignore_changes = [template, ingress, registry, secret, identity] }`. The deploy workflow then, **after** `terraform apply` has created the identity and its role grants (and the image build has given them ~1 min to propagate), runs:
- `az containerapp registry set --identity system` — bind ACR pull to the MI,
- `az containerapp secret set --secrets "…=keyvaultref:<uri>,identityref:system"` — the Neo4j KV references,
- `az containerapp update --image <acr>/kyc-aml@<digest> --set-env-vars …` — the real image + runtime env.

`ignore_changes` is what stops the next `terraform apply` from reverting the CLI's image/registry/secret back to the placeholder. (`system`-identity KV references specifically **cannot** be set at `az containerapp create` time either — MS docs note the system identity isn't available until after creation — which is the same cycle, and the same reason we set them post-provision.)

**Reuse for future days:** Any day that runs its own image on Container Apps with MI-based ACR/KV access needs this shell-in-Terraform + wire-with-CLI split. Don't try to declare the image + registry + KV secret in one apply.

---

## `azurerm_container_registry` — `retention_policy` block removed in azurerm 4.x

**Symptom:** `terraform validate` fails with `Blocks of type "retention_policy" are not expected here` when cloning the Day-02 ACR module (which targets azurerm 3.x) into Day-03 (pinned to **4.81**).

**Cause:** In azurerm 4.x the nested `retention_policy { days, enabled }` block on `azurerm_container_registry` was replaced by a single top-level attribute, **`retention_policy_in_days`** (Premium SKU only).

**Fix:** `retention_policy_in_days = var.is_production ? 7 : null` (null = unset on the Basic dev SKU). `georeplications` remains a block. Watch for the same 3.x→4.x block-to-attribute flattening on other resources when copying modules across days.

---

## Role assignments belonged on the wrong principal

**Symptom (latent):** The pre-Container-App code granted `Cognitive Services User` (Doc Intelligence) and `Search Index Data Contributor` (Search) to the **Foundry account's** managed identity. That's the wrong principal — those calls would 403 at runtime once a real host existed.

**Cause:** The app calls Search and Document Intelligence *itself* — `vector_store.py` and `ocr.py` both authenticate with `DefaultAzureCredential` from inside the container. So the **Container App's** MI is the caller, not the Foundry account's. (The Foundry account only needs to reach its *own* deployed models, which are local to it — no cross-resource grant.)

**Fix:** When the Container App landed, all six role assignments were (re)pointed at `module.containerapp.principal_id`: `AcrPull`, `Key Vault Secrets User`, `Cognitive Services OpenAI User` (embeddings, account endpoint), `Azure AI User` (agents, project endpoint — pinned by GUID `53ca6127-…` because the role was renamed Azure AI User → *Foundry User* mid-rollout), `Search Index Data Contributor`, and `Cognitive Services User`.

**Reuse for future days:** Grant back-end roles to whichever identity actually makes the SDK call. For a keyless app that is the Container App's MI — not the model host's.

---

## `ruff` CI drift — rules change between minor versions

**Symptom:** The `lint-and-sast` job flags (or stops flagging) code with no source change — CI is non-deterministic across runs as the runner picks up a newer ruff.

**Cause:** `ruff`'s default rule set expands between releases. An unpinned `ruff` in `requirements-dev.txt` means each CI run may use a different version and therefore a different lint contract.

**Fix:** Pin the version and the rule selection explicitly:
- `requirements-dev.txt` — `ruff==0.15.22`
- `ruff.toml` — `select = ["E4", "E7", "E9", "F"]` (the pyflakes + critical-error subset, matching ruff's documented default so upgrades don't silently add rules)

**Reuse for future days:** Pin every linter/formatter/scanner version in `requirements-dev.txt`. "Latest" is a moving target that turns CI red on unrelated PRs.

---

## Checkov SARIF upload — file not found

**Symptom:** The `iac-scan` job's `upload-sarif` step fails with a missing-file error even though Checkov ran and produced `results.sarif`.

**Cause:** A `uses:` step (a composite/JS action) does **not** honor the job's `defaults.run.working-directory`. `defaults.working-directory` only applies to `run:` shell steps. Checkov ran under the working directory and wrote its SARIF into `day-03-kyc-aml/`, but `upload-sarif` resolved its `sarif_file` path relative to the **repo root**.

**Fix:** Give the upload step a repo-root-relative path (or set the output directory explicitly on the Checkov step and point the upload at the same absolute path). Don't assume `working-directory` carries into action steps.

---

## Dependency-scan CVEs — `starlette` / `chromadb` transitive pins

**Symptom:** The `dependency-scan` (Snyk / pip-audit) job fails on known CVEs pulled in transitively.

**Cause:** FastAPI pulls `starlette`, and the RAG fallback pulls `chromadb`; both had advisory CVEs at versions inside the allowed range.

**Fix:** Add explicit floor pins in `requirements.txt` for the transitive packages to force patched versions. Re-run the scan to confirm the advisory clears.

**Reuse for future days:** When a scanner flags a transitive dependency, pin the *transitive* package directly in `requirements.txt` rather than loosening the scanner.

---

## GitHub Actions — SonarCloud S7637 (unpinned action tags)

**Symptom:** SonarCloud reports 13 HIGH issues, all rule `S7637`: "Use a commit SHA to pin the action."

**Cause:** Referencing actions by mutable tag (`actions/checkout@v4`) is a supply-chain risk — a tag can be re-pointed at malicious code.

**Fix:** Pin every `uses:` to a full 40-char commit SHA with the version in a trailing comment:
```yaml
- uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
```
All 13 were pinned (checkout, setup-python, upload-artifact, setup-terraform, checkov-action, codeql/upload-sarif, snyk, trivy, docker/metadata, docker/setup-buildx, docker/build-push, docker/login, azure/login). This cleared all 13 HIGH findings.

---

## SonarCloud Quality Gate fails on hotspots — but it's not a required check

**Symptom:** The SonarCloud Quality Gate shows failed on a PR even after all vulnerabilities are fixed.

**Cause:** Remaining items are **security hotspots** (`S8541`/`S8544` — pip `--only-binary`/hash-locked installs; `S6378` — missing `identity {}` on a storage account), not vulnerabilities. Hotspots require manual "make sure it's safe here" review; they do **not** affect the Security Rating and do **not** block anything unless you make the gate a required check.

**Key nuance:** The gate is evaluated on the **PR diff**, not the whole project. PR #5 failed the gate (its diff touched hotspot lines); PR #6 *passed* the same gate because its diff introduced no new hotspots — the pre-existing ones aren't re-counted against an unrelated diff.

**Fix:** Not blocking. The pip hash-lock hotspots are deferred to a dedicated lockfile PR (changing the Dockerfile `pip install` line risks breaking the required Docker build). The TF `S6378` `identity {}` hotspot is **no longer applicable** — its target (`azurerm_storage_account.hub` in the old `modules/ai_foundry`) was removed in the Foundry consolidation. See **Known gaps** below.

---

## Trivy container scan is advisory, not a gate

**Symptom:** The `build-and-scan` job's Trivy step has `continue-on-error: true` and the README/workflow mark it "advisory" rather than "required."

**Cause:** The runtime image ships the full ML stack (`torch` + CUDA libs, `transformers`, etc.) for the embedding/OCR fallbacks. These base layers carry a long tail of OS/library CVEs that would fail a strict gate on every build regardless of our code.

**Fix (interim):** Trivy runs and reports but does not block; a `.trivyignore` suppresses the known base-image noise.

**Proper fix (deferred — task #12):** Build a **multi-stage Dockerfile** with a slim runtime stage carrying only runtime deps (drop build toolchain, CUDA dev libs, test deps). Then remove `continue-on-error`, clear `.trivyignore`, and restore Trivy to a REQUIRED gate in both the workflow and README.

---

## `terraform init` hits the remote backend despite `-backend=false`

**Symptom:** Local `terraform init -backend=false` still tries to reach `rg-tfstate-kyc` / `stkycamltfstate` and fails (that backend isn't in the local user's subscription).

**Cause:** A stale `.terraform/` directory from a prior init cached the backend config; `-backend=false` doesn't override an already-initialized backend record.

**Fix:**
```bash
rm -rf .terraform .terraform.lock.hcl
terraform init -backend=false   # for local validate/plan only
```
Re-init then installs providers cleanly (e.g. `hashicorp/time` v0.14.0).

---

## `gh` CLI quirks encountered

**`gh secret list` panics with a Go nil-pointer** when the base repo is ambiguous (multiple remotes / detached context):
```bash
# Fix: always pass --repo explicitly
gh secret list --repo anoopkum/enterprise-ai-agents
```

**`gh pr merge <n>` returns exit code 1 but the merge actually succeeds** — the non-zero exit is warning noise (e.g. branch-delete warning). Confirm the real state before retrying:
```bash
gh pr view <n> --json state -q .state   # expect: MERGED
```
Retrying the merge blindly on the exit-1 will then error with "already merged."

---

## Known gaps (not failures — tracked follow-ups)

1. **~~No compute host in Terraform~~ — RESOLVED.** Added `modules/acr` (Azure Container Registry) + `modules/containerapp` (Log Analytics + Container Apps Environment + Container App, system-assigned MI, ingress `:8000`). The app's identity is granted `AcrPull`, `Key Vault Secrets User`, `Cognitive Services OpenAI User` + `Azure AI User` (Foundry account), `Search Index Data Contributor`, and `Cognitive Services User`. The deploy job now runs `terraform apply` → push image to ACR → `az containerapp` sets the real image + the two Foundry endpoints + Neo4j KV secret refs → `/health` smoke test. See the two footguns documented below (bootstrap ordering; role principal).
2. **Trivy re-promotion to REQUIRED** — needs the slim multi-stage runtime image first (task #12 above).
3. **SonarCloud medium hotspots** — pip `--only-binary`/hash-lock (`S8541`/`S8544`) deferred to a lockfile PR. (The TF `S6378` storage-account `identity {}` hotspot is **no longer applicable** — the backing storage account was removed in the Foundry consolidation above.)
4. **`main` is unprotected** — enable branch protection with "Security Gate" as a required status check (operator action in GitHub settings; the aggregator job exists but isn't enforced).
5. **Neo4j Aura is managed outside Terraform** — only its connection secrets live in Key Vault. Provisioning/scaling happens in the Aura console.

---

## Notes for local runs

- Run tests from the day directory, not the repo root:
  ```bash
  cd day-03-kyc-aml
  pytest tests/ -v --tb=short
  ```
- Real PII test documents (Aadhaar, bank statements, birth certs) live in `data/` and are **gitignored** — never commit them to the public repo. Only `data/.gitkeep` is tracked.
- `.env`, `Neo4j-*.txt`, and any credential files are gitignored and must stay that way.
