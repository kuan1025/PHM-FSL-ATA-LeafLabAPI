########################
# EventBridge routing for job queues
########################

locals {
  event_bridge_name = "leaflab-jobs"
  event_source      = "leaflab.api"
  event_detail_type = "JobRequested"
  tags              = var.common_tags
}

resource "aws_cloudwatch_event_bus" "jobs" {
  name = local.event_bridge_name
  tags = var.common_tags
}

# Rule for SAM jobs
resource "aws_cloudwatch_event_rule" "sam" {
  name           = "${var.sam_queue_name}-rule"
  description    = "Route SAM segmentation jobs to SAM SQS queue"
  event_bus_name = aws_cloudwatch_event_bus.jobs.name
  event_pattern = jsonencode({
    "source" : [local.event_source],
    "detail-type" : [local.event_detail_type],
    "detail" : {
      "queue" : ["sam"],
      "method" : ["sam"]
    }
  })
  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "sam" {
  rule           = aws_cloudwatch_event_rule.sam.name
  event_bus_name = aws_cloudwatch_event_bus.jobs.name
  target_id      = "sam-queue"
  arn            = aws_sqs_queue.sam.arn
  input_path     = "$.detail"
}

# Rule for GrabCut jobs
resource "aws_cloudwatch_event_rule" "grabcut" {
  name           = "${var.grabcut_queue_name}-rule"
  description    = "Route GrabCut jobs to GrabCut SQS queue"
  event_bus_name = aws_cloudwatch_event_bus.jobs.name
  event_pattern = jsonencode({
    "source" : [local.event_source],
    "detail-type" : [local.event_detail_type],
    "detail" : {
      "queue" : ["grabcut"],
      "method" : ["grabcut"]
    }
  })
  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "grabcut" {
  rule           = aws_cloudwatch_event_rule.grabcut.name
  event_bus_name = aws_cloudwatch_event_bus.jobs.name
  target_id      = "grabcut-queue"
  arn            = aws_sqs_queue.grabcut.arn
  input_path     = "$.detail"
}

########################
# Allow EventBridge to deliver to SQS
########################

resource "aws_sqs_queue_policy" "sam" {
  queue_url = aws_sqs_queue.sam.url
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid    = "AllowEventBridgeSendSam",
        Effect = "Allow",
        Principal = {
          Service = "events.amazonaws.com"
        },
        Action   = "sqs:SendMessage",
        Resource = aws_sqs_queue.sam.arn,
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.sam.arn
          }
        }
      }
    ]
  })
}

resource "aws_sqs_queue_policy" "grabcut" {
  queue_url = aws_sqs_queue.grabcut.url
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid    = "AllowEventBridgeSendGrabCut",
        Effect = "Allow",
        Principal = {
          Service = "events.amazonaws.com"
        },
        Action   = "sqs:SendMessage",
        Resource = aws_sqs_queue.grabcut.arn,
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.grabcut.arn
          }
        }
      }
    ]
  })
}

########################
# SSM Parameter for bus name
########################

data "aws_ssm_parameter" "event_bus_name" {
  name = "/n11233885/EVENT_BUS_NAME"
}

########################
# Outputs
########################

output "event_bus_name" {
  value = aws_cloudwatch_event_bus.jobs.name
}

output "event_bus_arn" {
  value = aws_cloudwatch_event_bus.jobs.arn
}

