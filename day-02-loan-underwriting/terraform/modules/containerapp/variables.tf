variable "env_name"             { type = string }
variable "app_name"             { type = string }
variable "resource_group_name"  { type = string }
variable "location"             { type = string }
variable "tags"                 { type = map(string) }
variable "key_vault_id"         { type = string }
variable "ai_foundry_endpoint"  { type = string }
variable "app_insights_conn_str" { type = string; sensitive = true }
variable "environment_name"     { type = string }
variable "container_image"      { type = string }
variable "acr_login_server"     { type = string }
variable "is_production"        { type = bool }
