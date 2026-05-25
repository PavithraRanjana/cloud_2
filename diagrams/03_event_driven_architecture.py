"""AeroLink – Event-Driven Architecture
EventBridge publish/subscribe, SQS + DLQ, Lambda triggers, S3, SES, and scheduled pricing.
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.integration import SQS, Eventbridge
from diagrams.aws.storage import S3
from diagrams.aws.compute import Lambda
from diagrams.aws.integration import SimpleNotificationServiceSnsEmailNotification as SES
from diagrams.programming.framework import FastAPI
from diagrams.onprem.client import User

graph_attr = {
    "fontsize": "20",
    "bgcolor": "white",
    "pad": "1.0",
    "splines": "spline",
    "rankdir": "LR",
    "nodesep": "1.0",
    "ranksep": "2.0",
    "concentrate": "false",
}

pub_cluster  = {"fontsize": "14", "bgcolor": "#EBF5FB", "margin": "20"}
aws_cluster  = {"fontsize": "14", "bgcolor": "#FEF9E7", "margin": "20"}
con_cluster  = {"fontsize": "14", "bgcolor": "#E9F7EF", "margin": "20"}
ext_cluster  = {"fontsize": "14", "bgcolor": "#FDEDEC", "margin": "20"}

with Diagram(
    "AeroLink – Event-Driven Architecture",
    filename="diagrams/03_event_driven_architecture",
    outformat="png",
    show=False,
    graph_attr=graph_attr,
):
    # ── Publishers ────────────────────────────────────────────────────────────
    with Cluster("Event Publishers", graph_attr=pub_cluster):
        booking   = FastAPI("booking-service\nBookingCreated\nBookingCancelled")
        payment   = FastAPI("payment-service\nPaymentCompleted\nPaymentFailed\nPaymentRefunded")
        flight    = FastAPI("flight-service\nFlightScheduleUpdated\nSeatAvailabilityChanged")
        baggage   = FastAPI("baggage-service\nBaggageRegistered\nBaggageStatusChanged")
        checkin   = FastAPI("checkin-service\nCheckInCompleted")

    # ── AWS Event Bus ─────────────────────────────────────────────────────────
    with Cluster("AWS  (LocalStack)", graph_attr=aws_cluster):
        eb = Eventbridge(
            "EventBridge\naerolink-events\n10 routing rules"
        )
        sqs = SQS(
            "SQS\naerolink-notifications\nmaxReceive = 3 before DLQ"
        )
        dlq = SQS(
            "SQS  (DLQ)\naerolink-notifications-dlq\nadmin reprocess endpoint"
        )
        lam_bp = Lambda(
            "boarding-pass-generator\nTrigger: CheckInCompleted\npython3.10 · fpdf2 · 60 s"
        )
        lam_pr = Lambda(
            "pricing-recalculation\nTrigger: CloudWatch schedule\nevery 5 min · pg8000 · 120 s"
        )
        s3 = S3(
            "S3\naerolink-documents\nboarding-passes/{booking_id}.pdf"
        )

    # ── Consumers ─────────────────────────────────────────────────────────────
    with Cluster("Event Consumers", graph_attr=con_cluster):
        notif = FastAPI(
            "notification-service\nlong-poll 10 msg / 5 s wait\ndedup via Redis SET NX"
        )

    # ── External ──────────────────────────────────────────────────────────────
    with Cluster("External", graph_attr=ext_cluster):
        ses = SES("AWS SES\nnoreply@aerolink.com")
        pg_direct = FastAPI("PostgreSQL\n(via pg8000)")

    # ── Publishers → EventBridge ──────────────────────────────────────────────
    booking >> Edge(color="#FF9900", penwidth="2.0", label="PutEvents") >> eb
    payment >> Edge(color="#FF9900", penwidth="2.0", label="PutEvents") >> eb
    flight  >> Edge(color="#FF9900", penwidth="2.0", label="PutEvents") >> eb
    baggage >> Edge(color="#FF9900", penwidth="2.0", label="PutEvents") >> eb
    checkin >> Edge(color="#FF9900", penwidth="2.0", label="PutEvents") >> eb

    # ── EventBridge → SQS (all notification events) ───────────────────────────
    eb >> Edge(
        color="#FF9900", penwidth="2.0",
        label="rules 1-10\nall event types"
    ) >> sqs

    # ── EventBridge → boarding-pass Lambda (CheckInCompleted only) ────────────
    eb >> Edge(
        color="#E74C3C", penwidth="2.0",
        label="CheckInCompleted\n(checkin-completed-to-notifications rule)"
    ) >> lam_bp

    # ── SQS → notification-service ────────────────────────────────────────────
    sqs >> Edge(
        color="#2980B9", penwidth="2.0",
        label="long-poll\nbackground thread"
    ) >> notif

    # ── SQS → DLQ (error path) ────────────────────────────────────────────────
    sqs >> Edge(
        color="#E74C3C", style="dashed",
        label="after 3 delivery failures"
    ) >> dlq

    # ── Notification → SES ────────────────────────────────────────────────────
    notif >> Edge(
        color="#C0392B", penwidth="1.8",
        label="send_email\n(plain text)"
    ) >> ses

    # ── boarding-pass Lambda → S3 ─────────────────────────────────────────────
    lam_bp >> Edge(
        color="#27AE60", penwidth="2.0",
        label="PutObject\nPDF boarding pass"
    ) >> s3

    # ── Pricing Lambda → PostgreSQL (direct DB, not via API) ──────────────────
    lam_pr >> Edge(
        color="#8E44AD", penwidth="2.0",
        label="direct pg8000\nSELECT + UPDATE prices"
    ) >> pg_direct
