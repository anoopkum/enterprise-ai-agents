variable "account_name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }
variable "key_vault_id" { type = string }
variable "is_production" { type = bool }

variable "chat_deployment_name" {
  description = "Deployment name the app calls at runtime (AZURE_OPENAI_DEPLOYMENT). Must match src/config.py."
  type        = string
  default     = "gpt-4o"
}
variable "chat_model_name" {
  description = "Azure OpenAI chat model family."
  type        = string
  default     = "gpt-4o"
}
variable "chat_model_version" {
  description = "Chat model version. gpt-4.1's 2025-04-14 is deprecating for NEW deployments in some subscriptions; gpt-4o 2024-11-20 is stable GA. Verify region/subscription availability before changing."
  type        = string
  default     = "2024-11-20"
}
variable "embed_deployment_name" {
  type    = string
  default = "text-embedding-3-large"
}
variable "embed_version" {
  type    = string
  default = "1"
}
