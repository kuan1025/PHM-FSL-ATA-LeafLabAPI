#!/usr/bin/env bash
MODEL_DIR=${MODEL_DIR:-/models}
set -euo pipefail
MODEL_DIR=${MODEL_DIR:-/models}
MODEL_BUCKET=${MODEL_BUCKET:-n11233885-leaflab-deployment}
MODEL_KEY=${MODEL_KEY:-models/sam_vit_b_01ec64.pth}
MODEL_PATH="${MODEL_DIR}/$(basename "${MODEL_KEY}")"

mkdir -p "${MODEL_DIR}"
python - <<'PY'
import os, boto3
bucket = os.environ["MODEL_BUCKET"]
key    = os.environ["MODEL_KEY"]
path   = os.environ.get("MODEL_PATH", "/models/sam_vit_b_01ec64.pth")
os.makedirs(os.path.dirname(path), exist_ok=True)
boto3.client("s3").download_file(bucket, key, path)
PY

exec python /worker/worker.py
