import json
import logging
from typing import Dict, Any

import boto3
from botocore.config import Config

from config.config import settings

logger = logging.getLogger("leaflab.events")

_SQS = boto3.client(
    "sqs",
    region_name=settings.AWS_REGION,
    config=Config(retries={"max_attempts": 3})
)

_DISPATCH_QUEUE_URL = settings.SQS_DISPATCH_QUEUE_URL


def publish_job_requested(detail: Dict[str, Any]) -> str:
    if not _DISPATCH_QUEUE_URL:
        raise RuntimeError("SQS_DISPATCH_QUEUE_URL not configured")

    body = json.dumps(detail, separators=(",", ":"))
    resp = _SQS.send_message(QueueUrl=_DISPATCH_QUEUE_URL, MessageBody=body)
    message_id = resp.get("MessageId")
    if not message_id:
        raise RuntimeError("send_message did not return MessageId")
    logger.info(
        "Dispatch queue enqueued job message_id=%s queue=%s",
        message_id,
        _DISPATCH_QUEUE_URL,
    )
    return message_id
