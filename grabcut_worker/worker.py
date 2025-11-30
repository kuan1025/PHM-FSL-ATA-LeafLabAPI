import json
import logging
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from sqlalchemy.exc import OperationalError

from config.db import SessionLocal
from config.db_models import File, Job, Result
from config.s3 import s3_get_bytes, s3_head, s3_put_bytes
from processing import decode_image_from_bytes, encode_png, heavy_pipeline
from sqs.jobqueue import delete_message, receive_jobs, resolve_queue_url


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("leaflab.grabcut-worker")

BATCH = int(os.getenv("WORKER_BATCH", "3"))
WAIT = int(os.getenv("WORKER_WAIT", "10"))
VIS = int(os.getenv("WORKER_VISIBILITY", "60"))
USE_DLQ = os.getenv("USE_DLQ", "true").lower() in ("1", "true", "yes")
MAX_FAILURES = int(os.getenv("JOB_MAX_FAILURES", "2"))
CONCURRENCY = int(
    os.getenv(
        "WORKER_THREADS",
        os.getenv("WORKER_CONCURRENCY", str(BATCH)),
    )
)

QUEUE_NAME = os.getenv("WORKER_QUEUE", "grabcut").lower()
QUEUE_URL = os.getenv("JOB_QUEUE_URL")

if QUEUE_URL:
    logger.info("GrabCut worker using explicit JOB_QUEUE_URL for queue '%s'", QUEUE_NAME or "(custom)")
else:
    try:
        QUEUE_URL = resolve_queue_url(QUEUE_NAME)
    except RuntimeError as exc:
        raise RuntimeError(f"SQS queue URL for worker queue '{QUEUE_NAME}' not configured") from exc


def _truncate_reason(reason: str | None) -> str | None:
    if not reason:
        return None
    return reason[:1024]


def _mark_job_failed(job_id: int, *, reason: str | None = None) -> Tuple[str | None, int]:
    with SessionLocal() as db:
        jb = db.get(Job, job_id)
        if not jb:
            return None, 0
        current = jb.failure_count or 0
        new_count = current + 1
        jb.failure_count = new_count
        jb.failure_reason = _truncate_reason(reason)
        jb.finished_at = datetime.now(timezone.utc)
        jb.status = "error_dlq" if new_count >= MAX_FAILURES else "error"
        db.commit()
        return jb.status, new_count


def _load_job(job_id: int) -> Tuple[Job, Dict[str, Any]]:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            raise RuntimeError(f"job_id={job_id} not found")
        if job.status not in ("queued", "error"):
            raise RuntimeError(f"job_id={job_id} invalid status {job.status!r}")

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        params = dict(job.params or {})
        db.commit()
        return job, params


def _load_file(file_id: int) -> str:
    with SessionLocal() as db:
        f = db.get(File, file_id)
        if not f or not f.s3_key:
            raise RuntimeError("file content missing (s3_key)")
        return str(f.s3_key)


def _write_result(job_id: int, summary: Dict[str, Any], logs: str, preview_key: str, meta: Dict[str, Any]) -> int:
    with SessionLocal() as db:
        res = Result(
            summary=summary,
            preview_s3_key=preview_key,
            preview_mime="image/png",
            preview_size=meta["size"],
            preview_etag=meta["etag"],
            logs=logs,
        )
        db.add(res)
        db.commit()
        db.refresh(res)

        job = db.get(Job, job_id)
        if job:
            job.result_id = res.id
            job.status = "done"
            job.finished_at = datetime.now(timezone.utc)
            job.failure_count = 0
            job.failure_reason = None
            db.commit()
        return res.id


def _process_one(job_id: int) -> Tuple[str, Any]:
    try:
        job, params = _load_job(job_id)
    except RuntimeError as exc:
        logger.warning("job_id=%s %s; skip", job_id, exc)
        return "skip", None

    file_id = int(job.file_id)
    owner_id = int(job.owner_id)

    method = params.get("method", "grabcut")
    if method.lower() != "grabcut":
        logger.warning("job_id=%s requested method=%s; forcing grabcut", job_id, method)
    white_balance = params.get("white_balance", "none")
    gamma = float(params.get("gamma", 1.0))
    repeat = int(params.get("repeat", 8))

    try:
        s3_key = _load_file(file_id)
    except RuntimeError as exc:
        logger.error("job_id=%s file load error: %s", job_id, exc)
        _mark_job_failed(job_id, reason=str(exc))
        return "error", None

    img_bytes = s3_get_bytes(s3_key)
    img = decode_image_from_bytes(img_bytes)

    feats, preview, logs = heavy_pipeline(
        img_bgr=img,
        repeat=repeat,
        white_balance=white_balance,
        gamma=gamma,
    )

    preview_bytes = encode_png(preview)
    preview_key = f"results/{owner_id}/{job_id}/preview.png"
    s3_put_bytes(preview_key, preview_bytes, "image/png")
    meta = s3_head(preview_key)

    result_payload = dict(feats)
    result_payload["logs"] = logs

    try:
        rid = _write_result(job_id, result_payload, logs, preview_key, meta)
    except OperationalError:
        rid = _write_result(job_id, result_payload, logs, preview_key, meta)

    return "ok", rid


def _handle_message(message: Dict[str, Any], *, queue_url: str) -> None:
    rh = message["ReceiptHandle"]
    body = json.loads(message["Body"])
    job_id = int(body["job_id"])
    logger.info(
        "Received GrabCut message job_id=%s queue=%s",
        job_id,
        body.get("queue", QUEUE_NAME),
    )
    attrs = message.get("Attributes", {})
    attempt = int(attrs.get("ApproximateReceiveCount", "1"))
    t0 = time.perf_counter()
    try:
        status, rid = _process_one(job_id)
        took = time.perf_counter() - t0
        if status == "ok":
            logger.info(
                "job_id=%s status=%s rid=%s took=%.2fs attempt=%s",
                job_id,
                status,
                rid,
                took,
                attempt,
            )
            delete_message(queue_url, rh)
        elif status == "skip":
            logger.warning(
                "job_id=%s skipped; deleting message (attempt=%s)",
                job_id,
                attempt,
            )
            delete_message(queue_url, rh)
        else:
            logger.info(
                "job_id=%s status=%s took=%.2fs attempt=%s",
                job_id,
                status,
                took,
                attempt,
            )
            delete_message(queue_url, rh)
    except Exception as exc:
        status_after, new_failures = _mark_job_failed(job_id, reason=str(exc))
        body["failure_count"] = new_failures
        body["failure_reason"] = str(exc)
        queue_name = str(body.get("queue", QUEUE_NAME)).lower()
        logger.error(
            "job_id=%s failed attempt=%s: %s\n%s",
            job_id,
            attempt,
            exc,
            traceback.format_exc(),
        )
        if not USE_DLQ:
            delete_message(queue_url, rh)
        else:
            logger.warning(
                "job_id=%s left on queue for SQS redrive (attempt=%s status=%s queue=%s)",
                job_id,
                attempt,
                status_after,
                queue_name,
            )


def main():
    logger.info(
        "GrabCut worker started: queue=%s url=%s BATCH=%s CONCURRENCY=%s WAIT=%s VIS=%s",
        QUEUE_NAME,
        QUEUE_URL,
        BATCH,
        CONCURRENCY,
        WAIT,
        VIS,
    )
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        while True:
            try:
                resp = receive_jobs(
                    queue_url=QUEUE_URL,
                    max_messages=BATCH,
                    wait_seconds=WAIT,
                    visibility_timeout=VIS,
                )
                msgs = resp.get("Messages", [])
                if not msgs:
                    logger.debug("No messages polled from %s", QUEUE_URL)
                    continue
                futures = [
                    executor.submit(_handle_message, m, queue_url=QUEUE_URL)
                    for m in msgs
                ]
                for fut in futures:
                    try:
                        fut.result()
                    except Exception as exc:
                        logger.error("grabcut worker future failed: %s", exc)
            except Exception as exc:
                logger.error("poll error: %s", exc)
                time.sleep(2)


if __name__ == "__main__":
    main()
