
data "aws_secretsmanager_secret" "cognito_client_secret" {
  name = "${var.ns}/COGNITO_CLIENT_SECRET"
}

resource "aws_secretsmanager_secret_version" "cognito_client_secret_v" {
  secret_id     = data.aws_secretsmanager_secret.cognito_client_secret.id
  secret_string = aws_cognito_user_pool_client.new.client_secret
  depends_on    = [aws_cognito_user_pool_client.new]
  lifecycle {
    prevent_destroy = true
  }
}

data "aws_secretsmanager_secret" "database_url" {
  name = "${var.ns}/DATABASE_URL"
}

resource "aws_secretsmanager_secret_version" "database_url_v" {
  secret_id     = data.aws_secretsmanager_secret.database_url.id
  secret_string = var.database_url
  lifecycle {
    prevent_destroy = true
  }
}
