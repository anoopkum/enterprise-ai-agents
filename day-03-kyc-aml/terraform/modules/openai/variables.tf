variable "account_name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }
variable "key_vault_id" { type = string }
variable "is_production" { type = bool }

variable "chat_deployment_name" {
  type    = string
  default = "gpt-4.1"
}
variable "gpt41_version" {
  description = "GPT-4.1 model version. Check region availability before changing."
  type        = string
  default     = "2025-04-14"
}
variable "embed_deployment_name" {
  type    = string
  default = "text-embedding-3-large"
}
variable "embed_version" {
  type    = string
  default = "1"
}
