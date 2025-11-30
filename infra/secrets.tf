
data "aws_secretsmanager_secret" "cognito_client_secret" {
  name = "${var.ns}/COGNITO_CLIENT_SECRET"
}



data "aws_secretsmanager_secret" "database_url" {
  name = "${var.ns}/DATABASE_URL"
}


