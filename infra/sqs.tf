########################
# SQS Queues for job routing
########################

locals {
  queue_tags = merge(var.common_tags, {
    service = "leaflab-jobs"
  })
}

resource "aws_sqs_queue" "sam_dlq" {
  name                        = "${var.sam_queue_name}-dlq"
  message_retention_seconds   = 1209600
  sqs_managed_sse_enabled     = true
  content_based_deduplication = false
  fifo_queue                  = false
  tags                        = local.queue_tags
}

resource "aws_sqs_queue" "grabcut_dlq" {
  name                        = "${var.grabcut_queue_name}-dlq"
  message_retention_seconds   = 1209600
  sqs_managed_sse_enabled     = true
  content_based_deduplication = false
  fifo_queue                  = false
  tags                        = local.queue_tags
}

resource "aws_sqs_queue" "sam" {
  name                        = var.sam_queue_name
  visibility_timeout_seconds  = 300
  receive_wait_time_seconds   = 20
  message_retention_seconds   = 1209600
  delay_seconds               = 0
  sqs_managed_sse_enabled     = true
  content_based_deduplication = false
  fifo_queue                  = false
  tags                        = local.queue_tags
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.sam_dlq.arn
    maxReceiveCount     = 2
  })
}

resource "aws_sqs_queue" "grabcut" {
  name                        = var.grabcut_queue_name
  visibility_timeout_seconds  = 300
  receive_wait_time_seconds   = 20
  message_retention_seconds   = 1209600
  delay_seconds               = 0
  sqs_managed_sse_enabled     = true
  content_based_deduplication = false
  fifo_queue                  = false
  tags                        = local.queue_tags
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.grabcut_dlq.arn
    maxReceiveCount     = 2
  })
}


########################
# SSM Parameters
########################

resource "aws_ssm_parameter" "sam_queue_url" {
  name      = "${var.ns}/SQS_SAM_QUEUE_URL"
  type      = "String"
  value     = aws_sqs_queue.sam.url
  overwrite = true
  tags      = var.common_tags
  count     = var.manage_ssm ? 1 : 0
}

resource "aws_ssm_parameter" "grabcut_queue_url" {
  name      = "${var.ns}/SQS_GRABCUT_QUEUE_URL"
  type      = "String"
  value     = aws_sqs_queue.grabcut.url
  overwrite = true
  tags      = var.common_tags
  count     = var.manage_ssm ? 1 : 0
}

resource "aws_ssm_parameter" "sam_dlq_queue_url" {
  name      = "${var.ns}/SQS_SAM_DLQ_URL"
  type      = "String"
  value     = aws_sqs_queue.sam_dlq.url
  overwrite = true
  tags      = var.common_tags
  count     = var.manage_ssm ? 1 : 0
}

resource "aws_ssm_parameter" "grabcut_dlq_queue_url" {
  name      = "${var.ns}/SQS_GRABCUT_DLQ_URL"
  type      = "String"
  value     = aws_sqs_queue.grabcut_dlq.url
  overwrite = true
  tags      = var.common_tags
  count     = var.manage_ssm ? 1 : 0
}


########################
# Outputs
########################

output "sam_queue_url" {
  value = aws_sqs_queue.sam.url
}

output "grabcut_queue_url" {
  value = aws_sqs_queue.grabcut.url
}

output "sam_dlq_queue_url" {
  value = aws_sqs_queue.sam_dlq.url
}

output "grabcut_dlq_queue_url" {
  value = aws_sqs_queue.grabcut_dlq.url
}
