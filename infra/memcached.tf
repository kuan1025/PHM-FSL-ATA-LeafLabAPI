########################
# Variables
########################

variable "memcached_cluster_id" {
  type    = string
}

variable "memcached_engine_version" {
  type    = string
  default = "1.6.22"
}

variable "memcached_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "memcached_num_nodes" {
  type    = number
  default = 1
}

variable "memcached_port" {
  type    = number
  default = 11211
}

variable "memcached_parameter_group" {
  type    = string
  default = "default.memcached1.6"
}

variable "memcached_az_mode" {
  type    = string
  default = "single-az"
}

variable "memcached_availability_zone" {
  type    = string
  default = "ap-southeast-2b"
}

variable "memcached_maintenance_window" {
  type    = string
  default = "tue:16:30-tue:17:30"
}

variable "memcached_security_group_ids" {
  type = list(string)
}

variable "memcached_subnet_group_name" {
  type    = string
}

variable "memcached_subnet_ids" {
  type = list(string)
}



########################
# Subnet Group
########################


########################
# Memcached Cluster（Blueprint）
########################
resource "aws_elasticache_cluster" "memcached" {
  cluster_id                 = var.memcached_cluster_id
  engine                     = "memcached"
  engine_version             = var.memcached_engine_version
  node_type                  = var.memcached_node_type
  num_cache_nodes            = var.memcached_num_nodes
  port                       = var.memcached_port
  parameter_group_name       = var.memcached_parameter_group
  az_mode                    = var.memcached_az_mode
  availability_zone          = var.memcached_availability_zone
  maintenance_window         = var.memcached_maintenance_window
  security_group_ids         = var.memcached_security_group_ids
  subnet_group_name          = "cab432-subnets"
  network_type               = "ipv4"
  ip_discovery               = "ipv4"
  transit_encryption_enabled = false
  tags                       = var.common_tags
}

########################
# Compose CACHE_URL
########################
locals {
  node_hosts = [for n in aws_elasticache_cluster.memcached.cache_nodes : split(":", n.address)[0]]
  node_host  = local.node_hosts[0]
  cache_port = aws_elasticache_cluster.memcached.port
  cache_url  = "memcached://${local.node_host}:${local.cache_port}"
}




########################
# SSM Parameter: /n11233885/CACHE_URL
########################
resource "aws_ssm_parameter" "cache_url" {
  name      = "${var.ns}/CACHE_URL"
  type      = "String"
  value     = local.cache_url
  overwrite = true
  tags      = var.common_tags
  count     = var.manage_ssm ? 1 : 0
}

########################
# Outputs
########################
output "memcached_cache_url" {
  value = local.cache_url
}

output "memcached_configuration_endpoint" {
  value = try(aws_elasticache_cluster.memcached.configuration_endpoint, null)
}