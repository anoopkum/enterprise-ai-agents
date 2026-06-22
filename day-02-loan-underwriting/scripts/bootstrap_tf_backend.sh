#!/usr/bin/env bash
# Run once manually before the first Terraform deploy.
# Creates the Azure Storage backend for Terraform state.
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
echo "Backend ready:"
echo "  resource_group_name  = \"$RESOURCE_GROUP\""
echo "  storage_account_name = \"$STORAGE_ACCOUNT\""
echo "  container_name       = \"$CONTAINER\""
echo "  key                  = \"loan-underwriting.tfstate\""
