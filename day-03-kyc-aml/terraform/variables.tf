variable "environment" {
  description = "Deployment environment: dev | staging | prod"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod"
  }
}

variable "subscription_id" {
  description = "Azure subscription ID (azurerm 4.x requires this explicitly). Set via TF_VAR_subscription_id / ARM_SUBSCRIPTION_ID."
  type        = string
  default     = ""
}

variable "location" {
  description = "Azure region. GPT-4.1 + Document Intelligence must be available here."
  type        = string
  default     = "swedencentral"
}

variable "project_name" {
  description = "Project identifier prefix"
  type        = string
  default     = "kyc-aml"
}

variable "admin_object_id" {
  description = "Azure AD Object ID for Key Vault admin"
  type        = string
  sensitive   = true
}

variable "doc_intelligence_sku" {
  description = "Document Intelligence SKU: S0 (standard) or F0 (free tier)"
  type        = string
  default     = "S0"
}

variable "search_sku" {
  description = "Azure AI Search SKU: basic | standard"
  type        = string
  default     = "basic"
}

# Neo4j Aura connection — provisioned in the Aura console, stored in Key Vault.
# Pass via TF_VAR_neo4j_uri / TF_VAR_neo4j_password (never commit these).
variable "neo4j_uri" {
  description = "Neo4j Aura connection URI, e.g. neo4j+s://<id>.databases.neo4j.io"
  type        = string
  default     = ""
}

variable "neo4j_password" {
  description = "Neo4j Aura password"
  type        = string
  default     = ""
  sensitive   = true
}
