# =============================================================================
# AWS WAF v2 Web ACL for CloudFront
# Note: CloudFront WAF must be created in us-east-1
# =============================================================================

resource "aws_wafv2_web_acl" "api_waf" {
  provider = aws.us_east_1
  name     = "${var.cluster_name}-api-waf"
  scope    = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # 0. Bypass Rule for Health Checks (Priority 0 - highest)
  rule {
    name     = "Allow-Health-Check"
    priority = 0

    action {
      allow {}
    }

    statement {
      regex_match_statement {
        regex_string = "^/api/v1/.*/healthcheck$"
        field_to_match {
          uri_path {}
        }
        text_transformation {
          priority = 0
          type     = "NONE"
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.cluster_name}-waf-healthcheck"
      sampled_requests_enabled   = true
    }
  }

  # 1. AWS Managed Core Rule Set (OWASP Top 10) - $1.00/mo
  rule {
    name     = "AWS-AWSManagedRulesCommonRuleSet"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.cluster_name}-waf-core"
      sampled_requests_enabled   = true
    }
  }

  # 2. IP Reputation List (Known malicious IPs) - $1.00/mo
  rule {
    name     = "AWS-AWSManagedRulesAmazonIpReputationList"
    priority = 20

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAmazonIpReputationList"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.cluster_name}-waf-ip-rep"
      sampled_requests_enabled   = true
    }
  }

  # 3. Known Bad Inputs (Log4j, etc.) - $1.00/mo
  rule {
    name     = "AWS-AWSManagedRulesKnownBadInputsRuleSet"
    priority = 30

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.cluster_name}-waf-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # 4. Rate Limiting (Prevent brute force/DDoS) - Free (included in base cost)
  rule {
    name     = "Rate-Limit-500"
    priority = 40

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 500
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.cluster_name}-waf-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.cluster_name}-api-waf-total"
    sampled_requests_enabled   = true
  }

  tags = {
    Environment = var.environment
  }
}

# =============================================================================
# WAF Logging Configuration (S3)
# Note: Bucket name MUST start with 'aws-waf-logs-'
# =============================================================================

resource "aws_s3_bucket" "waf_logs" {
  provider = aws.us_east_1
  bucket   = "aws-waf-logs-${var.cluster_name}-${var.environment}"

  # Allow WAF to be deleted if bucket is not empty (careful in prod)
  force_destroy = true

  tags = {
    Name        = "WAF Logs"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "waf_logs_lifecycle" {
  provider = aws.us_east_1
  bucket   = aws_s3_bucket.waf_logs.id

  rule {
    id     = "expire-logs"
    status = "Enabled"

    filter {}

    expiration {
      days = 30 # Keep logs for 30 days to control costs
    }
  }
}

resource "aws_wafv2_web_acl_logging_configuration" "api_waf_logging" {
  provider                = aws.us_east_1
  log_destination_configs = [aws_s3_bucket.waf_logs.arn]
  resource_arn            = aws_wafv2_web_acl.api_waf.arn

  # Optional: Filter logs to only save blocked requests to save S3 costs
  # logging_filter {
  #   default_behavior = "KEEP"
  #   filter {
  #     behavior = "KEEP"
  #     condition {
  #       action_condition {
  #         action = "BLOCK"
  #       }
  #     }
  #     requirement = "MEETS_ANY"
  #   }
  # }
}
