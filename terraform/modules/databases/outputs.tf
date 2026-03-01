output "db_endpoint" {
  description = "Endpoint of the RDS instance"
  value       = aws_db_instance.default.endpoint
}

output "db_security_group_id" {
  description = "ID of the RDS security group"
  value       = aws_security_group.rds.id
}
