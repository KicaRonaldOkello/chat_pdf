variable "aws_region" {
  type        = string
  description = "Region for main resources (ALB, ECS, RDS, EC2, ECR)."
  default     = "us-east-1"
}

variable "project" {
  type        = string
  description = "Name prefix for resources."
  default     = "chat-pdf"
}

# --- Phase: first apply = false, second apply = true after ECR image push
variable "create_backend" {
  type        = bool
  default     = false
  description = "If true, create ALB, ECS, and CloudFront /api->ALB. If false, only ECR+VPC+RDS+data EC2+frontend S3+CloudFront (static only)."
}

# --- Existing documents bucket (you created outside this module)
variable "existing_documents_s3_bucket" {
  type        = string
  description = "S3 bucket name for PDFs (read/write by the API task role)."
}

variable "s3_key_prefix" {
  type        = string
  default     = "documents"
  description = "S3 key prefix for documents (S3_KEY_PREFIX for the API)."
}

# --- ECR / ECS
variable "app_image" {
  type        = string
  default     = ""
  description = "ECR image URI:tag. Required when create_backend=true (enforced in ecs task precondition)."
}

# --- App env (sensitive in UI; still stored in state)
variable "clerk_jwks_url" {
  type        = string
  default     = ""
  description = "Clerk JWKS URL (required when create_backend = true)."
}

variable "clerk_issuer" {
  type        = string
  default     = ""
  description = "Clerk issuer, e.g. https://<instance>.clerk.accounts.dev (required when create_backend = true)."
}

variable "clerk_jwt_audience" {
  type    = string
  default = ""
}

variable "openrouter_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

# --- Data EC2
variable "data_instance_type" {
  type        = string
  description = "Ollama + Qdrant host (e.g. m6i.2xlarge for 32 GiB RAM)."
  default     = "m6i.2xlarge"
}

variable "ollama_models" {
  type        = list(string)
  default     = ["phi4-mini", "gemma4:e4b", "nomic-embed-text"]
  description = "Models to pull on first boot (takes a long time)."
}

# --- Fargate
variable "fargate_cpu" {
  type    = number
  default = 4096
}

variable "fargate_memory" {
  type    = number
  default = 8192
}

# --- GitHub OIDC
variable "github_owner" {
  type        = string
  description = "GitHub org or user who owns the repo (for IAM trust)."
  default     = ""
}

variable "github_repo" {
  type        = string
  description = "Repository name only (e.g. chat_pdf)."
  default     = ""
}

# --- CORS (auto-set in outputs when create_backend; override if needed)
variable "cors_extra_origins" {
  type        = string
  default     = ""
  description = "Optional comma-separated extra origins in addition to CloudFront URL (e.g. custom domain)."
}

# --- State bootstrap (for reference; actual backend passed to terraform init)
variable "terraform_state_bucket" {
  type        = string
  description = "S3 bucket for remote state (document only; use backend config for init)."
  default     = ""
}
