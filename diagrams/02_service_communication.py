"""AeroLink – Service-to-Service Communication
All synchronous HTTP calls between services.

Layout strategy: rankdir=LR with no service clusters so graphviz
builds ranks from edge topology:
  Rank 0  gw
  Rank 1  payment · checkin · passenger · auth · baggage (one hop from gw)
  Rank 2  booking  (called by payment, checkin, passenger + gw proxy)
  Rank 3  flight · notification  (terminal callees)
This keeps all arrows flowing left-to-right with no crossings.
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.client import User
from diagrams.onprem.network import Nginx
from diagrams.programming.framework import FastAPI

graph_attr = {
    "fontsize": "20",
    "bgcolor": "white",
    "pad": "1.0",
    "splines": "spline",
    "rankdir": "LR",
    "nodesep": "1.2",
    "ranksep": "2.2",
    "concentrate": "false",
}

with Diagram(
    "AeroLink – Service Communication",
    filename="diagrams/02_service_communication",
    outformat="png",
    show=False,
    graph_attr=graph_attr,
):
    client = User("Client")

    # ── Tier 0: Entry ─────────────────────────────────────────────────────────
    gw = Nginx("api-gateway\n:8000\nJWT auth · proxy")

    # ── Tier 1: Direct gateway targets (no outbound service calls) ────────────
    auth    = FastAPI("auth-service\n:8001")
    baggage = FastAPI("baggage-service\n:8005")

    # ── Tier 1/2: Orchestrators (make outbound calls) ─────────────────────────
    payment   = FastAPI("payment-service\n:8004")
    checkin   = FastAPI("checkin-service\n:8006")
    passenger = FastAPI("passenger-service\n:8007")

    # ── Tier 2: booking-service (called by orchestrators) ─────────────────────
    booking = FastAPI("booking-service\n:8003")

    # ── Tier 3: Terminal services (only called, never call out) ───────────────
    flight = FastAPI("flight-service\n:8002")
    notif  = FastAPI("notification-service\n:8008")

    # ── Client → Gateway ──────────────────────────────────────────────────────
    client >> Edge(penwidth="2.0", color="#2C3E50") >> gw

    # ── Gateway proxy edges (dashed) ──────────────────────────────────────────
    # Only draw gateway→leaf-services to establish left-anchor rank;
    # orchestrators get their rank from inter-service edges below.
    gw >> Edge(style="dashed", color="#7F8C8D", label="proxy all routes") >> auth
    gw >> Edge(style="dashed", color="#7F8C8D") >> baggage
    gw >> Edge(style="dashed", color="#7F8C8D") >> payment
    gw >> Edge(style="dashed", color="#7F8C8D") >> checkin
    gw >> Edge(style="dashed", color="#7F8C8D") >> passenger

    # ── booking-service ← → flight-service (booking saga) ────────────────────
    booking >> Edge(
        color="#1a73e8", penwidth="2.0",
        label="GET /flights/{id}\nPUT /flights/{id}/seats"
    ) >> flight

    # ── payment-service → booking-service (payment saga) ─────────────────────
    payment >> Edge(
        color="#34a853", penwidth="2.0",
        label="GET /bookings/{id}\nPUT /bookings/{id}/status"
    ) >> booking

    # ── payment-service → passenger-service (loyalty award) ──────────────────
    payment >> Edge(
        color="#34a853", penwidth="2.0",
        label="POST /passengers/loyalty/award\n(X-Internal-API-Key)"
    ) >> passenger

    # ── checkin-service → booking-service (checkin saga) ─────────────────────
    checkin >> Edge(
        color="#ea4335", penwidth="2.0",
        label="GET /bookings/{id}\nPUT /bookings/{id}/status"
    ) >> booking

    # ── checkin-service → flight-service (boarding pass data) ────────────────
    checkin >> Edge(
        color="#ea4335", penwidth="2.0",
        label="GET /flights/{id}\n(gate · terminal info)"
    ) >> flight

    # ── passenger-service → booking + notification (GDPR erasure) ────────────
    passenger >> Edge(
        color="#9334e6", style="dashed", penwidth="1.8",
        label="POST …/anonymize\n(GDPR right to erasure)"
    ) >> booking

    passenger >> Edge(
        color="#9334e6", style="dashed", penwidth="1.8",
        label="POST …/anonymize\n(GDPR right to erasure)"
    ) >> notif
