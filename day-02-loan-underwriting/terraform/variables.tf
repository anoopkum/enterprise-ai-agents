variable "environment" {
  description = "Deployment environment: dev | staging | prod"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod"
  }
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "project_name" {
  description = "Project identifier prefix"
  type        = string
  default     = "loan-underwriting"
}

variable "admin_object_id" {
  description = "Azure AD Object ID for Key Vault admin"
  type        = string
  sensitive   = true
}

variable "ai_foundry_endpoint" {
  description = "Azure AI Foundry project endpoint (existing hub — not managed by this Terraform)"
  type        = string
  default     = "https://oai-aihub-fraud-agent-staging.openai.azure.com"
}

variable "container_image" {
  description = "Full container image URI"
  type        = string
  default     = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
}
