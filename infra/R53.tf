variable "r53_zone_id" {
  type        = string
  description = ""
  default     = ""
}

locals {
  leaflab_fqdn    = ""
  apigw_exec_name = ""
}



# A (Alias)  point to  execute-api

resource "aws_route53_record" "leaflab_api_alias" {
  zone_id = var.r53_zone_id
  name    = local.leaflab_fqdn
  type    = "A"

  alias {
    name                   = local.apigw_exec_name
    zone_id                = ""
    evaluate_target_health = false
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}