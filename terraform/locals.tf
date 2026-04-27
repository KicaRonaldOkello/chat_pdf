locals {
  name         = var.project
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
  use_github_actions_oidc = var.github_owner != "" && var.github_repo != ""
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
