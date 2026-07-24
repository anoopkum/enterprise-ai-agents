variable "name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "tags" { type = map(string) }
variable "admin_object_id" {
  type      = string
  sensitive = true
}
variable "deployer_object_id" {
  description = "Object ID of the principal running terraform apply (CI SP or local user). Gets Secrets Officer so it can write secrets into this RBAC vault."
  type        = string
  sensitive   = true
}
variable "tenant_id" { type = string }
variable "is_production" { type = bool }
