import os
import time
import logging
from typing import Dict, Any
import boto3
from botocore.client import Config
from cache import cache_get_json, cache_set_json, cache_delete
from config import settings

AWS_REGION = settings.AWS_REGION
S3_BUCKET  = settings.S3_BUCKET
if not S3_BUCKET:
    raise RuntimeError("S3_BUCKET not set")

# boto3 client 
_s3 = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))

# TTL from env
HEAD_TTL    = 300    # seconds (0=disable HEAD cache)
PRESIGN_TTL = 300  # seconds
CACHE_DEBUG = True

logger = logging.getLogger("leaflab.cache")


# ---------- Object Ops ----------
def s3_put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    _s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    # Invalidate caches
    cache_delete(f"s3:head:{key}")
    cache_delete(f"s3:url:{key}")
    logger.info("INVALIDATE key=%s (after PUT)", key)

def s3_get_bytes(key: str) -> bytes:
    t0 = time.perf_counter()
    resp = _s3.get_object(Bucket=S3_BUCKET, Key=key)
    body = resp["Body"].read()
    took = (time.perf_counter() - t0) * 1000
    logger.info("GET bytes key=%s size=%d took=%.2fms", key, len(body), took)
    return body

def s3_delete(key: str) -> None:
    _s3.delete_object(Bucket=S3_BUCKET, Key=key)
    cache_delete(f"s3:head:{key}")
    cache_delete(f"s3:url:{key}")


# ---------- Metadata (HEAD) with cache ----------
def s3_head(key: str) -> Dict[str, Any]:
    t0 = time.monotonic()
    ck = f"s3:head:{key}"
    cached = cache_get_json(ck)
    if cached:
        logger.info("HEAD HIT key=%s took=%.2fms", key, (time.perf_counter() - t0)*1000)
        return cached

    logger.info("check Bucket %s : ", S3_BUCKET)
    logger.info("check key %s : ", key)
    t1 = time.monotonic()
    resp = _s3.head_object(Bucket=S3_BUCKET, Key=key)
    t2 = time.perf_counter()
    

    meta = {
        "size": resp["ContentLength"],
        "content_type": resp.get("ContentType") or "application/octet-stream",
        "etag": resp.get("ETag", "").strip('"'),
        "last_modified": resp.get("LastModified").isoformat() if resp.get("LastModified") else None,
    }
    if HEAD_TTL > 0:
        cache_set_json(ck, meta, HEAD_TTL)
    logger.info(
        "HEAD MISS key=%s total=%.2fms s3=%.2fms ttl=%ss",
        key, (t2 - t0) * 1000, (t2 - t1) * 1000, HEAD_TTL
    )
    return meta

# ---------- Pre-signed URLs ----------
def s3_presign_put(key: str, content_type: str = "application/octet-stream", expires: int = 900) -> str:
    t0 = time.perf_counter()
    url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": S3_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )
    logger.info("PRESIGN PUT key=%s expires=%ss took=%.2fms", key, expires, (time.perf_counter() - t0)*1000)
    return url

def s3_presign_get(key: str, expires: int = 900) -> str:
    now = int(time.time())
    ck = f"s3:url:{key}"
    t0 = time.perf_counter()
    cached = cache_get_json(ck)
    if cached and cached.get("exp", 0) > now + 5:
        logger.info("PRESIGN HIT key=%s took=%.2fms", key, (time.perf_counter() - t0)*1000)
        return cached["url"]

    url = _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )
    ttl = max(1, min(PRESIGN_TTL, expires - 5))  
    cache_set_json(ck, {"url": url, "exp": now + ttl}, ttl)
    logger.info("PRESIGN MISS key=%s total=%.2fms ttl=%ss", key, (time.perf_counter() - t0)*1000, ttl)
    return url
