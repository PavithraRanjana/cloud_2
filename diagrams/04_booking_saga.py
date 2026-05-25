"""AeroLink – Booking Saga
Three saga phases (Booking → Payment → Check-in) shown as a clean left-to-right pipeline.
Each phase is a cluster; compensation paths are dashed red arrows.

Layout strategy: rankdir=LR with three phase-clusters arranged horizontally.
Each service appears exactly once. Compensation arrows flow from right to left
as dashed red lines, clearly distinct from the happy path.
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.client import User
from diagrams.onprem.network import Nginx
from diagrams.onprem.database import PostgreSQL
from diagrams.programming.framework import FastAPI
from diagrams.aws.integration import Eventbridge
from diagrams.aws.compute import Lambda
from diagrams.aws.storage import S3
from diagrams.saas.payment import Stripe

graph_attr = {
    "fontsize": "20",
    "bgcolor": "white",
    "pad": "1.0",
    "splines": "spline",
    "rankdir": "LR",
    "nodesep": "1.0",
    "ranksep": "2.0",
}

phase1_attr = {"fontsize": "14", "bgcolor": "#EBF5FB", "margin": "20"}
phase2_attr = {"fontsize": "14", "bgcolor": "#E9F7EF", "margin": "20"}
phase3_attr = {"fontsize": "14", "bgcolor": "#FEF9E7", "margin": "20"}
shared_attr = {"fontsize": "14", "bgcolor": "#F5EEF8", "margin": "20"}
comp_attr   = {"fontsize": "14", "bgcolor": "#FDEDEC", "margin": "20"}

with Diagram(
    "AeroLink – Booking Saga",
    filename="diagrams/04_booking_saga",
    outformat="png",
    show=False,
    graph_attr=graph_attr,
):
    client  = User("Passenger")
    gateway = Nginx("api-gateway\n:8000")

    # ── Shared infrastructure (event bus + data) ──────────────────────────────
    with Cluster("Shared Infrastructure", graph_attr=shared_attr):
        pg = PostgreSQL("PostgreSQL\nbookings · flights\npayments · checkins")
        eb = Eventbridge("EventBridge\naerolink-events")

    # ── Phase 1: Booking Creation ─────────────────────────────────────────────
    with Cluster("Phase 1 – Book", graph_attr=phase1_attr):
        booking = FastAPI(
            "booking-service :8003\n① acquire seat lock (Redis 15 s)\n② check flight availability\n③ reserve seats (optimistic lock)\n④ persist booking (PENDING)\n⑤ publish BookingCreated"
        )
        flight  = FastAPI(
            "flight-service :8002\nPUT /flights/{id}/seats\nversion column → 409 on race"
        )

    # ── Phase 2: Payment ──────────────────────────────────────────────────────
    with Cluster("Phase 2 – Pay", graph_attr=phase2_attr):
        payment = FastAPI(
            "payment-service :8004\n① check idempotency (Redis + DB)\n② create Stripe PaymentIntent\n③ persist payment (PROCESSING)\n④ handle Stripe webhook\n⑤ update booking → PAID\n⑥ award loyalty points\n⑦ publish PaymentCompleted"
        )
        stripe  = Stripe("Stripe\nPaymentIntent\nwebhook validation")
        passenger = FastAPI(
            "passenger-service :8007\nPOST /loyalty/award\nrecalculate tier\n(bronze→silver→gold→platinum)"
        )

    # ── Phase 3: Check-in ─────────────────────────────────────────────────────
    with Cluster("Phase 3 – Check-In", graph_attr=phase3_attr):
        checkin = FastAPI(
            "checkin-service :8006\n① assign seat + boarding group\n② persist check-in record\n③ update booking → CHECKED-IN\n④ generate PDF boarding pass\n⑤ publish CheckInCompleted"
        )
        lam_bp  = Lambda(
            "boarding-pass-generator\nEventBridge → Lambda\nPDF → S3"
        )
        s3      = S3("S3\nboarding-passes/\n{booking_id}.pdf")

    # ── Compensation paths ────────────────────────────────────────────────────
    with Cluster("Compensation (rollback)", graph_attr=comp_attr):
        comp = FastAPI(
            "booking-service\nPOST /bookings/{id}/cancel\nrelease seats back to flight-service\npublish BookingCancelled"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Happy-path edges
    # ─────────────────────────────────────────────────────────────────────────

    # Client → Gateway → Phase 1
    client  >> Edge(penwidth="2.0", color="#2C3E50") >> gateway
    gateway >> Edge(penwidth="2.0", color="#2C3E50", label="POST /bookings") >> booking

    # Booking ↔ Flight
    booking >> Edge(color="#1a73e8", penwidth="2.0",
                    label="reserve seats") >> flight
    flight  >> Edge(color="#1a73e8", penwidth="2.0",
                    label="200 OK  (or 409 conflict)") >> booking

    # Booking → DB + EventBridge
    booking >> Edge(color="#27AE60", penwidth="1.8") >> pg
    booking >> Edge(color="#FF9900", penwidth="1.8",
                    label="BookingCreated") >> eb

    # Gateway → Phase 2
    gateway >> Edge(penwidth="2.0", color="#2C3E50",
                    label="POST /payments/intent") >> payment

    # Payment ↔ Stripe
    payment >> Edge(color="#E74C3C", penwidth="2.0",
                    label="create PaymentIntent") >> stripe
    stripe  >> Edge(color="#E74C3C", penwidth="2.0",
                    label="webhook: payment_intent.succeeded") >> payment

    # Payment → Booking (mark PAID)
    payment >> Edge(color="#34a853", penwidth="2.0",
                    label="PUT /bookings/{id}/status → paid") >> booking

    # Payment → Passenger (loyalty)
    payment >> Edge(color="#34a853", penwidth="2.0",
                    label="POST /loyalty/award") >> passenger

    # Payment → DB + EventBridge
    payment >> Edge(color="#27AE60", penwidth="1.8") >> pg
    payment >> Edge(color="#FF9900", penwidth="1.8",
                    label="PaymentCompleted") >> eb

    # Gateway → Phase 3
    gateway >> Edge(penwidth="2.0", color="#2C3E50",
                    label="POST /checkin") >> checkin

    # CheckIn → Booking + Flight
    checkin >> Edge(color="#E67E22", penwidth="2.0",
                    label="GET /bookings/{id}\n+ PUT /status → checked-in") >> booking
    checkin >> Edge(color="#E67E22", penwidth="2.0",
                    label="GET /flights/{id}\n(gate info)") >> flight

    # CheckIn → DB + EventBridge + Lambda + S3
    checkin >> Edge(color="#27AE60", penwidth="1.8") >> pg
    checkin >> Edge(color="#FF9900", penwidth="1.8",
                    label="CheckInCompleted") >> eb
    eb      >> Edge(color="#FF9900", penwidth="1.8") >> lam_bp
    lam_bp  >> Edge(color="#27AE60", penwidth="1.8",
                    label="PutObject") >> s3

    # ─────────────────────────────────────────────────────────────────────────
    # Compensation edges  (dashed red, right-to-left)
    # ─────────────────────────────────────────────────────────────────────────

    payment >> Edge(
        color="#E74C3C", style="dashed", penwidth="2.0",
        label="payment fails\nor refund requested"
    ) >> comp

    comp >> Edge(
        color="#E74C3C", style="dashed", penwidth="2.0",
        label="PUT /flights/{id}/seats\n(restore availability)"
    ) >> flight

    comp >> Edge(
        color="#FF9900", style="dashed", penwidth="1.8",
        label="BookingCancelled"
    ) >> eb
