output "cloudfront_id" {
  value       = aws_cloudfront_distribution.app.id
  description = "E.g. for `aws cloudfront create-invalidation --distribution-id`."
}

output "cloudfront_domain" {
  description = "Distribution domain; users open https://(this) for the SPA and /api (same host)."
  value = aws_cloudfront_distribution.app.domain_name
}

output "url" {
  value = "https://${aws_cloudfront_distribution.app.domain_name}"
}

output "s3_frontend_bucket" {
  value = aws_s3_bucket.frontend.id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "rds_address" {
  value = aws_db_instance.main.address
}

output "rds_port" {
  value = aws_db_instance.main.port
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "rds_password" {
  value     = random_password.db.result
  sensitive = true
}

output "data_plane_private_ip" {
  value       = aws_instance.data.private_ip
  description = "Ollama + Qdrant host (private). ECS tasks use this in env."
}

output "github_actions_role_arn" {
  value = local.use_github_actions_oidc ? aws_iam_role.github_actions[0].arn : "not created (set github_owner and github_repo)"
  description = "Set this in GitHub as AWS_DEPLOY_ROLE_ARN after first apply."
}

output "app_cluster_name" {
  value = aws_ecs_cluster.main.name
  description = "ECS cluster (always created) for one-off run-task, etc."
}

output "app_service_name" {
  value     = var.create_backend ? aws_ecs_service.app[0].name : "N/A"
}

output "app_task_definition_arn" {
  value     = var.create_backend ? aws_ecs_task_definition.app[0].arn : ""
  description = "Fargate task for run-task (migrations) overrides."
}

output "private_subnet_ids" {
  value = join(",", aws_subnet.private[*].id)
}

output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}
