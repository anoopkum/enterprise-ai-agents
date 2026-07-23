variable "name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }
variable "admin_object_id" {
  type      = string
  sensitive = true
}
variable "tenant_id" { type = string }
variable "is_production" { type = bool }
