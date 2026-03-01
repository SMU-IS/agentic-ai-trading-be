# Amplify App
resource "aws_amplify_app" "trading_frontend" {
  name       = "${var.cluster_name}-frontend"
  repository = var.amplify_repository
  access_token = var.amplify_access_token

  build_spec = <<-EOT
    version: 1
    frontend:
      phases:
        preBuild:
          commands:
            - npm ci
        build:
          commands:
            - npm run build
      artifacts:
        baseDirectory: build
        files:
          - '**/*'
      cache:
        paths:
          - node_modules/**/*
  EOT

  environment_variables = {
    ENV = var.environment
  }

  tags = {
    Environment = var.environment
  }
}

# Amplify Branch
resource "aws_amplify_branch" "main" {
  app_id = aws_amplify_app.trading_frontend.id

  branch_name = "main"

  tags = {
    Environment = var.environment
  }
}
