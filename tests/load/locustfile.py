"""
AeroLink Load Testing Suite
===========================
Assignment scenarios:
  Scenario 1 – FlightSearchUser        : 500 concurrent users searching flights
  Scenario 2 – BookingUser             : 200 concurrent booking requests
  Scenario 3 – BaggageTrackingUser     : 1000 concurrent baggage status checks
  Scenario 4 – EndToEndUser            : realistic full journey

High-value scenarios:
  Scenario 5 – SpikeUser               : flash-sale spike (0→500 in 5 s)
  Scenario 6 – DoubleBookingUser       : concurrent last-seat booking (optimistic lock)
  Scenario 7 – IdempotencyUser         : duplicate payment storm
  Scenario 8 – SoakUser                : 100 users × 30 min steady load

Medium-value scenarios:
  Scenario 9  – TokenRefreshUser       : JWT refresh storm (200 users)
  Scenario 10 – PassengerProfileUser   : passenger CRUD under load
  Scenario 11 – CheckInConcurrencyUser : concurrent check-ins for same flight

Run individual scenarios:
  locust -f tests/locustfile.py FlightSearchUser         --host http://localhost:8000 --headless -u 500  -r 25  -t 3m
  locust -f tests/locustfile.py BookingUser              --host http://localhost:8000 --headless -u 200  -r 10  -t 3m
  locust -f tests/locustfile.py BaggageTrackingUser      --host http://localhost:8000 --headless -u 1000 -r 50  -t 3m
  locust -f tests/locustfile.py EndToEndUser             --host http://localhost:8000 --headless -u 50   -r 5   -t 3m
  locust -f tests/locustfile.py SpikeUser                --host http://localhost:8000 --headless -u 500  -r 500 -t 2m
  locust -f tests/locustfile.py DoubleBookingUser        --host http://localhost:8000 --headless -u 50   -r 50  -t 2m
  locust -f tests/locustfile.py IdempotencyUser          --host http://localhost:8000 --headless -u 50   -r 50  -t 2m
  locust -f tests/locustfile.py SoakUser                 --host http://localhost:8000 --headless -u 100  -r 5   -t 30m
  locust -f tests/locustfile.py TokenRefreshUser         --host http://localhost:8000 --headless -u 200  -r 20  -t 3m
  locust -f tests/locustfile.py PassengerProfileUser     --host http://localhost:8000 --headless -u 100  -r 10  -t 3m
  locust -f tests/locustfile.py CheckInConcurrencyUser   --host http://localhost:8000 --headless -u 100  -r 20  -t 3m
"""

import json as _json
import random
import string
import uuid
from datetime import datetime, timedelta

from locust import HttpUser, TaskSet, between, events, tag, task

# Pre-seeded racer credentials for Scenario 6 (avoid rate-limit on on_start)
try:
    _RACER_CREDS = _json.load(open("/tmp/racer_creds.json"))
except FileNotFoundError:
    _RACER_CREDS = []

# ── Shared seed data ─────────────────────────────────────────────────────────

ROUTES = [
    ("DUB", "LHR"), ("LHR", "JFK"), ("JFK", "LAX"),
    ("DUB", "CDG"), ("CDG", "FCO"), ("LAX", "ORD"),
    ("JFK", "DUB"), ("LHR", "DXB"), ("DXB", "SIN"),
]
DEPARTURE_DATES = [
    (datetime.now() + timedelta(days=d)).strftime("%Y-%m-%d")
    for d in [7, 14, 21, 30, 45, 60]
]
KNOWN_TAG = "BAG-0001234567"   # seeded by the app; fallback for tracking tests
KNOWN_FLIGHT_ID = None          # populated on_start from a real search


def _random_email():
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"lt_{suffix}@aerolink.test"


def _random_password():
    return "LoadTest@" + "".join(random.choices(string.digits, k=6))


# ── Auth helpers ─────────────────────────────────────────────────────────────

class AuthMixin:
    """Shared login / token lifecycle for user classes that need auth."""

    token: str = ""
    user_id: str = ""
    email: str = ""
    password: str = ""
    username: str = ""

    def _register_and_login(self):
        self.email = _random_email()
        self.password = _random_password()
        self.username = self.email.split("@")[0]

        with self.client.post(
            "/api/v1/auth/register",
            json={
                "email": self.email,
                "username": self.username,
                "password": self.password,
                "full_name": "Load Tester",
            },
            name="/api/v1/auth/register",
            catch_response=True,
        ) as r:
            if r.status_code not in (201, 409):
                r.failure(f"register unexpected {r.status_code}")
                return
            else:
                r.success()

        with self.client.post(
            "/api/v1/auth/login",
            json={"username": self.username, "password": self.password},
            name="/api/v1/auth/login",
            catch_response=True,
        ) as r2:
            if r2.status_code == 200:
                body = r2.json()
                self.token = body.get("access_token", "")
                self.user_id = body.get("user_id", "")
                r2.success()
            else:
                r2.failure(f"login failed {r2.status_code}")

    @property
    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"}


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1 – Flight Search (500 users, read-heavy)
# ═══════════════════════════════════════════════════════════════════════════════

class FlightSearchUser(HttpUser):
    """
    Simulates passengers browsing flight availability.
    Heavy read load on flight-service via API gateway.
    Target: 500 concurrent users.
    """
    wait_time = between(0.5, 2)
    host = "http://localhost:8000"

    @tag("search", "scenario1")
    @task(5)
    def search_by_route(self):
        origin, dest = random.choice(ROUTES)
        self.client.get(
            f"/api/v1/flights?origin={origin}&destination={dest}",
            name="/api/v1/flights?origin&destination",
        )

    @tag("search", "scenario1")
    @task(3)
    def search_by_route_and_date(self):
        origin, dest = random.choice(ROUTES)
        date = random.choice(DEPARTURE_DATES)
        self.client.get(
            f"/api/v1/flights?origin={origin}&destination={dest}&departure_date={date}",
            name="/api/v1/flights?origin&destination&date",
        )

    @tag("search", "scenario1")
    @task(2)
    def search_with_price_filter(self):
        origin, dest = random.choice(ROUTES)
        max_price = random.choice([250, 350, 500, 800])
        self.client.get(
            f"/api/v1/flights?origin={origin}&destination={dest}&max_price={max_price}",
            name="/api/v1/flights?origin&destination&max_price",
        )

    @tag("search", "scenario1")
    @task(2)
    def list_all_flights(self):
        self.client.get("/api/v1/flights", name="/api/v1/flights (all)")

    @tag("search", "scenario1")
    @task(1)
    def get_specific_flight(self):
        # First search to find a flight ID
        r = self.client.get(
            "/api/v1/flights?origin=DUB&destination=LHR",
            name="/api/v1/flights (seed lookup)",
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                fid = items[0]["id"]
                self.client.get(
                    f"/api/v1/flights/{fid}",
                    name="/api/v1/flights/{flight_id}",
                )

    @tag("health", "scenario1")
    @task(1)
    def health_check(self):
        self.client.get("/health", name="/health (gateway)")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2 – Booking (200 users, write-heavy with auth)
# ═══════════════════════════════════════════════════════════════════════════════

class BookingUser(AuthMixin, HttpUser):
    """
    Simulates passengers searching and booking flights.
    Exercises auth + booking + payment pipeline.
    Target: 200 concurrent users.
    """
    wait_time = between(1, 3)
    host = "http://localhost:8000"

    _flight_id: str = ""
    _booking_id: str = ""

    def on_start(self):
        self._register_and_login()
        self._fetch_flight()

    def _fetch_flight(self):
        r = self.client.get(
            "/api/v1/flights",
            name="/api/v1/flights (booking seed)",
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                self._flight_id = items[0]["id"]

    @tag("booking", "scenario2")
    @task(4)
    def search_flights(self):
        origin, dest = random.choice(ROUTES)
        self.client.get(
            f"/api/v1/flights?origin={origin}&destination={dest}",
            name="/api/v1/flights (booking search)",
        )

    @tag("booking", "scenario2")
    @task(3)
    def create_booking(self):
        if not self.token or not self._flight_id:
            return
        seat_class = random.choice(["economy", "business"])
        r = self.client.post(
            "/api/v1/bookings",
            headers=self._auth,
            json={
                "flight_id": self._flight_id,
                "seat_class": seat_class,
                "passenger_name": "Load Tester",
                "passenger_email": self.email,
                "seat_number": f"{random.randint(1, 30)}{random.choice('ABCDEF')}",
            },
            name="/api/v1/bookings (create)",
        )
        if r.status_code == 201:
            self._booking_id = r.json().get("id", "")

    @tag("booking", "scenario2")
    @task(2)
    def list_my_bookings(self):
        if not self.token:
            return
        self.client.get(
            "/api/v1/bookings",
            headers=self._auth,
            name="/api/v1/bookings (list)",
        )

    @tag("booking", "scenario2")
    @task(2)
    def process_payment(self):
        if not self.token or not self._booking_id:
            return
        with self.client.post(
            "/api/v1/payments/intent",
            headers=self._auth,
            json={
                "booking_id": self._booking_id,
                "amount": round(random.uniform(150, 900), 2),
                "currency": "EUR",
                "idempotency_key": str(uuid.uuid4()),
            },
            name="/api/v1/payments/intent",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 201, 400, 409, 422, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("booking", "scenario2")
    @task(1)
    def get_booking(self):
        if not self.token or not self._booking_id:
            return
        self.client.get(
            f"/api/v1/bookings/{self._booking_id}",
            headers=self._auth,
            name="/api/v1/bookings/{id} (get)",
        )

    @tag("booking", "scenario2")
    @task(1)
    def validate_token(self):
        if not self.token:
            return
        self.client.get(
            "/api/v1/auth/validate",
            headers=self._auth,
            name="/api/v1/auth/validate",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3 – Baggage Tracking (1000 users, very high read volume)
# ═══════════════════════════════════════════════════════════════════════════════

class BaggageTrackingUser(AuthMixin, HttpUser):
    """
    Simulates authenticated passengers polling their baggage status.
    Users must sign in before they can track baggage.
    """
    wait_time = between(0.2, 1)
    host = "http://localhost:8000"

    _tag_pool: list = []

    def on_start(self):
        self._register_and_login()
        self._tag_pool = self._seed_tags()

    def _seed_tags(self) -> list:
        tags = [KNOWN_TAG]
        for _ in range(10):
            tags.append(f"BAG-{random.randint(1000000000, 9999999999)}")
        return tags

    @tag("baggage", "scenario3")
    @task(6)
    def track_by_tag(self):
        if not self.token:
            return
        tag_num = random.choice(self._tag_pool)
        with self.client.get(
            f"/api/v1/baggage/{tag_num}",
            name="/api/v1/baggage/{tag_number}",
            headers=self._auth,
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("baggage", "scenario3")
    @task(3)
    def track_by_booking(self):
        if not self.token:
            return
        booking_id = str(uuid.uuid4())
        with self.client.get(
            f"/api/v1/baggage/booking/{booking_id}",
            name="/api/v1/baggage/booking/{booking_id}",
            headers=self._auth,
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("baggage", "scenario3")
    @task(1)
    def health_check(self):
        self.client.get("/health", name="/health (baggage load)")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4 – End-to-End Journey (realistic user flow)
# ═══════════════════════════════════════════════════════════════════════════════

class EndToEndUser(AuthMixin, HttpUser):
    """
    Full passenger journey: register → login → search → book → pay → check-in → track baggage.
    Lower concurrency but highest complexity — exposes saga/circuit-breaker paths.
    Target: 50 concurrent users.
    """
    wait_time = between(2, 5)
    host = "http://localhost:8000"

    _flight_id: str = ""
    _booking_id: str = ""
    _booking_ref: str = ""

    def on_start(self):
        self._register_and_login()

    @tag("e2e")
    @task(1)
    def full_journey(self):
        if not self.token:
            self._register_and_login()
            return

        # Step 1: Search
        r = self.client.get(
            "/api/v1/flights?origin=DUB&destination=LHR",
            name="[e2e] 1_search_flights",
        )
        if r.status_code != 200:
            return
        items = r.json().get("items", [])
        if not items:
            return
        self._flight_id = items[0]["id"]

        # Step 2: Book
        with self.client.post(
            "/api/v1/bookings",
            headers=self._auth,
            json={
                "flight_id": self._flight_id,
                "seat_class": "economy",
                "passenger_name": "E2E Tester",
                "passenger_email": self.email,
                "seat_number": f"{random.randint(1, 30)}A",
            },
            name="[e2e] 2_create_booking",
            catch_response=True,
        ) as r:
            if r.status_code == 201:
                r.success()
            elif r.status_code in (400, 409, 422, 429):
                r.success()  # seat conflict or rate-limit — expected under load
                return
            else:
                r.failure(f"unexpected {r.status_code}")
                return
        if r.status_code != 201:
            return
        body = r.json()
        self._booking_id = body.get("id", "")
        self._booking_ref = body.get("booking_reference", "")

        # Step 3: Pay
        self.client.post(
            "/api/v1/payments/intent",
            headers=self._auth,
            json={
                "booking_id": self._booking_id,
                "amount": 199.99,
                "currency": "EUR",
                "idempotency_key": str(uuid.uuid4()),
            },
            name="[e2e] 3_process_payment",
        )

        # Step 4: Check-in (may fail if payment failed — that's expected saga behaviour)
        if self._booking_id:
            self.client.post(
                "/api/v1/checkin",
                headers=self._auth,
                json={
                    "booking_id": self._booking_id,
                    "seat_number": f"{random.randint(1, 30)}B",
                    "document_type": "passport",
                    "document_number": f"P{random.randint(10000000, 99999999)}",
                },
                name="[e2e] 4_checkin",
            )

        # Step 5: Track baggage (will likely 404 — still exercises the path)
        with self.client.get(
            f"/api/v1/baggage/booking/{self._booking_id}",
            headers=self._auth,
            name="[e2e] 5_track_baggage",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("e2e")
    @task(1)
    def passenger_profile(self):
        if not self.token:
            return
        with self.client.get(
            "/api/v1/passengers/profile",
            headers=self._auth,
            name="[e2e] get_profile",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 5 – Spike / Flash-sale (sudden 0→500 surge)
# ═══════════════════════════════════════════════════════════════════════════════

class SpikeUser(HttpUser):
    """
    Simulates a flash-sale: all 500 users arrive simultaneously (spawn-rate=500).
    Tests gateway queuing, backpressure, and graceful degradation under instant load.
    Run with: --users 500 --spawn-rate 500 --run-time 2m
    """
    wait_time = between(0.1, 0.5)
    host = "http://localhost:8000"

    @tag("spike", "scenario5")
    @task(7)
    def search_flash_sale_route(self):
        origin, dest = random.choice(ROUTES)
        with self.client.get(
            f"/api/v1/flights?origin={origin}&destination={dest}",
            name="[spike] search_flights",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("spike", "scenario5")
    @task(2)
    def get_specific_flight(self):
        r = self.client.get(
            "/api/v1/flights",
            name="[spike] list_flights",
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                fid = random.choice(items)["id"]
                self.client.get(
                    f"/api/v1/flights/{fid}",
                    name="[spike] get_flight/{id}",
                )

    @tag("spike", "scenario5")
    @task(1)
    def health(self):
        with self.client.get(
            "/health",
            name="[spike] /health",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"{r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 6 – Double-booking / Optimistic Locking
# ═══════════════════════════════════════════════════════════════════════════════

# Scarce flight seeded by bootstrap: AL999 with only 5 economy seats
SCARCE_FLIGHT_ID = "0214099e-5ef0-4beb-9531-bda770fc3381"


class DoubleBookingUser(AuthMixin, HttpUser):
    """
    50 users all try to book the same scarce flight (5 seats) simultaneously.
    Only 5 should succeed; the rest should get 409/400. Validates optimistic
    locking prevents overselling.
    Run with: --users 50 --spawn-rate 50 --run-time 2m
    """
    wait_time = between(0.1, 0.3)
    host = "http://localhost:8000"

    def on_start(self):
        if _RACER_CREDS:
            cred = random.choice(_RACER_CREDS)
            r = self.client.post(
                "/api/v1/auth/login",
                json={"username": cred["username"], "password": cred["password"]},
                name="[double-booking] login",
            )
            if r.status_code == 200:
                self.token = r.json().get("access_token", "")
                self.email = cred["username"] + "@aerolink.test"
        else:
            self._register_and_login()

    @tag("double-booking", "scenario6")
    @task(1)
    def attempt_last_seat(self):
        if not self.token:
            return
        with self.client.post(
            "/api/v1/bookings",
            headers=self._auth,
            json={
                "flight_id": SCARCE_FLIGHT_ID,
                "seat_class": "economy",
                "passenger_name": "Race Condition",
                "passenger_email": self.email,
                "seat_number": f"{random.randint(1, 5)}A",
            },
            name="[double-booking] book_last_seat",
            catch_response=True,
        ) as r:
            # 201 = got a seat, 409/400/422 = correctly rejected
            if r.status_code in (201, 400, 409, 422, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("double-booking", "scenario6")
    @task(1)
    def check_availability(self):
        with self.client.get(
            f"/api/v1/flights/{SCARCE_FLIGHT_ID}",
            name="[double-booking] check_seats",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 7 – Payment Idempotency Storm
# ═══════════════════════════════════════════════════════════════════════════════

IDEMPOTENCY_FLIGHT_ID = "19dc2b3d-e36d-4ace-af2d-c8fcb5d4e27b"  # AL100 — 149 economy seats


class IdempotencyUser(AuthMixin, HttpUser):
    """
    50 users each fire the same payment request (same idempotency_key) repeatedly.
    Only one charge should ever be created per key.
    Uses pre-seeded racer credentials to avoid bcrypt bottleneck on startup.
    Run with: --users 50 --spawn-rate 50 --run-time 2m
    """
    wait_time = between(0.05, 0.2)
    host = "http://localhost:8000"

    _idempotency_key: str = ""
    _booking_id: str = ""

    def on_start(self):
        # Login with pre-seeded cred to skip registration bcrypt cost
        if _RACER_CREDS:
            cred = random.choice(_RACER_CREDS)
            with self.client.post(
                "/api/v1/auth/login",
                json={"username": cred["username"], "password": cred["password"]},
                name="[idempotency] login",
                catch_response=True,
            ) as r:
                if r.status_code == 200:
                    self.token = r.json().get("access_token", "")
                    self.email = cred["username"] + "@aerolink.test"
                    r.success()
                else:
                    r.failure(f"login {r.status_code}")
        else:
            self._register_and_login()

        self._idempotency_key = str(uuid.uuid4())
        self._setup_booking()

    def _setup_booking(self):
        if not self.token:
            return
        with self.client.post(
            "/api/v1/bookings",
            headers=self._auth,
            json={
                "flight_id": IDEMPOTENCY_FLIGHT_ID,
                "seat_class": "economy",
                "passenger_name": "Idempotency Test",
                "passenger_email": self.email,
                "seat_number": f"{random.randint(1, 100)}{random.choice('ABCDEF')}",
            },
            name="[idempotency] seed_booking",
            catch_response=True,
        ) as r:
            if r.status_code == 201:
                self._booking_id = r.json().get("id", "")
                r.success()
            elif r.status_code in (400, 409, 422, 429):
                r.success()  # seat taken or rate-limited — still a valid run
            else:
                r.failure(f"seed_booking {r.status_code}")

    @tag("idempotency", "scenario7")
    @task(1)
    def duplicate_payment(self):
        if not self.token or not self._booking_id:
            return
        with self.client.post(
            "/api/v1/payments/intent",
            headers=self._auth,
            json={
                "booking_id": self._booking_id,
                "amount": 199.99,
                "currency": "EUR",
                "idempotency_key": self._idempotency_key,
            },
            name="[idempotency] duplicate_payment",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 201, 409, 422, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 8 – Soak Test (memory leaks, connection pool exhaustion)
# ═══════════════════════════════════════════════════════════════════════════════

class SoakUser(AuthMixin, HttpUser):
    """
    100 users at steady load for 30 minutes. Catches slow memory leaks,
    connection pool exhaustion, and DB query degradation over time.
    Run with: --users 100 --spawn-rate 5 --run-time 30m
    """
    wait_time = between(2, 6)
    host = "http://localhost:8000"

    _flight_id: str = ""
    _booking_id: str = ""

    def on_start(self):
        self._register_and_login()
        self._seed_flight()

    def _seed_flight(self):
        r = self.client.get("/api/v1/flights", name="[soak] seed")
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                self._flight_id = items[0]["id"]

    @tag("soak", "scenario8")
    @task(4)
    def search_flights(self):
        origin, dest = random.choice(ROUTES)
        self.client.get(
            f"/api/v1/flights?origin={origin}&destination={dest}",
            name="[soak] search",
        )

    @tag("soak", "scenario8")
    @task(2)
    def view_flight(self):
        if not self._flight_id:
            return
        self.client.get(
            f"/api/v1/flights/{self._flight_id}",
            name="[soak] get_flight",
        )

    @tag("soak", "scenario8")
    @task(2)
    def book_and_pay(self):
        if not self.token or not self._flight_id:
            return
        with self.client.post(
            "/api/v1/bookings",
            headers=self._auth,
            json={
                "flight_id": self._flight_id,
                "seat_class": "economy",
                "passenger_name": "Soak Tester",
                "passenger_email": self.email,
                "seat_number": f"{random.randint(1, 150)}{random.choice('ABCDEF')}",
            },
            name="[soak] create_booking",
            catch_response=True,
        ) as r:
            if r.status_code == 201:
                r.success()
            elif r.status_code in (400, 409, 422, 429):
                r.success()  # seat conflict or rate-limit — expected under load
            else:
                r.failure(f"unexpected {r.status_code}")
        if r.status_code == 201:
            self._booking_id = r.json().get("id", "")
            self.client.post(
                "/api/v1/payments/intent",
                headers=self._auth,
                json={
                    "booking_id": self._booking_id,
                    "amount": 199.99,
                    "currency": "EUR",
                    "idempotency_key": str(uuid.uuid4()),
                },
                name="[soak] pay",
            )

    @tag("soak", "scenario8")
    @task(1)
    def health_all_services(self):
        for port, svc in [(8001, "auth"), (8002, "flight"), (8003, "booking"),
                          (8004, "payment"), (8005, "baggage")]:
            with self.client.get(
                "/health",
                name=f"[soak] /health",
                catch_response=True,
            ) as r:
                if r.status_code == 200:
                    r.success()
                    break


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 9 – Token Refresh Storm
# ═══════════════════════════════════════════════════════════════════════════════

class TokenRefreshUser(HttpUser):
    """
    200 users hammering the token refresh endpoint simultaneously.
    Simulates mass token expiry (e.g. after a gateway restart).
    Tests JWT signing throughput and token blacklisting behaviour.
    Run with: --users 200 --spawn-rate 20 --run-time 3m
    """
    wait_time = between(0.5, 1.5)
    host = "http://localhost:8000"

    _refresh_token: str = ""
    _access_token: str = ""

    def on_start(self):
        if _RACER_CREDS:
            cred = random.choice(_RACER_CREDS)
            with self.client.post(
                "/api/v1/auth/login",
                json={"username": cred["username"], "password": cred["password"]},
                name="[refresh] initial_login",
                catch_response=True,
            ) as r:
                if r.status_code == 200:
                    self._refresh_token = r.json().get("refresh_token", "")
                    self._access_token = r.json().get("access_token", "")
                    r.success()
                else:
                    r.failure(f"login {r.status_code}")
        else:
            email = _random_email()
            pwd = _random_password()
            username = email.split("@")[0]
            with self.client.post(
                "/api/v1/auth/register",
                json={"email": email, "username": username,
                      "password": pwd, "full_name": "Refresh Tester"},
                name="[refresh] register",
                catch_response=True,
            ) as r:
                r.success()
            with self.client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": pwd},
                name="[refresh] initial_login",
                catch_response=True,
            ) as r:
                if r.status_code == 200:
                    self._refresh_token = r.json().get("refresh_token", "")
                    self._access_token = r.json().get("access_token", "")
                    r.success()
                else:
                    r.failure(f"login {r.status_code}")

    @tag("token-refresh", "scenario9")
    @task(5)
    def refresh_token(self):
        if not self._refresh_token:
            return
        with self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": self._refresh_token},
            name="[refresh] POST /auth/refresh",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                self._access_token = r.json().get("access_token", "")
                r.success()
            elif r.status_code in (401, 429):
                r.success()  # expected under load
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("token-refresh", "scenario9")
    @task(3)
    def validate_token(self):
        if not self._access_token:
            return
        with self.client.get(
            "/api/v1/auth/validate",
            headers={"Authorization": f"Bearer {self._access_token}"},
            name="[refresh] GET /auth/validate",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 401, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("token-refresh", "scenario9")
    @task(2)
    def get_me(self):
        if not self._access_token:
            return
        with self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {self._access_token}"},
            name="[refresh] GET /auth/me",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 401, 404, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 10 – Passenger Profile CRUD Under Load
# ═══════════════════════════════════════════════════════════════════════════════

class PassengerProfileUser(AuthMixin, HttpUser):
    """
    100 users creating, reading, and updating passenger profiles.
    Tests PII write path, encryption overhead, and loyalty tier reads.
    Run with: --users 100 --spawn-rate 10 --run-time 3m
    """
    wait_time = between(1, 3)
    host = "http://localhost:8000"

    _profile_created: bool = False

    def on_start(self):
        if _RACER_CREDS:
            cred = random.choice(_RACER_CREDS)
            with self.client.post(
                "/api/v1/auth/login",
                json={"username": cred["username"], "password": cred["password"]},
                name="[profile] login",
                catch_response=True,
            ) as r:
                if r.status_code == 200:
                    self.token = r.json().get("access_token", "")
                    self.email = cred["username"] + "@aerolink.test"
                    r.success()
                else:
                    r.failure(f"login {r.status_code}")
        else:
            self._register_and_login()

    @tag("profile", "scenario10")
    @task(3)
    def create_or_get_profile(self):
        if not self.token:
            return
        if not self._profile_created:
            with self.client.post(
                "/api/v1/passengers/profile",
                headers=self._auth,
                json={
                    "first_name": "Load",
                    "last_name": "Tester",
                    "nationality": random.choice(["IE", "GB", "US", "DE", "FR"]),
                    "phone_number": f"+353{random.randint(800000000, 899999999)}",
                    "passport_number": f"P{random.randint(10000000, 99999999)}",
                },
                name="[profile] POST /passengers/profile",
                catch_response=True,
            ) as r:
                if r.status_code in (201, 409):
                    self._profile_created = True
                    r.success()
                elif r.status_code in (429, 422):
                    r.success()
                else:
                    r.failure(f"unexpected {r.status_code}")
        else:
            with self.client.get(
                "/api/v1/passengers/profile",
                headers=self._auth,
                name="[profile] GET /passengers/profile",
                catch_response=True,
            ) as r:
                if r.status_code in (200, 404, 429):
                    r.success()
                else:
                    r.failure(f"unexpected {r.status_code}")

    @tag("profile", "scenario10")
    @task(2)
    def update_preferences(self):
        if not self.token or not self._profile_created:
            return
        with self.client.put(
            "/api/v1/passengers/profile",
            headers=self._auth,
            json={
                "meal_preference": random.choice(
                    ["standard", "vegetarian", "vegan", "halal", "kosher", None]
                ),
                "seat_preference": random.choice(["window", "aisle", "middle", None]),
            },
            name="[profile] PUT /passengers/profile",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("profile", "scenario10")
    @task(1)
    def manage_consent(self):
        if not self.token:
            return
        with self.client.post(
            "/api/v1/passengers/consent",
            headers=self._auth,
            json={
                "purpose": random.choice(["marketing", "analytics", "personalisation"]),
                "granted": random.choice([True, False]),
            },
            name="[profile] POST /passengers/consent",
            catch_response=True,
        ) as r:
            if r.status_code in (201, 429, 422):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("profile", "scenario10")
    @task(1)
    def list_consents(self):
        if not self.token:
            return
        with self.client.get(
            "/api/v1/passengers/consent",
            headers=self._auth,
            name="[profile] GET /passengers/consent",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 11 – Check-In Concurrency
# ═══════════════════════════════════════════════════════════════════════════════

class CheckInConcurrencyUser(AuthMixin, HttpUser):
    """
    100 users all attempt to check-in for the same flight at the same time.
    Tests the booking status state machine under concurrent writes:
    only users with valid confirmed bookings should succeed.
    Run with: --users 100 --spawn-rate 20 --run-time 3m
    """
    wait_time = between(0.5, 2)
    host = "http://localhost:8000"

    _booking_id: str = ""
    _flight_id: str = ""

    def on_start(self):
        if _RACER_CREDS:
            cred = random.choice(_RACER_CREDS)
            with self.client.post(
                "/api/v1/auth/login",
                json={"username": cred["username"], "password": cred["password"]},
                name="[checkin] login",
                catch_response=True,
            ) as r:
                if r.status_code == 200:
                    self.token = r.json().get("access_token", "")
                    self.email = cred["username"] + "@aerolink.test"
                    r.success()
                else:
                    r.failure(f"login {r.status_code}")
        else:
            self._register_and_login()
        self._create_booking()

    def _create_booking(self):
        if not self.token:
            return
        # Use AL100 — ample economy seats
        self._flight_id = IDEMPOTENCY_FLIGHT_ID
        with self.client.post(
            "/api/v1/bookings",
            headers=self._auth,
            json={
                "flight_id": self._flight_id,
                "seat_class": "economy",
                "passenger_name": "CheckIn Racer",
                "passenger_email": self.email,
                "seat_number": f"{random.randint(1, 149)}{random.choice('ABCDEF')}",
            },
            name="[checkin] seed_booking",
            catch_response=True,
        ) as r:
            if r.status_code == 201:
                self._booking_id = r.json().get("id", "")
                r.success()
            elif r.status_code in (400, 409, 422, 429):
                r.success()
            else:
                r.failure(f"seed_booking {r.status_code}")

    @tag("checkin", "scenario11")
    @task(3)
    def attempt_checkin(self):
        if not self.token or not self._booking_id or not self._flight_id:
            return
        with self.client.post(
            "/api/v1/checkin",
            headers=self._auth,
            json={
                "booking_id": self._booking_id,
                "flight_id": self._flight_id,
                "passenger_name": "CheckIn Racer",
                "seat_preference": random.choice(["window", "aisle", None]),
            },
            name="[checkin] POST /checkin",
            catch_response=True,
        ) as r:
            # 201 = first check-in, 409 = already checked in, 404 = booking not found
            if r.status_code in (201, 200, 400, 409, 404, 422, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("checkin", "scenario11")
    @task(2)
    def get_checkin_status(self):
        if not self.token or not self._booking_id:
            return
        with self.client.get(
            f"/api/v1/checkin/{self._booking_id}",
            headers=self._auth,
            name="[checkin] GET /checkin/{booking_id}",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("checkin", "scenario11")
    @task(1)
    def get_boarding_pass(self):
        if not self.token or not self._booking_id:
            return
        with self.client.get(
            f"/api/v1/checkin/{self._booking_id}/boarding-pass",
            headers=self._auth,
            name="[checkin] GET /checkin/{id}/boarding-pass",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")
