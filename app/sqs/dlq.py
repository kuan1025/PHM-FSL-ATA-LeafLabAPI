import json
from datetime import datetime, timezone
from typing import Dict, Optional, List

import boto3
from botocore.config import Config

from config.config import settings

_CLIENT = boto3.client(
    "sqs",
    region_name=settings.AWS_REGION,
    config=Config(retries={"max_attempts": 3}),
)

_DLQ_MAP: Dict[str, Optional[str]] = {
    "sam": settings.SQS_SAM_DLQ_URL,
    "grabcut": settings.SQS_GRABCUT_DLQ_URL,
}


def _resolve_dlq(queue_name: str) -> str:
    key = queue_name.lower()
    url = _DLQ_MAP.get(key)
    if not url:
        raise RuntimeError(f"DLQ URL for '{queue_name}' not configured")
    return url


def list_messages(queue_name: str, max_messages: int = 5) -> List[Dict]:
    url = _resolve_dlq(queue_name)
    resp = _CLIENT.receive_message(
        QueueUrl=url,
        MaxNumberOfMessages=max(1, min(10, max_messages)),
        WaitTimeSeconds=0,
        VisibilityTimeout=0,
        AttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
        MessageAttributeNames=["All"],
    )
    messages = resp.get("Messages", [])
    deduped: Dict[str, Dict] = {}
    for msg in messages:
        mid = msg.get("MessageId")
        if mid is None or mid not in deduped:
            deduped[mid or str(len(deduped))] = msg
    return list(deduped.values())


def pop_message(queue_name: str, visibility_timeout: int = 60) -> Optional[Dict]:
    url = _resolve_dlq(queue_name)
    resp = _CLIENT.receive_message(
        QueueUrl=url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=0,
        VisibilityTimeout=max(0, visibility_timeout),
        AttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
        MessageAttributeNames=["All"],
    )
    msgs = resp.get("Messages", [])
    return msgs[0] if msgs else None


def delete_message(queue_name: str, receipt_handle: str) -> None:
    url = _resolve_dlq(queue_name)
    _CLIENT.delete_message(QueueUrl=url, ReceiptHandle=receipt_handle)


def send_to_dlq(queue_name: str, payload: Dict) -> str:
    url = _resolve_dlq(queue_name)
    resp = _CLIENT.send_message(
        QueueUrl=url,
        MessageBody=json.dumps(payload, separators=(",", ":")),
    )
    return resp.get("MessageId", "")


def decode_message(message: Dict) -> Dict:
    body = message.get("Body")
    detail = json.loads(body) if body else {}
    attrs = message.get("Attributes", {})
    sent_ts = attrs.get("SentTimestamp")
    sent_at = None
    if sent_ts:
        try:
            sent_at = datetime.fromtimestamp(int(sent_ts) / 1000, tz=timezone.utc).isoformat()
        except Exception:
            sent_at = None
    return {
        "message_id": message.get("MessageId"),
        "receipt_handle": message.get("ReceiptHandle"),
        "payload": detail,
        "approximate_receive_count": int(attrs.get("ApproximateReceiveCount", "0")),
        "sent_at": sent_at,
    }
