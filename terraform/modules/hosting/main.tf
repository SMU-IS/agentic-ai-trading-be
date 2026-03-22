# Amplify App
resource "aws_amplify_app" "trading_frontend" {
  name         = "${var.cluster_name}-frontend"
  repository   = var.amplify_repository
  access_token = var.amplify_access_token
  platform     = "WEB_COMPUTE"

  build_spec = <<-EOT
    version: 1
    frontend:
      phases:
        preBuild:
          commands:
            - npm ci --cache .npm --prefer-offline
        build:
          commands:
            - npm run build
      artifacts:
        baseDirectory: .next
        files:
          - '**/*'
      cache:
        paths:
          - .next/cache/**/*
          - .npm/**/*
  EOT

  custom_rule {
    source = "/<*>"
    status = "404"
    target = "/index.html"
  }

  environment_variables = {
    ENV                         = var.environment
    NEXT_PUBLIC_BASE_API_URL    = var.base_api_url
    NEXT_PUBLIC_CHAT_API_URL    = var.chat_api_url
    NEXT_PUBLIC_FINNHUB_API_KEY = var.finnhub_api_key
    NEXT_PUBLIC_LOGOKIT_API_KEY = var.logokit_api_key
    NEXT_PUBLIC_NOTIF_API_URL   = var.notif_api_url
    NEXT_PUBLIC_THREAD_API_URL  = var.thread_api_url
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

# CloudFront Distribution pointing to Amplify
resource "aws_cloudfront_distribution" "amplify_cdn" {
  origin {
    domain_name = "${aws_amplify_branch.main.branch_name}.${aws_amplify_app.trading_frontend.default_domain}"
    origin_id   = "Amplify-Origin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled         = true
  is_ipv6_enabled = true
  comment         = "CloudFront for Amplify ${var.environment}"
  price_class     = "PriceClass_100" # cheapest (North America and Europe)

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "Amplify-Origin"

    forwarded_values {
      query_string = true
      cookies {
        forward = "all"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_cloudfront_distribution" "kong_api" {
  origin {
    domain_name = "k8s-default-kongkong-f56d41ad22-b89d49cb73c55092.elb.us-east-1.amazonaws.com"
    origin_id   = "Kong-Origin"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }
  enabled         = true
  is_ipv6_enabled = true
  comment         = "CloudFront for Kong API ${var.environment}"
  price_class     = "PriceClass_100"

  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "Kong-Origin"
    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Content-Type", "Origin"]
      cookies {
        forward = "all"
      }
    }
    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Environment = var.environment
  }
}
