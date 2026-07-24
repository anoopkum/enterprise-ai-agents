variable "name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }
variable "key_vault_id" { type = string }
variable "is_production" { type = bool }

variable "sku" {
  description = "basic | standard | standard2 ... . 'basic' is enough for a demo KB."
  type        = string
  default     = "basic"
}
