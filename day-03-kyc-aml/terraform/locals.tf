locals {
  prefix        = "${var.project_name}-${var.environment}"
  is_production = var.environment == "prod"
  is_staging    = var.environment == "staging"

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
    day         = "03"
    agent       = "kyc-aml-compliance"
    cost_center = local.is_production ? "prod-banking" : "dev-test"
    repo        = "anoopkum/enterprise-ai-agents"
  }
}
