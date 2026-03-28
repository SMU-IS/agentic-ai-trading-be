output "amplify_app_id" {
  description = "ID of the Amplify app"
  value       = aws_amplify_app.trading_frontend.id
}

output "amplify_default_domain" {
  description = "Default domain of the Amplify app"
  value       = aws_amplify_app.trading_frontend.default_domain
}

output "custom_domain_name" {
  description = "The custom domain associated with the Amplify app"
  value       = aws_amplify_domain_association.example.domain_name
}
