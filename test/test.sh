#!/usr/bin/env bash
set -euo pipefail

BASE="http://localhost:8001" #  For tunnel TCP 8001 
LOGIN_URL="$BASE/api/auth/login"
START_BASE="$BASE/api/v1/jobs"
USERNAME="admin"
PASSWORD="password"
JOB_IDS=(73 72 71 70 69 68 67 66 65 64 63 62 61 60 59 58 57 56 55 54 53 52 51)

BATCH_SIZE=4
INTERVAL_SEC=330  

echo "[1/2] Login to get JWT..."
LOGIN_RESP=$(curl -sS -X POST "$LOGIN_URL" \
  --data-urlencode "username=$USERNAME" \
  --data-urlencode "password=$PASSWORD")

JWT=$(echo "$LOGIN_RESP" | jq -r '.access_token // .token // .jwt // .data.token // empty')
if [[ -z "${JWT:-}" || "$JWT" == "null" ]]; then
  echo "Login failed. Response:" >&2
  echo "$LOGIN_RESP" >&2
  exit 1
fi
echo "JWT stored"

echo "[2/2] Fire-and-go: batches of $BATCH_SIZE every $((INTERVAL_SEC))s (no waiting for job completion)..."

total=${#JOB_IDS[@]}
for (( offset=0; offset<total; offset+=BATCH_SIZE )); do
  batch_no=$((offset / BATCH_SIZE + 1))
  last_index=$(( offset + BATCH_SIZE - 1 ))
  (( last_index >= total )) && last_index=$(( total - 1 ))
  echo "===> Batch ${batch_no} (jobs indices ${offset}..${last_index})"

  for (( j=0; j<BATCH_SIZE && (offset+j)<total; j++ )); do
    id=${JOB_IDS[$((offset+j))]}
    url="$START_BASE/$id/start"
    ts=$(date -Iseconds)

    echo "[$ts] -> start job $id"
    {

      if curl -fsS -X POST "$url" \
           -H "Authorization: Bearer $JWT" \
           -H 'Accept: application/json' \
           -o "/tmp/start_job_${id}.log"; then
        echo "job $id -> triggered (log: /tmp/start_job_${id}.log)"
      else
        rc=$?
        echo "job $id -> trigger error (curl exit $rc, see /tmp/start_job_${id}.log)" >&2
      fi
    } & 
  done

  remaining=$(( total - (offset + BATCH_SIZE) ))
  if (( remaining > 0 )); then
    echo "sleep ${INTERVAL_SEC}s before next batch..."
    sleep "$INTERVAL_SEC"
  fi
done

echo "All $total jobs have been triggered in batches of $BATCH_SIZE (without waiting)."
