# ECS task execution: pull ECR, logs
resource "aws_iam_role" "ecs_exec" {
  name = "${local.name}-ecs-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
  tags = { Name = "${local.name}-ecs-exec" }
}

resource "aws_iam_role_policy_attachment" "exec_managed" {
  role       = aws_iam_role.ecs_exec.id
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# App task: S3 documents bucket, optional
resource "aws_iam_role" "app_task" {
  name = "${local.name}-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
  tags = { Name = "${local.name}-task" }
}

data "aws_s3_bucket" "documents" {
  bucket = var.existing_documents_s3_bucket
}

data "aws_iam_policy_document" "task_s3" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:AbortMultipartUpload", "s3:ListBucketMultipartUploads", "s3:PutObjectAcl", "s3:DeleteObject"
    ]
    # Restrict to the existing bucket; narrow your prefix if you use a dedicated prefix
    resources = [data.aws_s3_bucket.documents.arn, "${data.aws_s3_bucket.documents.arn}/*"]
  }
}

resource "aws_iam_role_policy" "s3" {
  name   = "s3-docs"
  role   = aws_iam_role.app_task.id
  policy = data.aws_iam_policy_document.task_s3.json
}

resource "aws_cloudwatch_log_group" "ecs" {
  name = "/ecs/${local.name}/api"
  # Short retention for short-lived stack
  retention_in_days = 7
}
