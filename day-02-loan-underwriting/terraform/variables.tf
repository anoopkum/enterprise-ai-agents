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
  description = "Azure AD Object ID for Key Vault admin (CI service principal or developer)"
  type        = string
  sensitive   = true
}

variable "container_image" {
  description = "Full container image URI — ghcr.io/anoopkum/enterprise-ai-agents/loan-underwriting:<tag>"
  type        = string
  default     = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
}
