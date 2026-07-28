variable "env_name" { type = string }
variable "app_name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }
variable "is_production" { type = bool }
