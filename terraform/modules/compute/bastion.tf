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

# Launch Template for Bastion
resource "aws_launch_template" "bastion" {
  name_prefix   = "${var.cluster_name}-bastion-"
  image_id      = data.aws_ami.al2023.id
  instance_type = "t4g.nano" # Default, overridden by ASG mixed instances policy

  vpc_security_group_ids = [aws_security_group.bastion_sg.id]

  iam_instance_profile {
    name = aws_iam_instance_profile.bastion_profile.name
  }

  monitoring {
    enabled = false
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name        = "${var.cluster_name}-bastion"
      Environment = var.environment
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Auto Scaling Group for Bastion (1 instance, Mixed Instance Policy for Spot)
resource "aws_autoscaling_group" "bastion" {
  name                = "${var.cluster_name}-bastion-asg"
  vpc_zone_identifier = var.subnet_ids
  desired_capacity    = 1
  max_size            = 1
  min_size            = 1

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0 # 100% Spot
      spot_allocation_strategy                 = "price-capacity-optimized"
    }

    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.bastion.id
        version            = "$Latest"
      }

      override { instance_type = "t4g.nano" }
      override { instance_type = "t4g.micro" }
      override { instance_type = "t4g.small" }
    }
  }

  tag {
    key                 = "Name"
    value               = "${var.cluster_name}-bastion"
    propagate_at_launch = true
  }

  tag {
    key                 = "Environment"
    value               = var.environment
    propagate_at_launch = true
  }
}
