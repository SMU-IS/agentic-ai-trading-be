output "db_endpoint" {
  description = "Endpoint of the RDS instance"
  value       = aws_db_instance.default.endpoint
}

output "db_security_group_id" {
  description = "ID of the RDS security group"
  value       = aws_security_group.rds.id
}

output "db_name" {
  description = "Name of the database"
  value       = aws_db_instance.default.db_name
}

output "db_instance_id" {
  description = "The RDS instance identifier"
  value       = aws_db_instance.default.id
}
