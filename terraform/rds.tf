resource "random_password" "db" {
  length  = 24
  special = false
}

resource "aws_db_subnet_group" "main" {
  name = "${local.name}-db"
  subnet_ids = aws_subnet.private[*].id
  tags = { Name = "${local.name}-db-subnet" }
}

resource "aws_db_instance" "main" {
  identifier = "${local.name}-pg"
  engine     = "postgres"
  engine_version = "16"
  instance_class   = "db.t4g.small"
  allocated_storage   = 20
  max_allocated_storage = 100
  storage_type = "gp3"

  db_name  = "chatpdf"
  username = "chatpdf"
  password = random_password.db.result

  db_subnet_group_name = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  skip_final_snapshot     = true
  backup_retention_period  = 1
  apply_immediately = true

  tags = { Name = "${local.name}-rds" }
}
