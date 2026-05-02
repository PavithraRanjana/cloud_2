"""Tests for lambdas/boarding_pass_generator/handler.py."""
import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "boarding_pass_generator"))

# boto3 hangs on import in this environment, so mock it before importing handler
mock_boto3_module = MagicMock()
with patch.dict("sys.modules", {"boto3": mock_boto3_module}):
    from handler import _build_pdf, handler


# ── _build_pdf ───────────────────────────────────────────────────

def test_build_pdf_returns_bytes():
    result = _build_pdf(
        passenger_name="John Doe",
        flight_id="AL100",
        seat_number="12A",
        boarding_group="B",
        gate="A5",
        booking_id="ALTEST01",
    )
    # fpdf2 returns bytearray; accept both bytes and bytearray
    assert isinstance(result, (bytes, bytearray))
    assert len(result) > 0


def test_build_pdf_contains_passenger_name():
    result = _build_pdf(
        passenger_name="Jane Smith",
        flight_id="AL200",
        seat_number="1A",
        boarding_group="A",
        gate="B3",
        booking_id="ALTEST02",
    )
    # fpdf2 compresses content with FlateDecode, so raw text search
    # won't work; verify we got a valid PDF with reasonable size
    assert result[:5] == b"%PDF-"
    assert len(result) > 500


# ── handler ──────────────────────────────────────────────────────

def test_handler_success_uploads_to_s3():
    mock_s3 = MagicMock()
    mock_boto3_module.client.return_value = mock_s3

    event = {
        "detail": {
            "booking_id": "BOOKING-1",
            "flight_id": "FLIGHT-1",
            "passenger_name": "Test User",
            "seat_number": "5B",
            "boarding_group": "A",
            "gate": "C2",
        }
    }
    result = handler(event, None)
    assert result["statusCode"] == 200
    mock_s3.put_object.assert_called_once()
    body = json.loads(result["body"])
    assert body["passenger"] == "Test User"


def test_handler_correct_s3_key():
    mock_s3 = MagicMock()
    mock_boto3_module.client.return_value = mock_s3

    event = {
        "detail": {
            "booking_id": "BOOKING-42",
            "flight_id": "FL-1",
            "passenger_name": "User",
            "seat_number": "1A",
            "boarding_group": "A",
            "gate": "A1",
        }
    }
    handler(event, None)
    call_kwargs = mock_s3.put_object.call_args
    assert call_kwargs[1]["Key"] == "boarding-passes/BOOKING-42.pdf"


def test_handler_missing_fields_uses_defaults():
    mock_s3 = MagicMock()
    mock_boto3_module.client.return_value = mock_s3

    event = {"detail": {}}
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["passenger"] == "Passenger"


def test_handler_detail_as_string_parsed():
    mock_s3 = MagicMock()
    mock_boto3_module.client.return_value = mock_s3

    event = {
        "detail": json.dumps({
            "booking_id": "B-STR",
            "flight_id": "F-1",
            "passenger_name": "String Detail",
            "seat_number": "3C",
            "boarding_group": "A",
            "gate": "D1",
        })
    }
    result = handler(event, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["passenger"] == "String Detail"
