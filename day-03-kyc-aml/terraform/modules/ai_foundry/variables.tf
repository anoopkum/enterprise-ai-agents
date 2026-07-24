variable "name" {
  description = "AI Foundry hub name."
  type        = string
}

variable "project_name" {
  description = "AI Foundry project name."
  type        = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "key_vault_id" {
  description = "Key Vault backing the hub (required by azurerm_ai_foundry)."
  type        = string
}

variable "storage_account_name" {
  description = "Globally-unique storage account name (3-24 lowercase alphanumeric)."
  type        = string
}

variable "is_production" {
  type    = bool
  default = false
}

variable "friendly_name" {
  description = "Display name shown in the Foundry portal."
  type        = string
  default     = "KYC/AML Compliance"
}
