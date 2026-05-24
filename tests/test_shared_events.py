"""Tests for shared/events.py — EventPublisher and EventConsumer."""
import sys
import os
import json
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Ensure boto3 is mockable - put a mock in sys.modules if not present
_mock_boto3 = MagicMock()
sys.modules.setdefault("boto3", _mock_boto3)

from shared.events import EventPublisher, EventConsumer


# ── EventPublisher ───────────────────────────────────────────────

def test_publish_event_success():
    mock_client = MagicMock()
    mock_client.put_events.return_value = {"FailedEntryCount": 0}

    with patch("shared.events.boto3") as patched_boto3:
        patched_boto3.client.return_value = mock_client
        pub = EventPublisher(
            endpoint_url="http://localhost:4566",
            region="eu-west-1",
            bus_name="test-bus",
        )
        resp = pub.publish("test-source", "TestEvent", {"key": "value"})
    assert resp["FailedEntryCount"] == 0
    mock_client.put_events.assert_called_once()


def test_publish_event_adds_timestamp():
    mock_client = MagicMock()
    mock_client.put_events.return_value = {"FailedEntryCount": 0}

    with patch("shared.events.boto3") as patched_boto3:
        patched_boto3.client.return_value = mock_client
        pub = EventPublisher(
            endpoint_url="http://localhost:4566",
            region="eu-west-1",
            bus_name="test-bus",
        )
        detail = {"key": "value"}
        pub.publish("src", "Type", detail)
    assert "timestamp" in detail


def test_publish_event_failure_raises():
    mock_client = MagicMock()
    mock_client.put_events.side_effect = Exception("AWS error")

    with patch("shared.events.boto3") as patched_boto3:
        patched_boto3.client.return_value = mock_client
        pub = EventPublisher(
            endpoint_url="http://localhost:4566",
            region="eu-west-1",
            bus_name="test-bus",
        )
        with pytest.raises(Exception, match="AWS error"):
            pub.publish("src", "Type", {"k": "v"})


# ── EventConsumer ────────────────────────────────────────────────

def test_poll_returns_parsed_messages():
    mock_client = MagicMock()
    mock_client.receive_message.return_value = {
        "Messages": [
            {"Body": json.dumps({"detail-type": "TestEvent"}), "ReceiptHandle": "rh1", "MessageId": "msg-1"},
        ]
    }

    with patch("shared.events.boto3") as patched_boto3:
        patched_boto3.client.return_value = mock_client
        consumer = EventConsumer(
            endpoint_url="http://localhost:4566",
            region="eu-west-1",
            queue_url="http://localhost:4566/queue/test",
        )
        results = consumer.poll()
    assert len(results) == 1
    assert results[0]["body"]["detail-type"] == "TestEvent"
    assert results[0]["receipt_handle"] == "rh1"
    assert results[0]["message_id"] == "msg-1"


def test_poll_empty_queue():
    mock_client = MagicMock()
    mock_client.receive_message.return_value = {"Messages": []}

    with patch("shared.events.boto3") as patched_boto3:
        patched_boto3.client.return_value = mock_client
        consumer = EventConsumer(
            endpoint_url="http://localhost:4566",
            region="eu-west-1",
            queue_url="http://localhost:4566/queue/test",
        )
        results = consumer.poll()
    assert results == []


def test_poll_handles_json_body():
    body_data = {"detail-type": "BookingCreated", "detail": {"id": "123"}}
    mock_client = MagicMock()
    mock_client.receive_message.return_value = {
        "Messages": [
            {"Body": json.dumps(body_data), "ReceiptHandle": "rh2", "MessageId": "msg-2"},
        ]
    }

    with patch("shared.events.boto3") as patched_boto3:
        patched_boto3.client.return_value = mock_client
        consumer = EventConsumer(
            endpoint_url="http://localhost:4566",
            region="eu-west-1",
            queue_url="http://localhost:4566/queue/test",
        )
        results = consumer.poll()
    assert results[0]["body"]["detail"]["id"] == "123"


def test_ack_deletes_message():
    mock_client = MagicMock()

    with patch("shared.events.boto3") as patched_boto3:
        patched_boto3.client.return_value = mock_client
        consumer = EventConsumer(
            endpoint_url="http://localhost:4566",
            region="eu-west-1",
            queue_url="http://localhost:4566/queue/test",
        )
        consumer.ack("receipt-handle-123")
    mock_client.delete_message.assert_called_once_with(
        QueueUrl="http://localhost:4566/queue/test",
        ReceiptHandle="receipt-handle-123",
    )


def test_ack_failure_raises():
    mock_client = MagicMock()
    mock_client.delete_message.side_effect = Exception("SQS error")

    with patch("shared.events.boto3") as patched_boto3:
        patched_boto3.client.return_value = mock_client
        consumer = EventConsumer(
            endpoint_url="http://localhost:4566",
            region="eu-west-1",
            queue_url="http://localhost:4566/queue/test",
        )
        with pytest.raises(Exception, match="SQS error"):
            consumer.ack("rh")
