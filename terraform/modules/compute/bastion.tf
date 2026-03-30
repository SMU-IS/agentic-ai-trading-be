# =============================================================================
# Bastion Host and EC2 Instance Connect Endpoint
# =============================================================================

# Security Group for EC2 Instance Connect Endpoint
resource "aws_security_group" "eice_sg" {
  name        = "${var.cluster_name}-eice-sg"
  vpc_id      = var.vpc_id
  description = "EICE Security Group"

  egress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.cluster_name}-eice-sg"
    Environment = var.environment
  }
}

# Security Group for Bastion Host
resource "aws_security_group" "bastion_sg" {
  name        = "${var.cluster_name}-bastion-sg"
  vpc_id      = var.vpc_id
  description = "Allow SSH from EICE"

  ingress {
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.eice_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.cluster_name}-bastion-sg"
    Environment = var.environment
  }
}

# EC2 Instance Connect Endpoint
resource "aws_ec2_instance_connect_endpoint" "this" {
  subnet_id          = var.subnet_ids[0]
  security_group_ids = [aws_security_group.eice_sg.id]

  tags = {
    Name        = "${var.cluster_name}-eice"
    Environment = var.environment
  }
}

# IAM Role for Bastion (SSM Access)
resource "aws_iam_role" "bastion_role" {
  name = "${var.cluster_name}-bastion-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.cluster_name}-bastion-role"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "bastion_ssm" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  role       = aws_iam_role.bastion_role.name
}

resource "aws_iam_instance_profile" "bastion_profile" {
  name = "${var.cluster_name}-bastion-profile"
  role = aws_iam_role.bastion_role.name

  tags = {
    Name        = "${var.cluster_name}-bastion-profile"
    Environment = var.environment
  }
}

# Small Bastion Instance (using AL2023 ARM64 to match other infrastructure)
resource "aws_instance" "bastion" {
  ami                  = data.aws_ami.al2023.id
  instance_type        = "t4g.nano"
  subnet_id            = var.subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.bastion_sg.id]
  iam_instance_profile = aws_iam_instance_profile.bastion_profile.name

  # No key_name needed with EICE/SSM
  
  # Ensure the instance has the EC2 Instance Connect software (installed by default on AL2023)
  
  tags = {
    Name        = "${var.cluster_name}-bastion"
    Environment = var.environment
  }
}
