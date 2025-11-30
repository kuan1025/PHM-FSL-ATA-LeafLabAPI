import os, json, time, logging, traceback
from datetime import datetime, timezone
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.exc import OperationalError
from config.db import SessionLocal
from config.db_models import Job, Result, File
from config.s3 import s3_get_bytes, s3_put_bytes, s3_head
from processing import heavy_pipeline, decode_image_from_bytes, encode_png
from sqs.jobqueue import (
    receive_jobs,
    delete_message,
    resolve_queue_url,
)


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("leaflab.worker")

BATCH = int(os.getenv("WORKER_BATCH", "3"))
WAIT  = int(os.getenv("WORKER_WAIT", "10"))        
VIS   = int(os.getenv("WORKER_VISIBILITY", "60"))  
USE_DLQ = os.getenv("USE_DLQ", "true").lower() in ("1","true","yes")
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
    logger.info("Worker using explicit JOB_QUEUE_URL for queue '%s'", QUEUE_NAME or "(custom)")
else:
    try:
        QUEUE_URL = resolve_queue_url(QUEUE_NAME)
    except RuntimeError as exc:
        raise RuntimeError(f"SQS queue URL for worker queue '{QUEUE_NAME}' not configured") from exc


def _truncate_reason(reason: str | None) -> str | None:
    if not reason:
        return None
    return reason[:1024]


def _mark_job_failed(job_id: int, *, reason: str | None = None) -> tuple[str | None, int]:
    with SessionLocal() as db:
        jb = db.get(Job, job_id)
        if not jb:
            return None, 0
        current = jb.failure_count or 0
        new_count = current + 1
        jb.failure_count = new_count
        jb.failure_reason = _truncate_reason(reason)
        jb.finished_at = datetime.now(timezone.utc)
        if new_count >= MAX_FAILURES:
            jb.status = "error_dlq"
        else:
            jb.status = "error"
        db.commit()
        return jb.status, new_count


def _process_one(job_id: int):

    with SessionLocal() as db:
        j = db.get(Job, job_id)
        if not j:
            logger.warning("job_id=%s not found; skip", job_id)
            return "skip_nodel", None
        if j.status not in ("queued", "error"):
            logger.info("job_id=%s status=%s not queued/error; skip", job_id, j.status)
            return "skip_status", None

        j.status = "running"
        j.started_at = datetime.now(timezone.utc)

        file_id  = int(j.file_id)
        owner_id = int(j.owner_id)
        params   = dict(j.params or {})
        db.commit()

    # 2) 
    with SessionLocal() as db:
        f = db.get(File, file_id)
        if not f or not f.s3_key:
            with SessionLocal() as s2:
                jb = s2.get(Job, job_id)
                if jb:
                    jb.status = "error"
                    jb.finished_at = datetime.now(timezone.utc)
                    s2.commit()
            raise RuntimeError("file content missing (s3_key)")
        s3_key = str(f.s3_key)

    img_bytes = s3_get_bytes(s3_key)
    img = decode_image_from_bytes(img_bytes)

    # 3)  heavy
    method = params.get("method", "sam")
    wb     = params.get("white_balance", "none")
    gamma  = float(params.get("gamma", 1.0))
    repeat = int(params.get("repeat", 8))
    if method == "sam":
        wb, gamma = "none", 1.0

    feats, preview, logs = heavy_pipeline(
        img_bgr=img, repeat=repeat, white_balance=wb, gamma=gamma, method=method
    )

    # 4) update result
    preview_bytes = encode_png(preview)
    preview_key = f"results/{owner_id}/{job_id}/preview.png"
    s3_put_bytes(preview_key, preview_bytes, "image/png")
    meta = s3_head(preview_key)

    # 5) rewrite Result & Job
    def _write_back():
        with SessionLocal() as s_w:
            res = Result(
                summary=feats,
                preview_s3_key=preview_key,
                preview_mime="image/png",
                preview_size=meta["size"],
                preview_etag=meta["etag"],
                logs=logs,
            )
            s_w.add(res); s_w.commit(); s_w.refresh(res)
            jb = s_w.get(Job, job_id)
            if jb:
                jb.result_id = res.id
                jb.status = "done"
                jb.finished_at = datetime.now(timezone.utc)
                jb.failure_count = 0
                jb.failure_reason = None
                s_w.commit()
            return res.id

    try:
        rid = _write_back()
    except OperationalError:
        rid = _write_back()

    return "ok", rid


def _handle_message(message: Dict[str, Any], *, queue_url: str) -> None:
    rh = message["ReceiptHandle"]
    body = json.loads(message["Body"])
    job_id = int(body["job_id"])
    logger.info(
        "Received message job_id=%s method=%s queue=%s",
        job_id,
        body.get("method"),
        body.get("queue", QUEUE_NAME),
    )
    attrs = message.get("Attributes", {})
    attempt = int(attrs.get("ApproximateReceiveCount", "1"))
    t0 = time.perf_counter()
    try:
        status, rid = _process_one(job_id)
        took = (time.perf_counter() - t0)
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
        elif status == "skip_nodel":
            logger.warning(
                "job_id=%s not found in DB (attempt=%s); deleting message",
                job_id,
                attempt,
            )
            delete_message(queue_url, rh)
        elif status == "skip_status":
            logger.warning(
                "job_id=%s status=%s; leaving on queue=%s USE_DLQ=%s",
                job_id,
                status,
                queue_url,
                USE_DLQ,
            )
            if not USE_DLQ:
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
    except Exception as e:
        status_after, new_failures = _mark_job_failed(job_id, reason=str(e))
        body["failure_count"] = new_failures
        body["failure_reason"] = str(e)
        queue_name = str(body.get("queue", QUEUE_NAME)).lower()
        logger.error(
            "job_id=%s failed attempt=%s: %s\n%s",
            job_id,
            attempt,
            e,
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
        "Worker started: queue=%s url=%s BATCH=%s CONCURRENCY=%s WAIT=%s VIS=%s",
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
                        logger.error("worker future failed: %s", exc)
            except Exception as e:
                logger.error("poll error: %s", e)
                time.sleep(2)

if __name__ == "__main__":
    main()
