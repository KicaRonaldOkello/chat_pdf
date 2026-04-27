terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Configure in CI or via: terraform init -backend-config=backend.hcl
  backend "s3" {
    # bucket, key, region set by backend config (dynamodb_table optional for locking)
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "chat-pdf"
      Terraform = "true"
    }
  }
}
