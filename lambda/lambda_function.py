import json
import os
import boto3

sqs = boto3.client("sqs")

SAM_QUEUE_URL = os.environ["SAM_QUEUE_URL"]
GRABCUT_QUEUE_URL = os.environ["GRABCUT_QUEUE_URL"]

def lambda_handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        method = (body.get("method") or "").lower()

        if method == "sam":
            target = SAM_QUEUE_URL
        elif method == "grabcut":
            target = GRABCUT_QUEUE_URL
        else:
            print(f"Unknown method: {method}, skipping")
            continue

        sqs.send_message(
            QueueUrl=target,
            MessageBody=json.dumps(body, separators=(",", ":")),
        )
