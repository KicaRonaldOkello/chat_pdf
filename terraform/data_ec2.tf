data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_iam_role" "data_ec2" {
  name = "${local.name}-data-ec2"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
  tags = { Name = "${local.name}-data-ec2-role" }
}

resource "aws_iam_instance_profile" "data_ec2" {
  name = "${local.name}-data-ec2"
  role = aws_iam_role.data_ec2.name
}

# Optional: SSM for debugging (no SSH key)
resource "aws_iam_role_policy_attachment" "data_ssm" {
  role = aws_iam_role.data_ec2.id
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_instance" "data" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.data_instance_type
  subnet_id              = aws_subnet.private[0].id
  vpc_security_group_ids = [aws_security_group.data.id]
  iam_instance_profile   = aws_iam_instance_profile.data_ec2.name

  user_data = base64encode(templatefile("${path.module}/templates/data_user_data.sh", {
    ollama_models = var.ollama_models
  }))

  root_block_device {
    volume_size = 100
    volume_type = "gp3"
  }

  tags = {
    Name = "${local.name}-ollama-qdrant"
  }

  depends_on = [aws_nat_gateway.main]
}
