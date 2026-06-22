#!/usr/bin/env bash
# Run once manually before the first Terraform deploy.
set -euo pipefail

RESOURCE_GROUP="rg-tfstate-loan"
STORAGE_ACCOUNT="stloanunderwritingtf"
CONTAINER="tfstate"
LOCATION="${1:-eastus}"

echo "Creating Terraform remote backend..."

az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags managed_by=terraform project=loan-underwriting \
  --output none

az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --output none

az storage container create \
  --name "$CONTAINER" \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login \
  --output none

echo ""
echo "Backend ready. Add ACR_LOGIN_SERVER secret after first terraform apply:"
echo "  gh secret set ACR_LOGIN_SERVER --body \"\$(terraform output -raw acr_login_server)\" --repo anoopkum/enterprise-ai-agents"
