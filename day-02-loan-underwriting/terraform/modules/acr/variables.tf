variable "name"                { type = string }
variable "resource_group_name" { type = string }
variable "location"            { type = string }
variable "tags"                { type = map(string) }
variable "is_production"       { type = bool }
variable "secondary_location"  { type = string; default = "westus" }
variable "pull_principal_ids"  { type = list(string); default = [] }
