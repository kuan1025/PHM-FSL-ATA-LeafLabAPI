from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config.db import SessionLocal
from config.db_models import Job
from config.deps import current_admin
from events.job_events import publish_job_requested
from sqs.dlq import list_messages, pop_message, delete_message, decode_message

VERSION = "v1"
QueueName = Literal["sam", "grabcut"]

router = APIRouter(prefix=f"/{VERSION}/dlq", tags=["dlq"], dependencies=[Depends(current_admin)])


class DLQMessage(BaseModel):
    message_id: str
    queue: str
    job_id: int | None
    attempt: int
    sent_at: str | None
    payload: dict
    failure_count: int | None = None
    failure_reason: str | None = None


def _extract_job_id(payload: dict) -> int | None:
    try:
        return int(payload.get("job_id"))
    except (TypeError, ValueError):
        return None


def _job_failure_meta(job_id: int | None) -> tuple[int | None, str | None]:
    if job_id is None:
        return None, None
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return None, None
        return int(job.failure_count or 0), job.failure_reason


@router.get("/{queue_name}", response_model=list[DLQMessage])
def list_dlq_messages(queue_name: QueueName, max_messages: int = 5):
    msgs = list_messages(queue_name, max_messages=max_messages)
    out: list[DLQMessage] = []
    for m in msgs:
        decoded = decode_message(m)
        payload = decoded.get("payload", {})
        job_id = _extract_job_id(payload)
        failure_count, failure_reason = _job_failure_meta(job_id)
        out.append(
            DLQMessage(
                message_id=decoded.get("message_id") or "",
                queue=queue_name,
                job_id=job_id,
                attempt=decoded.get("approximate_receive_count", 0),
                sent_at=decoded.get("sent_at"),
                payload=payload,
                failure_count=failure_count,
                failure_reason=failure_reason,
            )
        )
    return out


class ProcessRequest(BaseModel):
    visibility_timeout: int | None = 15


@router.post("/{queue_name}/requeue", response_model=DLQMessage)
def requeue_dlq_message(queue_name: QueueName, body: ProcessRequest | None = None):
    vt = (body.visibility_timeout if body else 60) or 0
    msg = pop_message(queue_name, visibility_timeout=vt)
    if not msg:
        raise HTTPException(status_code=404, detail="DLQ empty")

    decoded = decode_message(msg)
    payload = decoded.get("payload", {})
    job_id = _extract_job_id(payload)

    if job_id is not None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                job.status = "queued"
                job.started_at = None
                job.finished_at = None
                job.result_id = None
                job.failure_count = 0
                job.failure_reason = None
                db.commit()

    payload = dict(payload or {})
    payload.update({
        "failure_count": 0,
        "failure_reason": None,
    })

    publish_job_requested(payload)
    delete_message(queue_name, msg["ReceiptHandle"])

    failure_count, failure_reason = _job_failure_meta(job_id)

    return DLQMessage(
        message_id=decoded.get("message_id") or "",
        queue=queue_name,
        job_id=job_id,
        attempt=decoded.get("approximate_receive_count", 0),
        sent_at=decoded.get("sent_at"),
        payload=payload,
        failure_count=failure_count,
        failure_reason=failure_reason,
    )


@router.post("/{queue_name}/discard", response_model=DLQMessage)
def discard_dlq_message(queue_name: QueueName, body: ProcessRequest | None = None):
    vt = (body.visibility_timeout if body else 60) or 0
    msg = pop_message(queue_name, visibility_timeout=vt)
    if not msg:
        raise HTTPException(status_code=404, detail="DLQ empty")

    decoded = decode_message(msg)
    payload = decoded.get("payload", {})
    job_id = _extract_job_id(payload)

    if job_id is not None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                job.status = "error_dlq"
                job.finished_at = job.finished_at or job.started_at
                job.failure_reason = job.failure_reason or "discarded from DLQ"
                db.commit()

    delete_message(queue_name, msg["ReceiptHandle"])

    failure_count, failure_reason = _job_failure_meta(job_id)

    return DLQMessage(
        message_id=decoded.get("message_id") or "",
        queue=queue_name,
        job_id=job_id,
        attempt=decoded.get("approximate_receive_count", 0),
        sent_at=decoded.get("sent_at"),
        payload=payload,
        failure_count=failure_count,
        failure_reason=failure_reason,
    )
