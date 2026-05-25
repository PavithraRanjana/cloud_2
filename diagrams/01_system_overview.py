"""AeroLink – System Overview
Full system: all services, API gateway, data layer, AWS resources, and external integrations.
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.client import User
from diagrams.onprem.network import Nginx
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis
from diagrams.aws.integration import SQS, Eventbridge
from diagrams.aws.storage import S3
from diagrams.aws.database import Dynamodb
from diagrams.aws.compute import Lambda
from diagrams.aws.security import Cognito
from diagrams.saas.payment import Stripe
from diagrams.programming.framework import FastAPI
from diagrams.aws.integration import SimpleNotificationServiceSnsEmailNotification as SES

graph_attr = {
    "fontsize": "22",
    "bgcolor": "white",
    "pad": "0.8",
    "splines": "spline",
    "rankdir": "TB",
    "nodesep": "0.8",
    "ranksep": "1.4",
    "concentrate": "true",
}

svc_cluster   = {"fontsize": "14", "bgcolor": "#EBF5FB", "margin": "20"}
data_cluster  = {"fontsize": "14", "bgcolor": "#E9F7EF", "margin": "20"}
aws_cluster   = {"fontsize": "14", "bgcolor": "#FEF9E7", "margin": "20"}
ext_cluster   = {"fontsize": "14", "bgcolor": "#FDEDEC", "margin": "20"}

with Diagram(
    "AeroLink – System Overview",
    filename="diagrams/01_system_overview",
    outformat="png",
    show=False,
    graph_attr=graph_attr,
):
    client = User("Client\n(Browser / Mobile App)")

    with Cluster("API Gateway  :8000", graph_attr={"fontsize": "14", "bgcolor": "#D6EAF8", "margin": "20"}):
        gateway = Nginx("api-gateway\nJWT auth  ·  longest-prefix routing\n30 s timeout  ·  X-Trace-Id injection")

    with Cluster("Microservices", graph_attr=svc_cluster):
        auth      = FastAPI("auth-service :8001\nJWT · bcrypt · Cognito\nrate-limit (Redis DB0)")
        flight    = FastAPI("flight-service :8002\nCQRS · optimistic locking\nRedis cache (DB1)")
        booking   = FastAPI("booking-service :8003\nSaga · distributed seat lock\ncircuit breaker (DB2)")
        payment   = FastAPI("payment-service :8004\nStripe  ·  idempotency\ncircuit breaker (DB3)")
        baggage   = FastAPI("baggage-service :8005\ntag gen  ·  status tracking\nRedis cache (DB4)")
        checkin   = FastAPI("checkin-service :8006\nseat assign  ·  boarding groups\nPDF boarding pass (DB5)")
        passenger = FastAPI("passenger-service :8007\nencryption · GDPR · loyalty\nRedis cache (DB6)")
        notif     = FastAPI("notification-service :8008\nSQS long-poll  ·  dedup\nSES email  (DB7)")

    with Cluster("Data Layer", graph_attr=data_cluster):
        pg    = PostgreSQL("PostgreSQL :5432\nShared DB  –  tables per service")
        redis = Redis("Redis :6379\n8 logical databases")

    with Cluster("AWS  (LocalStack :4566)", graph_attr=aws_cluster):
        cognito = Cognito("Cognito\naerolink-local\npassenger · admin groups")
        eb      = Eventbridge("EventBridge\naerolink-events\n10 routing rules")
        sqs     = SQS("SQS\naerolink-notifications\n+ DLQ (maxReceive=3)")
        ddb     = Dynamodb("DynamoDB\npayment-idempotency")
        s3      = S3("S3\naerolink-documents\nboarding-passes/")
        lam_bp  = Lambda("boarding-pass-generator\nCheckInCompleted → PDF → S3\npython3.10 · fpdf2")
        lam_pr  = Lambda("pricing-recalculation\nEvery 5 min → adjust prices\npython3.10 · pg8000")

    with Cluster("External Services", graph_attr=ext_cluster):
        stripe  = Stripe("Stripe\nPaymentIntent · Refunds\nWebhook validation")
        ses     = SES("AWS SES\nnoreply@aerolink.com\nplain-text email")

    # ── Client → Gateway ──────────────────────────────────────────────────────
    client >> Edge(color="#2C3E50", penwidth="2.0") >> gateway

    # ── Gateway → Services ────────────────────────────────────────────────────
    for svc in [auth, flight, booking, payment, baggage, checkin, passenger, notif]:
        gateway >> Edge(color="#5D6D7E", style="dashed") >> svc

    # ── Services → Data Layer ─────────────────────────────────────────────────
    for svc in [auth, flight, booking, payment, baggage, checkin, passenger, notif]:
        svc >> Edge(color="#27AE60", style="dotted", penwidth="1.5") >> pg

    auth      >> Edge(color="#E67E22", style="dotted") >> redis
    flight    >> Edge(color="#E67E22", style="dotted") >> redis
    booking   >> Edge(color="#E67E22", style="dotted") >> redis
    payment   >> Edge(color="#E67E22", style="dotted") >> redis
    baggage   >> Edge(color="#E67E22", style="dotted") >> redis
    checkin   >> Edge(color="#E67E22", style="dotted") >> redis
    passenger >> Edge(color="#E67E22", style="dotted") >> redis
    notif     >> Edge(color="#E67E22", style="dotted") >> redis

    # ── Auth → Cognito ────────────────────────────────────────────────────────
    auth >> Edge(color="#8E44AD", style="dotted", label="RS256 JWKS") >> cognito

    # ── EventBridge publish/subscribe ─────────────────────────────────────────
    booking   >> Edge(color="#FF9900", label="BookingCreated\nBookingCancelled") >> eb
    payment   >> Edge(color="#FF9900", label="PaymentCompleted\nPaymentFailed\nPaymentRefunded") >> eb
    flight    >> Edge(color="#FF9900", label="FlightScheduleUpdated\nSeatAvailabilityChanged") >> eb
    baggage   >> Edge(color="#FF9900", label="BaggageRegistered\nBaggageStatusChanged") >> eb
    checkin   >> Edge(color="#FF9900", label="CheckInCompleted") >> eb

    eb >> Edge(color="#FF9900") >> sqs
    sqs >> Edge(color="#2980B9", label="long-poll") >> notif

    eb >> Edge(color="#FF9900", label="CheckInCompleted") >> lam_bp
    lam_bp >> Edge(color="#27AE60") >> s3

    lam_pr >> Edge(color="#8E44AD", style="dashed", label="scheduled 5 min") >> pg

    # ── Payment → DynamoDB ────────────────────────────────────────────────────
    payment >> Edge(color="#8E44AD", style="dotted", label="idempotency") >> ddb

    # ── External ─────────────────────────────────────────────────────────────
    payment >> Edge(color="#C0392B", label="PaymentIntent\nRefund · Webhook") >> stripe
    notif   >> Edge(color="#C0392B", label="send_email") >> ses
