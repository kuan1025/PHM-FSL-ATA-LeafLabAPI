import os, json, time, urllib.request
from datetime import datetime, timezone
import boto3

REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
QUEUE_URLS = [q.strip() for q in os.environ.get("QUEUE_URLS", "").split(",") if q.strip()]
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK", "").strip()
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SEC", "0"))  
TIMEOUT_SEC = int(os.environ.get("HTTP_TIMEOUT_SEC", "5"))      
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1","true","yes")

sqs = boto3.client("sqs", region_name=REGION)

def get_counts(url):
    a = sqs.get_queue_attributes(
        QueueUrl=url,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible"
        ]
    ).get("Attributes", {})
    visible = int(a.get("ApproximateNumberOfMessages", "0"))
    inflight = int(a.get("ApproximateNumberOfMessagesNotVisible", "0"))
    return visible, inflight

def build_slack_message(rows):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f" *DLQ Health Check* ({REGION})", f"*Time:* {now}"]
    lines += [f"• `{name}` — *{v}* pending | {i} in-flight" for name, v, i in rows]
    lines.append("*Action:* Admins, please review DLQ messages and requeue/discard as appropriate.")
    return "\n".join(lines)

def post_slack(text):
    if not SLACK_WEBHOOK:
        print("[info] SLACK_WEBHOOK not set, skip sending")
        return
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        resp.read()

def run_once():
    if not QUEUE_URLS:
        print("[warn] QUEUE_URLS is empty; nothing to report")
        return

    rows = []
    for url in QUEUE_URLS:
        qname = url.rsplit("/", 1)[-1]
        try:
            vis, inflight = get_counts(url)
        except Exception as e:
            print(f"[error] get_counts failed for {qname}: {e}")
            vis, inflight = -1, -1
        rows.append((qname, vis, inflight))

    msg = build_slack_message(rows)
    print(msg)
    if not DRY_RUN:
        try:
            post_slack(msg)
        except Exception as e:
            print(f"[error] post_slack failed: {e}")

if __name__ == "__main__":
    if POLL_INTERVAL <= 0:
        run_once()
    else:
        while True:
            run_once()
            time.sleep(POLL_INTERVAL)
