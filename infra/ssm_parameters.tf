locals { p = var.ns }

# aws_ssm_parameter must be imported if it already exists!!!

resource "aws_ssm_parameter" "s3_bucket" {
  name      = "${local.p}/S3_BUCKET"
  type      = "String"
  value     = var.s3_bucket
  overwrite = true
  tags      = var.common_tags
}

resource "aws_ssm_parameter" "sam_model_type" {
  name      = "${local.p}/SAM_MODEL_TYPE"
  type      = "String"
  value     = var.sam_model_type
  overwrite = true
  tags      = var.common_tags
}

resource "aws_ssm_parameter" "sam_checkpoint" {
  name      = "${local.p}/SAM_CHECKPOINT"
  type      = "String"
  value     = var.sam_checkpoint
  overwrite = true
  tags      = var.common_tags
}

resource "aws_ssm_parameter" "version_prefix" {
  name      = "${local.p}/VERSION"
  type      = "String"
  value     = var.version_prefix
  overwrite = true
  tags      = var.common_tags
}

resource "aws_ssm_parameter" "cors_allow_origins" {
  name      = "${local.p}/CORS_ALLOW_ORIGINS"
  type      = "String"
  value     = var.cors_allow_origins
  overwrite = true
  tags      = var.common_tags
}


