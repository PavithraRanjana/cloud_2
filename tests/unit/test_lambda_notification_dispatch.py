"""Tests for lambdas/notification_dispatch/handler.py."""
import sys
import os
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambdas", "notification_dispatch"))

from handler import handler, _render_template, TEMPLATES


# ── _render_template ─────────────────────────────────────────────

def test_render_template_all_fields():
    template = TEMPLATES["BookingCreated"]
    detail = {
        "booking_reference": "AL1ABC23",
        "passenger_name": "John Doe",
        "flight_id": "flight-1",
        "total_price": "199.99",
    }
    subject, body = _render_template(template, detail)
    assert "AL1ABC23" in subject
    assert "John Doe" in body
    assert "199.99" in body


def test_render_template_missing_fields_na():
    template = TEMPLATES["BookingCreated"]
    detail = {"booking_reference": "AL1ABC23"}  # missing other fields
    subject, body = _render_template(template, detail)
    assert "AL1ABC23" in subject
    assert "N/A" in body  # missing fields replaced with N/A


# ── handler ──────────────────────────────────────────────────────

def test_handler_single_record():
    event = {
        "Records": [
            {
                "body": json.dumps({
                    "detail-type": "BookingCreated",
                    "detail": json.dumps({
                        "booking_reference": "ALTEST01",
                        "passenger_name": "Test User",
                        "flight_id": "F001",
                        "total_price": "150.00",
                        "passenger_email": "test@example.com",
                    }),
                })
            }
        ]
    }
    result = handler(event, None)
    body = json.loads(result["body"])
    assert body["processed"] == 1
    assert body["errors"] == 0


def test_handler_multiple_records():
    event = {
        "Records": [
            {
                "body": json.dumps({
                    "detail-type": "BookingCreated",
                    "detail": json.dumps({
                        "booking_reference": "AL000001",
                        "passenger_name": "User1",
                        "flight_id": "F1",
                        "total_price": "100",
                    }),
                })
            },
            {
                "body": json.dumps({
                    "detail-type": "PaymentProcessed",
                    "detail": json.dumps({
                        "booking_id": "B1",
                        "amount": "100",
                        "transaction_ref": "TXN-1",
                    }),
                })
            },
        ]
    }
    result = handler(event, None)
    body = json.loads(result["body"])
    assert body["processed"] == 2
    assert body["total"] == 2


def test_handler_unknown_event_type():
    event = {
        "Records": [
            {
                "body": json.dumps({
                    "detail-type": "UnknownEvent",
                    "detail": "{}",
                })
            }
        ]
    }
    result = handler(event, None)
    body = json.loads(result["body"])
    assert body["processed"] == 0  # skipped


def test_handler_malformed_record():
    event = {
        "Records": [
            {"body": "not-valid-json"}
        ]
    }
    result = handler(event, None)
    body = json.loads(result["body"])
    assert body["errors"] == 1


def test_handler_empty_records():
    event = {"Records": []}
    result = handler(event, None)
    body = json.loads(result["body"])
    assert body["processed"] == 0
    assert body["total"] == 0
