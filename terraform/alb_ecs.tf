resource "aws_ecs_cluster" "main" {
  name = "${local.name}-cluster"
}

# --- Public ALB (CloudFront fetches this origin; browser never hits ALB host directly)
resource "aws_lb" "app" {
  count              = var.create_backend ? 1 : 0
  name = "${local.name}-alb"
  load_balancer_type = "application"
  internal = false
  security_groups    = [aws_security_group.alb.id]
  subnets = aws_subnet.public[*].id

  tags = { Name = "${local.name}-alb" }
}

resource "aws_lb_target_group" "app" {
  count = var.create_backend ? 1 : 0
  name = "${local.name}-tg"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id
  deregistration_delay = 5

  health_check {
    enabled  = true
    path     = "/docs"
    protocol = "HTTP"
    matcher  = "200"
    interval = 15
  }
  tags = { Name = "${local.name}-tg" }
}

resource "aws_lb_listener" "http" {
  count = var.create_backend ? 1 : 0
  load_balancer_arn = aws_lb.app[0].arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app[0].arn
  }
}

locals {
  db_url = format(
    "postgresql://%s:%s@%s:%s/%s?sslmode=require",
    aws_db_instance.main.username,
    random_password.db.result,
    aws_db_instance.main.address,
    tostring(aws_db_instance.main.port),
    aws_db_instance.main.db_name
  )
  ollama_url  = "http://${aws_instance.data.private_ip}:11434"
  qdrant_url  = "http://${aws_instance.data.private_ip}:6333"
  public_origin  = "https://${aws_cloudfront_distribution.app.domain_name}"
  extra_cors   = [for s in split(",", var.cors_extra_origins) : trimspace(s) if trimspace(s) != ""]
  cors_allow_orig = join(",", concat([local.public_origin], local.extra_cors))
  app_env = concat(
    [
      { name = "DATABASE_URL", value = local.db_url },
      { name = "S3_BUCKET", value = var.existing_documents_s3_bucket },
      { name = "S3_KEY_PREFIX", value = var.s3_key_prefix },
      { name = "OLLAMA_BASE_URL", value = local.ollama_url },
      { name = "QDRANT_URL", value = local.qdrant_url },
      { name = "CORS_ALLOW_ORIGINS", value = local.cors_allow_orig },
      { name = "CLERK_JWKS_URL", value = var.clerk_jwks_url },
      { name = "CLERK_ISSUER", value = var.clerk_issuer },
      { name = "AWS_REGION", value = var.aws_region },
    ],
    var.clerk_jwt_audience != "" ? [{ name = "CLERK_JWT_AUDIENCE", value = var.clerk_jwt_audience }] : [],
    var.openrouter_api_key != "" ? [{ name = "OPENROUTER_API_KEY", value = var.openrouter_api_key }] : []
  )
}

resource "aws_ecs_task_definition" "app" {
  count = var.create_backend ? 1 : 0
  family  = "${local.name}-api"
  cpu     = tostring(var.fargate_cpu)
  memory  = tostring(var.fargate_memory)
  network_mode = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn  = aws_iam_role.ecs_exec.arn
  task_role_arn    = aws_iam_role.app_task.arn

  lifecycle {
    precondition {
      condition = (
        !var.create_backend ||
        (var.app_image != "" && var.clerk_jwks_url != "" && var.clerk_issuer != "")
      )
      error_message = "For create_backend=true, set app_image, clerk_jwks_url, and clerk_issuer."
    }
  }

  container_definitions = jsonencode([{
    name  = "api"
    image = var.app_image
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]

    environment = local.app_env

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs.name
        awslogs-region         = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

resource "aws_ecs_service" "app" {
  count    = var.create_backend ? 1 : 0
  name  = "${local.name}-api"
  cluster  = aws_ecs_cluster.main.id
  task_definition  = aws_ecs_task_definition.app[0].arn
  launch_type  = "FARGATE"
  desired_count  = 1
  health_check_grace_period_seconds  = 120
  network_configuration {
    security_groups  = [aws_security_group.ecs.id]
    subnets  = aws_subnet.private[*].id
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app[0].arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_instance.data, aws_db_instance.main, aws_lb_listener.http]
}