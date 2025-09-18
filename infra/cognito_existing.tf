########################
# Variables
########################

variable "new_pool_name" {
  type    = string
}


variable "new_domain_prefix" {
  type    = string
}

variable "ses_from_name" {
  type    = string
}

variable "ses_from_email" {
  type    = string
}

variable "ses_identity" {
  type    = string
}

data "aws_caller_identity" "current" {}




variable "callback_urls" {
  type = list(string)
  default = [

    "http://localhost/api/v1/cognito/callback",
    "http://localhost/callback",
    "http://localhost:5173/callback",

  ]
}

variable "logout_urls" {
  type = list(string)

}


# ---- Google OAuth ----
variable "google_client_id" {
  type    = string
  default = ""
}

variable "google_client_secret" {
  type      = string
  sensitive = true
  default   = ""
}

########################
# New Cognito User Pool
########################
resource "aws_cognito_user_pool" "new" {
  name                = var.new_pool_name
  deletion_protection = "INACTIVE"


  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF"

  email_configuration {
    email_sending_account  = "DEVELOPER"
    from_email_address     = "${var.ses_from_name} <${var.ses_from_email}>"
    reply_to_email_address = var.ses_from_email
    source_arn             = "arn:aws:ses:${var.region}:${data.aws_caller_identity.current.account_id}:identity/${var.ses_identity}"
  }


  schema {
    attribute_data_type = "String"
    name                = "email"
    required            = true
    mutable             = true
  }

  tags = var.common_tags
}

########################
# Google IdP
########################
resource "aws_cognito_identity_provider" "google_new" {
  user_pool_id  = aws_cognito_user_pool.new.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    authorize_scopes = "openid email profile"
    client_id        = var.google_client_id
    client_secret    = var.google_client_secret
    authorize_url    = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url        = "https://www.googleapis.com/oauth2/v4/token"
    oidc_issuer      = "https://accounts.google.com"
  }

  attribute_mapping = {
    email = "email"
  }
}

########################
########################
resource "aws_cognito_user_pool_client" "new" {
  name                                 = "${var.new_pool_name}-client"
  user_pool_id                         = aws_cognito_user_pool.new.id
  generate_secret                      = true
  supported_identity_providers         = ["COGNITO", "Google"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  prevent_user_existence_errors        = "ENABLED"

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 5
}

########################
# Hosted UI Domain
########################
resource "aws_cognito_user_pool_domain" "new" {
  domain       = var.new_domain_prefix
  user_pool_id = aws_cognito_user_pool.new.id
}

########################
# SSM Parameters
########################
locals {
  cognito_domain_url = "https://${aws_cognito_user_pool_domain.new.domain}.auth.${var.region}.amazoncognito.com"
}

resource "aws_ssm_parameter" "cognito_user_pool_id" {
  name      = "${var.ns}/COGNITO_USER_POOL_ID"
  type      = "String"
  value     = aws_cognito_user_pool.new.id
  overwrite = true
  tags      = var.common_tags
}

resource "aws_ssm_parameter" "cognito_client_id" {
  name      = "${var.ns}/COGNITO_CLIENT_ID"
  type      = "String"
  value     = aws_cognito_user_pool_client.new.id
  overwrite = true
  tags      = var.common_tags
}

resource "aws_ssm_parameter" "cognito_domain" {
  name      = "${var.ns}/COGNITO_DOMAIN"
  type      = "String"
  value     = local.cognito_domain_url
  overwrite = true
  tags      = var.common_tags
}

resource "aws_ssm_parameter" "cognito_redirect_uri" {
  name      = "${var.ns}/COGNITO_REDIRECT_URI"
  type      = "String"
  value     = element(var.callback_urls, 0)
  overwrite = true
  tags      = var.common_tags
}

resource "aws_ssm_parameter" "cognito_logout_uri" {
  name      = "${var.ns}/COGNITO_LOGOUT_REDIRECT_URI"
  type      = "String"
  value     = element(var.logout_urls, 0)
  overwrite = true
  tags      = var.common_tags
}

########################
# Outputs
########################
output "new_user_pool_id" {
  value = aws_cognito_user_pool.new.id
}

output "new_client_id" {
  value = aws_cognito_user_pool_client.new.id
}

output "new_domain_url" {
  value = local.cognito_domain_url
}
