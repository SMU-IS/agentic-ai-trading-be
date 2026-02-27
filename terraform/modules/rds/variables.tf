variable "cluster_name" { type = string }
variable "vpc_id" { type = string }
variable "vpc_cidr_block" { type = string }
variable "private_subnets" { type = list(string) }
variable "db_name" { type = string }
variable "db_username" { type = string }
variable "db_password" { type = string }
variable "environment" { type = string }
