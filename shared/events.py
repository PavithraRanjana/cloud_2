import json
import boto3
import structlog
from datetime import datetime, timezone
from typing import Any

logger = structlog.get_logger()


class EventPublisher:
    def __init__(self, endpoint_url: str, region: str, bus_name: str,
                 aws_access_key_id: str = "test", aws_secret_access_key: str = "test"):
        self.bus_name = bus_name
        self.client = boto3.client(
            "events",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
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
                 aws_access_key_id: str = "test", aws_secret_access_key: str = "test"):
        self.queue_url = queue_url
        self.client = boto3.client(
            "sqs",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
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
            results.append({"body": body, "receipt_handle": msg["ReceiptHandle"]})
        return results

    def ack(self, receipt_handle: str):
        self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
