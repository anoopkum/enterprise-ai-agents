variable "hub_name"            { type = string }
variable "project_name"        { type = string }
variable "resource_group_name" { type = string }
variable "location"            { type = string }
variable "tags"                { type = map(string) }
variable "key_vault_id"        { type = string }
variable "openai_id"           { type = string }
variable "is_production"       { type = bool }
