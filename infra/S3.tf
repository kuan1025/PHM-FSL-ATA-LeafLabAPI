variable "bucket_name" {

}

resource "aws_s3_bucket" "deployment" {
  bucket = var.bucket_name

}

#-----CORS------

variable "s3_cors_allowed_origins" {
  type = list(string)
  default = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:5173",

  ]
}

#----------------public_access--------------
resource "aws_s3_bucket_public_access_block" "deployment" {
  bucket                  = aws_s3_bucket.deployment.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}


resource "aws_s3_bucket_server_side_encryption_configuration" "deployment" {
  bucket = aws_s3_bucket.deployment.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}


resource "aws_s3_bucket_cors_configuration" "deployment" {
  bucket = aws_s3_bucket.deployment.id
  cors_rule {
    allowed_methods = ["PUT", "POST", "GET", "HEAD"]
    allowed_origins = var.s3_cors_allowed_origins
    allowed_headers = ["*"]
    expose_headers  = ["ETag", "x-amz-request-id", "x-amz-version-id"]
    max_age_seconds = 3000
  }
}

#----------------TLS------------
data "aws_iam_policy_document" "deployment_policy" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = [
      aws_s3_bucket.deployment.arn,
      "${aws_s3_bucket.deployment.arn}/*"
    ]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "deployment" {
  bucket = aws_s3_bucket.deployment.id
  policy = file("${path.module}/bucket_policy.json")
}