"""AeroLink – Infrastructure
Docker containers, shared data layer, LocalStack AWS resources, and external services.
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.container import Docker
from diagrams.aws.integration import SimpleNotificationServiceSnsEmailNotification as SES
from diagrams.aws.integration import SQS, Eventbridge
from diagrams.aws.storage import S3
from diagrams.aws.database import Dynamodb
from diagrams.aws.compute import Lambda
from diagrams.aws.security import Cognito, IAM
from diagrams.saas.payment import Stripe

graph_attr = {
    "fontsize": "20",
    "bgcolor": "white",
    "pad": "1.0",
    "splines": "spline",
    "rankdir": "TB",
    "nodesep": "0.8",
    "ranksep": "1.4",
    "concentrate": "true",
}

docker_attr = {"fontsize": "14", "bgcolor": "#EBF5FB", "margin": "20"}
data_attr   = {"fontsize": "14", "bgcolor": "#E9F7EF", "margin": "20"}
redis_attr  = {"fontsize": "13", "bgcolor": "#FEF9E7", "margin": "16"}
aws_attr    = {"fontsize": "14", "bgcolor": "#FDF2E9", "margin": "20"}
ext_attr    = {"fontsize": "14", "bgcolor": "#FDEDEC", "margin": "20"}

with Diagram(
    "AeroLink – Infrastructure",
    filename="diagrams/05_infrastructure",
    outformat="png",
    show=False,
    graph_attr=graph_attr,
):
    # ── Docker Compose services ───────────────────────────────────────────────
    with Cluster("Docker Compose Network  (bridge)", graph_attr=docker_attr):
        gw       = Docker("api-gateway :8000\nhealthcheck: GET /health")
        auth_c   = Docker("auth-service :8001\nbcrypt rounds=10\nasync hash/verify")
        flight_c = Docker("flight-service :8002\nCQRS read model (Redis)\noptimistic locking")
        book_c   = Docker("booking-service :8003\ndistributed seat lock\ncircuit breaker + retry")
        pay_c    = Docker("payment-service :8004\nStripe integration\nidempotency guard")
        bag_c    = Docker("baggage-service :8005\ntag gen BAG-XXXXXXXXXX")
        chk_c    = Docker("checkin-service :8006\nseat resolution\nPDF via fpdf2")
        pax_c    = Docker("passenger-service :8007\nAES encryption (passport)\nGDPR + loyalty tiers")
        notif_c  = Docker("notification-service :8008\nSQS long-poll thread\ndedup + DLQ handling")

    # ── Shared Data Layer ─────────────────────────────────────────────────────
    with Cluster("Shared Data Layer", graph_attr=data_attr):
        pg = PostgreSQL(
            "PostgreSQL 15  :5432\nDB: aerolink\n"
            "users · flights · bookings\n"
            "payments · baggage · checkins\n"
            "passengers · notifications\n"
            "audit_logs · gdpr_consents"
        )

        with Cluster("Redis 7  :6379  (8 logical DBs)", graph_attr=redis_attr):
            r0 = Redis("DB 0  auth\nlogin fail counter\nrate-limit TTL 300 s")
            r1 = Redis("DB 1  flight\nflight search cache\nTTL 300 s  –  CQRS")
            r2 = Redis("DB 2  booking\nseat lock  SET NX 15 s\nbooking list TTL 60 s")
            r3 = Redis("DB 3  payment\nintent cache\nTTL 86400 s (24 h)")
            r4 = Redis("DB 4  baggage\ntag + admin list\nTTL 30–300 s")
            r5 = Redis("DB 5  checkin\ncheckin record\nTTL 3600 s")
            r6 = Redis("DB 6  passenger\nprofile cache\nTTL 300 s")
            r7 = Redis("DB 7  notification\ndedup key SET NX\nTTL 3600 s")

    # ── LocalStack (AWS emulation) ────────────────────────────────────────────
    with Cluster("LocalStack :4566  (AWS emulation)", graph_attr=aws_attr):
        cognito = Cognito(
            "Cognito  aerolink-local\ngroups: passenger · admin\ntest users: ranjana, test-admin …"
        )
        eb  = Eventbridge("EventBridge\naerolink-events\n10 routing rules")
        sqs = SQS("SQS  aerolink-notifications\nmaxReceiveCount = 3")
        dlq = SQS("SQS  aerolink-notifications-dlq\nadmin reprocess API")
        s3  = S3("S3  aerolink-documents\nboarding-passes/{booking_id}.pdf")
        ddb = Dynamodb("DynamoDB\npayment-idempotency\nHASH: idempotency_key")
        iam = IAM("IAM\nlambda-execution-role\nAWSLambdaBasicExecutionRole")
        lam_bp = Lambda(
            "boarding-pass-generator\nEventBridge → PDF → S3\npython3.10 · fpdf2\n256 MB · 60 s · arm64"
        )
        lam_pr = Lambda(
            "pricing-recalculation\nCloudWatch 5 min schedule\npython3.10 · pg8000\n256 MB · 120 s · arm64"
        )

    # ── External Services ─────────────────────────────────────────────────────
    with Cluster("External Services", graph_attr=ext_attr):
        stripe = Stripe("Stripe\nPaymentIntent · Refund\nWebhook signature validation")
        ses    = SES("AWS SES\nnoreply@aerolink.com\nverify identity on startup")

    # ── Services → PostgreSQL ─────────────────────────────────────────────────
    for svc in [auth_c, flight_c, book_c, pay_c, bag_c, chk_c, pax_c, notif_c]:
        svc >> Edge(color="#27AE60", style="dotted", penwidth="1.5") >> pg

    # ── Services → Redis (one-to-one logical DB) ──────────────────────────────
    auth_c   >> Edge(color="#E67E22") >> r0
    flight_c >> Edge(color="#E67E22") >> r1
    book_c   >> Edge(color="#E67E22") >> r2
    pay_c    >> Edge(color="#E67E22") >> r3
    bag_c    >> Edge(color="#E67E22") >> r4
    chk_c    >> Edge(color="#E67E22") >> r5
    pax_c    >> Edge(color="#E67E22") >> r6
    notif_c  >> Edge(color="#E67E22") >> r7

    # ── Auth → Cognito ────────────────────────────────────────────────────────
    auth_c >> Edge(color="#8E44AD", style="dashed", label="JWKS / RS256") >> cognito

    # ── EventBridge publish → SQS → notification ─────────────────────────────
    for svc in [book_c, pay_c, flight_c, bag_c, chk_c]:
        svc >> Edge(color="#FF9900", penwidth="1.8") >> eb

    eb >> Edge(color="#FF9900", penwidth="2.0") >> sqs
    sqs >> Edge(color="#2980B9", penwidth="2.0", label="long-poll") >> notif_c
    sqs >> Edge(color="#E74C3C", style="dashed", label="3 failures") >> dlq

    # ── EventBridge → boarding-pass Lambda ───────────────────────────────────
    eb >> Edge(color="#FF9900", label="CheckInCompleted") >> lam_bp
    lam_bp >> Edge(color="#27AE60") >> s3

    # ── Pricing Lambda → PostgreSQL direct ───────────────────────────────────
    lam_pr >> Edge(color="#8E44AD", label="direct pg8000") >> pg

    # ── Payment → DynamoDB ────────────────────────────────────────────────────
    pay_c >> Edge(color="#8E44AD", style="dotted", label="idempotency") >> ddb

    # ── IAM → Lambdas ────────────────────────────────────────────────────────
    iam >> Edge(color="#7F8C8D", style="dotted") >> lam_bp
    iam >> Edge(color="#7F8C8D", style="dotted") >> lam_pr

    # ── External integrations ────────────────────────────────────────────────
    pay_c   >> Edge(color="#E74C3C", penwidth="2.0", label="PaymentIntent · Refund") >> stripe
    notif_c >> Edge(color="#C0392B", penwidth="2.0", label="send_email") >> ses
