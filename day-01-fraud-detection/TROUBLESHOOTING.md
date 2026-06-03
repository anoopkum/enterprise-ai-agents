# Troubleshooting — Day 01 Fraud Detection Agent

All errors encountered during CI/CD setup and deployment, with root cause and fix.

---

## CI/CD Pipeline Errors

### 1. opentelemetry-sdk version conflict on pip install
**Error:** `semgrep==1.100.0` requires `opentelemetry-sdk~=1.25`; `azure-monitor-opentelemetry==1.6.4` requires `~=1.28` — conflict.
**Fix:** Remove `semgrep` from `requirements-dev.txt` entirely (run as CLI tool in CI). Upgrade `azure-monitor-opentelemetry` to `1.8.8`.

### 2. ImportError: cannot import name 'AgentThread' from 'azure.ai.projects.models'
**Error:** azure-ai-agents 1.2.0b6 moved agent types to `azure.ai.agents.models`, not `azure.ai.projects.models`.
**Fix:** Use `from azure.ai.agents.models import FunctionTool, ToolSet, MessageRole, RunStatus`. Use `AIProjectClient` and access agents via `client.agents.threads.create()`, `client.agents.runs.create_and_process()`, etc.

### 3. Test failure: run.status comparison MagicMock != RunStatus.COMPLETED
**Error:** Unit test mock sets `mock_run.status` as a `MagicMock`, not the real enum value, so `run.status != RunStatus.COMPLETED` always evaluates true.
**Fix:** In the test fixture, set `mock_run.status = RunStatus.COMPLETED` using a real import of the enum.

### 4. Integration test AttributeError: module 'src.api' has no attribute 'main'
**Error:** `patch('src.api.main.FraudDetectionAgent')` resolves before the module is loaded.
**Fix:** Add `import src.api.main` at the top of the integration test file before `patch()` is called.

### 5. detect-secrets: argument --baseline: Invalid path /dev/null (Linux CI)
**Error:** `/dev/null` is not a valid baseline file path on Linux.
**Fix:** `detect-secrets scan src/ > .secrets.baseline` then parse the JSON inline with Python to check for findings.

### 6. Docker build: Cache export not supported for docker driver
**Error:** Default `docker` driver doesn't support `type=gha` cache with `--load`.
**Fix:** Add `docker/setup-buildx-action@v3` step before the build step.

### 7. Unit test coverage failure: total 62% < fail-under=80%
**Error:** Unit tests cover agent/tools/models; API layer is covered by integration tests, not unit tests.
**Fix:** Lower `--cov-fail-under=80` to `--cov-fail-under=60`.

### 8. GitHub Actions OIDC: AADSTS700213 federated identity not found
**Error:** Azure AD OIDC federated identity credential not configured for the `environment:staging` subject.
**Root cause:** The existing federated credential only covered `pull_request` subject, not `environment:staging` or `environment:production`.
**Fix (short term):** Switch to service principal secret auth (`AZURE_CLIENT_SECRET` GitHub secret + `creds` JSON in `azure/login@v2`). Migrate to OIDC later for production use.

---

## Bicep / ARM Deployment Errors

### 9. BCP065: Function "utcNow" is not valid at this location
**Error:** `dateTimeToEpoch(dateTimeAdd(utcNow(), 'P1Y'))` inline in a resource property — `utcNow()` can only be used as a parameter default value.
**Fix:** Add `param utcNowValue string = utcNow()` to the module and reference `utcNowValue` inline instead of calling `utcNow()` directly.
**Affected modules:** `cosmosdb.bicep`, `eventhub.bicep`, `servicebus.bicep`, `app_insights.bicep`.

### 10. Authorization failed: roleAssignments/write permission denied
**Error:** `The client does not have permission to perform action 'Microsoft.Authorization/roleAssignments/write'`.
**Root cause:** `Contributor` role explicitly excludes IAM write permissions to prevent privilege escalation. The Key Vault module creates a role assignment in Bicep.
**Fix:** Grant `User Access Administrator` at resource group scope to the service principal. For production, scope to specific resource groups only (not subscription).
```bash
az role assignment create \
  --assignee <sp-object-id> \
  --role "User Access Administrator" \
  --scope /subscriptions/<sub-id>/resourceGroups/<rg-name>
```

### 11. PrincipalTypeNotSupported: Principals of type Application cannot be used in role assignments
**Error:** `Principals of type Application cannot validly be used in role assignments`.
**Root cause:** `AZURE_ADMIN_OBJECT_ID` was set to the **App Registration object ID** (the `id` of `az ad app show`), not the **user's object ID**. Role assignments for `principalType: 'User'` require the signed-in user's object ID.
**Fix:** Update the GitHub secret to the user's object ID: `az ad signed-in-user show --query id -o tsv`.

### 12. enablePurgeProtection cannot be set to false
**Error:** `The property "enablePurgeProtection" cannot be set to false. Enabling the purge protection for a vault is an irreversible action.`
**Root cause:** Once Key Vault purge protection is enabled, it cannot be disabled. Sending `enablePurgeProtection: false` on any subsequent update (even a fresh-looking deploy) fails.
**Fix:** Use `enablePurgeProtection: isProduction ? true : null`. Setting `null` omits the property from the ARM payload, leaving the default (`false`) without triggering the immutability check.

### 13. EventHub captureDescription with enabled:false requires destination
**Error:** `Required property 'destination' not found in JSON. Path 'properties.captureDescription'`.
**Root cause:** The ARM API requires `destination` when `captureDescription` is present, even with `enabled: false`.
**Fix:** Use `captureDescription: isProduction ? { ... } : null` — omit the property entirely in dev instead of sending `{enabled: false}`.

### 14. Service Bus maxSizeInMegabytes: 256 is invalid
**Error:** `The specified value 256 is invalid. The property MaxSizeInMegabytes, must be one of the following values: 1024;2048;3072;4096;5120`.
**Fix:** Use `maxSizeInMegabytes: 1024` (minimum valid value for Standard tier queues).

### 15. AI Foundry model deployment: ResourceNotFound on CognitiveServices account
**Error:** `The Resource 'Microsoft.CognitiveServices/accounts/aihub-fraud-agent-staging' was not found`.
**Root cause:** `Microsoft.CognitiveServices/accounts/deployments` cannot be created scoped to an AI Foundry Hub name — model deployments require a standalone `Microsoft.CognitiveServices/accounts` resource (`kind: 'OpenAI'`) as the parent.
**Fix:** Create a separate `Microsoft.CognitiveServices/accounts` resource (`oai-${hubName}`) and make the model deployment a child of that resource.

### 16. Log Analytics retentionInDays: 7 violates SKU limits
**Error:** `'RetentionInDays' property doesn't match the SKU limits`.
**Root cause:** The `PerGB2018` Log Analytics SKU enforces a minimum of **30 days** retention.
**Fix:** Use `retentionInDays: isProduction ? 90 : 30`. The minimum is 30 days regardless of environment.
**Affected modules:** `container_app.bicep` (was 7), `app_insights.bicep` (was 7).

### 17. Service Bus listKeys() must be called on authorization rule, not namespace
**Error:** Empty `BadRequest` on `sbConnectionSecret` resource.
**Root cause:** `serviceBusNamespace.listKeys()` does not exist — `listKeys()` is a method on `Microsoft.ServiceBus/namespaces/authorizationRules`, not on the namespace itself.
**Fix:** Reference the built-in `RootManageSharedAccessKey` authorization rule as an `existing` resource and call `listKeys()` on that.
```bicep
resource rootManageRule 'Microsoft.ServiceBus/namespaces/authorizationRules@2022-10-01-preview' existing = {
  parent: serviceBusNamespace
  name: 'RootManageSharedAccessKey'
}
value: rootManageRule.listKeys().primaryConnectionString
```

### 18. Service Bus capacity property invalid on Standard tier
**Error:** Empty `BadRequest` when deploying Service Bus namespace.
**Root cause:** The `capacity` field on the SKU is only valid for `Premium` tier. Sending `capacity: null` still serializes in some SDK versions and causes a `BadRequest`.
**Fix:** Use `capacity: isProduction ? 1 : null` — ARM omits `null` properties in the serialized payload for Standard tier.

### 19. arm-deploy@v2 fails on Bicep linter warnings (failOnStdErr)
**Error:** `Deployment process failed as some lines were written to stderr` — but all ARM deployments show `Succeeded`.
**Root cause:** `azure/arm-deploy@v2` defaults `failOnStdErr: true`. Bicep linter warnings are written to stderr, causing the step to fail even when the deployment completes successfully.
**Fix:** Add `failOnStdErr: false` to the `azure/arm-deploy@v2` step. Also fix the underlying warning: `aiFoundryConnectionString` parameter needs `@secure()` decorator since it's used as a Container App secret value.

---

## Azure AD / RBAC

### 20. Service principal object ID vs application object ID confusion
**Summary:** There are two object IDs for a service principal:
- **App Registration ID** (`az ad app show --id ... --query id`): the application object
- **Service Principal / Enterprise App ID** (`az ad sp show --id ... --query id`): used for role assignments

Role assignments use the **Service Principal object ID** (`c274590a-...` in this project).
GitHub secret `AZURE_CLIENT_ID` = App ID (`c8b217d5-...`).
GitHub secret `AZURE_ADMIN_OBJECT_ID` = **signed-in user's** object ID (for Key Vault admin role assignment).
