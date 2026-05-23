import json
import boto3
import structlog
from datetime import datetime, timezone
from typing import Any

logger = structlog.get_logger()


def _boto3_kwargs(endpoint_url: str, region: str,
                  aws_access_key_id: str = "", aws_secret_access_key: str = "") -> dict:
    """Build boto3 client kwargs. Credentials and endpoint are only passed when
    targeting LocalStack (endpoint_url is set); in production the ECS task IAM
    role is used automatically via the standard credential chain."""
    kwargs: dict = {"region_name": region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
        # LocalStack requires non-empty credentials — "test" is the conventional placeholder.
        # Empty strings cause LocalStack to resolve a different (non-existent) account ID.
        kwargs["aws_access_key_id"] = aws_access_key_id or "test"
        kwargs["aws_secret_access_key"] = aws_secret_access_key or "test"
    return kwargs


class EventPublisher:
    def __init__(self, endpoint_url: str, region: str, bus_name: str,
                 aws_access_key_id: str = "", aws_secret_access_key: str = ""):
        self.bus_name = bus_name
        self.client = boto3.client(
            "events",
            **_boto3_kwargs(endpoint_url, region, aws_access_key_id, aws_secret_access_key),
        )

    def publish(self, source: str, detail_type: str, detail: dict[str, Any]) -> dict:
        detail["timestamp"] = datetime.now(timezone.utc).isoformat()
        entry = {
            "Source": source,
            "DetailType": detail_type,
            "Detail": json.dumps(detail, default=str),
            "EventBusName": self.bus_name,
        }
        try:
            response = self.client.put_events(Entries=[entry])
            logger.info("event_published", source=source, detail_type=detail_type,
                        failed=response.get("FailedEntryCount", 0))
            return response
        except Exception as e:
            logger.error("event_publish_failed", source=source, detail_type=detail_type, error=str(e))
            raise


class EventConsumer:
    """Polls SQS queue that is subscribed to EventBridge rules."""

    def __init__(self, endpoint_url: str, region: str, queue_url: str,
                 aws_access_key_id: str = "", aws_secret_access_key: str = ""):
        self.queue_url = queue_url
        self.client = boto3.client(
            "sqs",
            **_boto3_kwargs(endpoint_url, region, aws_access_key_id, aws_secret_access_key),
        )

    def poll(self, max_messages: int = 10, wait_seconds: int = 5) -> list[dict]:
        resp = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
        )
        messages = resp.get("Messages", [])
        results = []
        for msg in messages:
            body = json.loads(msg["Body"])
            results.append({"body": body, "receipt_handle": msg["ReceiptHandle"], "message_id": msg["MessageId"]})
        return results

    def ack(self, receipt_handle: str):
        self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
