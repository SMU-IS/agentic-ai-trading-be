output "amplify_app_id" {
  value = aws_amplify_app.trading_frontend.id
}

output "amplify_default_domain" {
  value = aws_amplify_app.trading_frontend.default_domain
}
