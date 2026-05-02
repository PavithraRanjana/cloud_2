"""
Lambda 1: Notification Dispatch
Triggered by SQS (aerolink-notifications queue).
Receives EventBridge events forwarded by SQS, renders notification
templates and logs output (simulating email/SMS delivery).
No external dependencies - stdlib only.
"""

import json
import logging

logger = logging.getLogger("notification_dispatch")
logger.setLevel(logging.INFO)

# Same templates used by the notification-service
TEMPLATES = {
    "BookingCreated": {
        "subject": "Booking Confirmation - {booking_reference}",
        "body": (
            "Dear {passenger_name},\n\n"
            "Your booking {booking_reference} has been created successfully.\n\n"
            "Flight: {flight_id}\nTotal: EUR {total_price}\n\n"
            "Please proceed to payment to confirm your booking.\n\n"
            "Thank you for choosing AeroLink!"
        ),
    },
    "PaymentProcessed": {
        "subject": "Payment Confirmed - Booking {booking_id}",
        "body": (
            "Dear Customer,\n\n"
            "Your payment of EUR {amount} has been processed successfully.\n\n"
            "Transaction Reference: {transaction_ref}\n"
            "Booking: {booking_id}\n\n"
            "You can now check in online.\n\n"
            "Thank you for choosing AeroLink!"
        ),
    },
    "CheckInCompleted": {
        "subject": "Check-In Complete - Seat {seat_number}",
        "body": (
            "Dear {passenger_name},\n\n"
            "You have been checked in successfully.\n\n"
            "Seat: {seat_number}\nFlight: {flight_id}\n\n"
            "Your boarding pass is ready. Please arrive at the gate "
            "at least 30 minutes before departure.\n\n"
            "Have a great flight!"
        ),
    },
    "BaggageStatusChanged": {
        "subject": "Baggage Update - {tag_number}",
        "body": (
            "Baggage {tag_number} status update:\n\n"
            "New Status: {status}\nLocation: {location}\n\n"
            "Track your baggage at any time through our app."
        ),
    },
    "BookingCancelled": {
        "subject": "Booking Cancelled - {booking_reference}",
        "body": (
            "Your booking {booking_reference} has been cancelled.\n\n"
            "If you made a payment, a refund will be processed within "
            "5-7 business days.\n\n"
            "We hope to see you again soon."
        ),
    },
    "PaymentFailed": {
        "subject": "Payment Failed - Booking {booking_id}",
        "body": (
            "Dear Customer,\n\n"
            "Your payment for booking {booking_id} could not be processed.\n\n"
            "Please try again or use a different payment method.\n\n"
            "Thank you for choosing AeroLink!"
        ),
    },
}


class _SafeDict(dict):
    """Dict subclass that returns 'N/A' for missing keys during str.format_map."""
    def __missing__(self, key):
        return "N/A"


def _render_template(template: dict, detail: dict) -> tuple[str, str]:
    """Render subject and body, substituting missing keys with 'N/A'."""
    safe = _SafeDict(detail)
    subject = template["subject"].format_map(safe)
    body = template["body"].format_map(safe)
    return subject, body


def handler(event, context):
    """
    SQS Lambda handler.
    Each record in event["Records"] contains an SQS message whose body
    is the EventBridge event JSON.
    """
    records = event.get("Records", [])
    logger.info("Received %d SQS record(s)", len(records))

    processed = 0
    errors = 0

    for record in records:
        try:
            body = json.loads(record["body"])
            detail_type = body.get("detail-type", "")
            detail = body.get("detail", {})
            if isinstance(detail, str):
                detail = json.loads(detail)

            template = TEMPLATES.get(detail_type)
            if not template:
                logger.info("No template for event type: %s", detail_type)
                continue

            subject, rendered_body = _render_template(template, detail)

            recipient = detail.get("passenger_email", "unknown@example.com")
            logger.info(
                "[NOTIFICATION SENT] To: %s | Subject: %s | Event: %s",
                recipient, subject, detail_type,
            )
            logger.info("[NOTIFICATION BODY]\n%s", rendered_body)
            processed += 1

        except Exception as e:
            logger.error("Failed to process record: %s", str(e))
            errors += 1

    result = {
        "statusCode": 200,
        "body": json.dumps({
            "processed": processed,
            "errors": errors,
            "total": len(records),
        }),
    }
    logger.info("Dispatch complete: %s", result["body"])
    return result
