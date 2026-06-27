#!/usr/bin/env bash
# Deploy Day 01 — Fraud Detection Agent to Azure
set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-dev}"
LOCATION="${AZURE_LOCATION:-eastus2}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-fraud-agent-${ENVIRONMENT}}"
PROJECT_NAME="fraud-agent"

echo "=================================================="
echo "  Deploying Fraud Detection Agent"
echo "  Environment : ${ENVIRONMENT}"
echo "  Location    : ${LOCATION}"
echo "  Resource Grp: ${RESOURCE_GROUP}"
echo "=================================================="

# 1. Prerequisites check
command -v az >/dev/null 2>&1 || { echo "Azure CLI not installed"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker not installed"; exit 1; }
az account show >/dev/null 2>&1 || { echo "Not logged in: run 'az login'"; exit 1; }

ADMIN_OBJECT_ID=${AZURE_ADMIN_OBJECT_ID:-$(az ad sp show --id "${AZURE_CLIENT_ID}" --query id -o tsv 2>/dev/null || az ad signed-in-user show --query id -o tsv)}
echo "[1/6] Admin Object ID: ${ADMIN_OBJECT_ID}"

# 2. Create resource group
echo "[2/6] Creating resource group..."
az group create \
  --name "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --tags project="${PROJECT_NAME}" environment="${ENVIRONMENT}" \
  --output none
echo "     Resource group ready."

# 3. Bicep IaC scan (Checkov)
echo "[3/6] Scanning Bicep templates with Checkov..."
if command -v checkov >/dev/null 2>&1; then
  checkov -d infra/ --framework bicep --quiet --compact || {
    echo "WARNING: Checkov found IaC issues — review before prod deployment"
  }
else
  echo "     Checkov not found, skipping IaC scan (install: pip install checkov)"
fi

# 4. Deploy Bicep
echo "[4/6] Deploying infrastructure via Bicep..."
DEPLOYMENT_OUTPUT=$(az deployment group create \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file infra/main.bicep \
  --parameters \
      environment="${ENVIRONMENT}" \
      location="${LOCATION}" \
      projectName="${PROJECT_NAME}" \
      adminObjectId="${ADMIN_OBJECT_ID}" \
      adminPrincipalType="${ADMIN_PRINCIPAL_TYPE:-ServicePrincipal}" \
  --output json)

CONTAINER_APP_URL=$(echo "${DEPLOYMENT_OUTPUT}" | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['properties']['outputs']['containerAppUrl']['value'])")
echo "     Infrastructure deployed. App URL: ${CONTAINER_APP_URL}"

# 5. Build and push Docker image
echo "[5/6] Building and pushing Docker image..."
ACR_NAME=$(echo "${DEPLOYMENT_OUTPUT}" | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print(d['properties']['outputs'].get('acrName',{}).get('value',''))" 2>/dev/null || echo "")

if [ -n "${ACR_NAME}" ]; then
  az acr login --name "${ACR_NAME}"
  docker build -t "${ACR_NAME}.azurecr.io/fraud-detection:latest" .
  # Trivy scan before push
  if command -v trivy >/dev/null 2>&1; then
    echo "     Running Trivy container scan..."
    trivy image --exit-code 1 --severity HIGH,CRITICAL "${ACR_NAME}.azurecr.io/fraud-detection:latest"
  fi
  docker push "${ACR_NAME}.azurecr.io/fraud-detection:latest"
else
  echo "     Using GHCR image — skipping local build"
fi

# 6. Health check
echo "[6/6] Validating deployment..."
sleep 15
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${CONTAINER_APP_URL}/health" || echo "000")
if [ "${HTTP_STATUS}" == "200" ]; then
  echo ""
  echo "=================================================="
  echo "  Deployment SUCCESSFUL"
  echo "  API URL: ${CONTAINER_APP_URL}"
  echo "=================================================="
else
  echo "WARNING: Health check returned HTTP ${HTTP_STATUS} — check container logs"
fi
