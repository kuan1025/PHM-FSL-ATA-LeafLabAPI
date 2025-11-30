import json
import logging
from typing import Dict, Optional

import boto3
from botocore.config import Config

from config.config import settings

logger = logging.getLogger("leaflab.jobqueue")

AWS_REGION = settings.AWS_REGION or "ap-southeast-2"

_QUEUE_MAP: Dict[str, Optional[str]] = {
    "sam": settings.SQS_SAM_QUEUE_URL,
    "grabcut": settings.SQS_GRABCUT_QUEUE_URL,
}


def _default_queue_url() -> Optional[str]:
    for url in _QUEUE_MAP.values():
        if url:
            return url
    return None


def resolve_queue_url(queue_name: Optional[str]) -> str:
    """Resolve the SQS queue URL for the requested logical queue name."""
    default_url = _default_queue_url()

    if queue_name:
        key = queue_name.lower()
        if key in _QUEUE_MAP:
            url = _QUEUE_MAP.get(key)
            if not url:
                raise RuntimeError(f"SQS queue URL for '{key}' not configured")
            return url
        if default_url:
            logger.warning("Unknown queue '%s'; falling back to default queue", key)
            return default_url
        raise RuntimeError(f"Unknown queue '{key}' and no default queue configured")

    if default_url:
        return default_url

    raise RuntimeError("No SQS queue URL configured")


_sqs = boto3.client(
    "sqs",
    region_name=AWS_REGION,
    config=Config(retries={"max_attempts": 3}),
)


def enqueue_job(payload: dict, *, queue_name: Optional[str] = None, queue_url: Optional[str] = None) -> str:
    url = queue_url or resolve_queue_url(queue_name)
    body = json.dumps(payload, separators=(",", ":"))
    resp = _sqs.send_message(QueueUrl=url, MessageBody=body)
    mid = resp.get("MessageId")
    logger.info("ENQUEUE queue=%s job_id=%s mid=%s", queue_name or "(resolved)", payload.get("job_id"), mid)
    return mid


def receive_jobs(*, queue_url: str, max_messages=5, wait_seconds=20, visibility_timeout=None):
    params = dict(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max(1, min(20, int(max_messages))),
        WaitTimeSeconds=max(0, min(20, int(wait_seconds))),
        MessageAttributeNames=["All"],
        AttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
    )
    if visibility_timeout is not None:
        params["VisibilityTimeout"] = int(visibility_timeout)
    return _sqs.receive_message(**params)


def delete_message(queue_url: str, receipt_handle: str):
    _sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


def change_visibility(queue_url: str, receipt_handle: str, timeout: int):
    _sqs.change_message_visibility(
        QueueUrl=queue_url,
        ReceiptHandle=receipt_handle,
        VisibilityTimeout=int(timeout),
    )
