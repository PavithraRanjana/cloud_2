"""
Lambda 2: Boarding Pass PDF Generator
Triggered by EventBridge on CheckInCompleted events.
Generates a PDF boarding pass using fpdf2 and uploads it to S3.
Dependencies: fpdf2
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from fpdf import FPDF

logger = logging.getLogger("boarding_pass_generator")
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get("S3_BUCKET", "aerolink-documents")
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "http://localstack:4566")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")


def _build_pdf(passenger_name: str, flight_id: str, seat_number: str,
               boarding_group: str, gate: str, booking_id: str) -> bytes:
    """Generate a branded boarding pass PDF and return its bytes."""
    pdf = FPDF(orientation="L", unit="mm", format=(100, 210))
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # ---- Header band ----
    pdf.set_fill_color(0, 51, 102)  # AeroLink navy
    pdf.rect(0, 0, 210, 22, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(8, 4)
    pdf.cell(100, 14, "AeroLink", ln=0)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(140, 4)
    pdf.cell(60, 14, "BOARDING PASS", align="R")

    # ---- Passenger info ----
    pdf.set_text_color(0, 0, 0)
    y = 28
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(8, y)
    pdf.cell(50, 5, "PASSENGER NAME")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_xy(8, y + 5)
    pdf.cell(120, 8, passenger_name.upper())

    # ---- Flight / Seat / Gate row ----
    y = 46
    col_w = 48
    labels = ["FLIGHT", "SEAT", "BOARDING GROUP", "GATE"]
    values = [flight_id[:16], seat_number, boarding_group, gate or "TBA"]
    for i, (label, value) in enumerate(zip(labels, values)):
        x = 8 + i * col_w
        pdf.set_font("Helvetica", "", 8)
        pdf.set_xy(x, y)
        pdf.cell(col_w, 5, label)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_xy(x, y + 5)
        pdf.cell(col_w, 8, str(value))

    # ---- QR placeholder ----
    pdf.set_draw_color(180, 180, 180)
    pdf.rect(160, 55, 30, 30)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(160, 70)
    pdf.cell(30, 5, "QR CODE", align="C")

    # ---- Divider ----
    pdf.set_draw_color(200, 200, 200)
    pdf.dashed_line(8, 65, 150, 65, dash_length=2, space_length=2)

    # ---- Footer ----
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(120, 120, 120)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.set_xy(8, 88)
    pdf.cell(190, 5, f"Booking: {booking_id}  |  Generated: {generated}  |  AeroLink Airlines")

    return pdf.output()


def handler(event, context):
    """
    EventBridge event handler.
    The event 'detail' contains check-in data:
      booking_id, flight_id, passenger_name, seat_number, boarding_group, gate
    """
    logger.info("Boarding pass generator invoked")
    detail = event.get("detail", {})
    if isinstance(detail, str):
        detail = json.loads(detail)

    booking_id = detail.get("booking_id", "unknown")
    flight_id = detail.get("flight_id", "unknown")
    passenger_name = detail.get("passenger_name", "Passenger")
    seat_number = detail.get("seat_number", "N/A")
    boarding_group = detail.get("boarding_group", "N/A")
    gate = detail.get("gate", "TBA")

    logger.info(
        "Generating boarding pass for %s on flight %s, seat %s",
        passenger_name, flight_id, seat_number,
    )

    pdf_bytes = _build_pdf(
        passenger_name=passenger_name,
        flight_id=flight_id,
        seat_number=seat_number,
        boarding_group=boarding_group,
        gate=gate,
        booking_id=booking_id,
    )

    s3_key = f"boarding-passes/{booking_id}.pdf"
    s3 = boto3.client(
        "s3",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )

    logger.info("Uploaded boarding pass to s3://%s/%s", S3_BUCKET, s3_key)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Boarding pass generated",
            "s3_key": s3_key,
            "passenger": passenger_name,
            "flight": flight_id,
        }),
    }
