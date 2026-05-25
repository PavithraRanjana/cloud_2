"""
AeroLink Stress Testing Suite
==============================
Goal: find the breaking point of each service by ramping load until failures
appear, then verify the system recovers.

Scenarios
---------
  StressFlightSearch   – ramp to 2000 users; find flight-service / DB limit
  StressAuth           – concurrent bcrypt; find auth-service saturation point
  StressBooking        – concurrent writes; find booking-service / Postgres limit
  StressPayment        – payment intent storm; find payment-service limit
  StressMixed          – all services simultaneously at 2× normal load
  StressRecovery       – spike to 1000 then drop to 0, measure recovery

Run individual scenarios:
  python3.10 -m locust -f tests/load/stress_test.py StressFlightSearch \
      --host http://localhost:8000 --headless -u 2000 -r 100 -t 5m
  python3.10 -m locust -f tests/load/stress_test.py StressAuth \
      --host http://localhost:8000 --headless -u 300 -r 50 -t 3m
  python3.10 -m locust -f tests/load/stress_test.py StressBooking \
      --host http://localhost:8000 --headless -u 500 -r 50 -t 3m
  python3.10 -m locust -f tests/load/stress_test.py StressPayment \
      --host http://localhost:8000 --headless -u 200 -r 20 -t 3m
  python3.10 -m locust -f tests/load/stress_test.py StressMixed \
      --host http://localhost:8000 --headless -u 1000 -r 50 -t 5m
  python3.10 -m locust -f tests/load/stress_test.py StressRecovery \
      --host http://localhost:8000 --headless -u 1000 -r 1000 -t 3m
"""

import json as _json
import random
import string
import uuid

from locust import HttpUser, between, events, task, tag

# ── Pre-seeded credentials (avoids bcrypt bottleneck in non-auth stress tests) ─

try:
    _CREDS = _json.load(open("/tmp/racer_creds.json"))
except FileNotFoundError:
    _CREDS = []

ROUTES = [
    ("DUB", "LHR"), ("LHR", "JFK"), ("JFK", "LAX"),
    ("DUB", "CDG"), ("CDG", "FCO"), ("LAX", "ORD"),
    ("JFK", "DUB"), ("LHR", "DXB"), ("DXB", "SIN"),
]

FLIGHT_ID = "19dc2b3d-e36d-4ace-af2d-c8fcb5d4e27b"  # AL100 — seeded flight


def _rnd(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _login(client, cred):
    """Login with a pre-seeded credential; return token or ''."""
    r = client.post(
        "/api/v1/auth/login",
        json={"username": cred["username"], "password": cred["password"]},
        name="[stress] login",
        catch_response=True,
    )
    with r:
        if r.status_code == 200:
            r.success()
            return r.json().get("access_token", "")
        r.failure(f"login {r.status_code}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# STRESS 1 – Flight Search  (target: 2000 users, find DB connection ceiling)
# ═══════════════════════════════════════════════════════════════════════════════

class StressFlightSearch(HttpUser):
    """
    Ramps to 2000 concurrent users hitting the flight-service read path.
    No auth required. Identifies when the Postgres connection pool or the
    flight-service worker queue becomes the bottleneck.
    Target: find the user count where p95 latency exceeds 5 s or errors appear.
    Run: -u 2000 -r 100 -t 5m
    """
    wait_time = between(0.1, 0.5)
    host = "http://localhost:8000"

    @tag("stress", "flight")
    @task(5)
    def search_route(self):
        origin, dest = random.choice(ROUTES)
        with self.client.get(
            f"/api/v1/flights?origin={origin}&destination={dest}",
            name="[stress-flight] search",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "flight")
    @task(3)
    def list_all(self):
        with self.client.get(
            "/api/v1/flights",
            name="[stress-flight] list_all",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "flight")
    @task(2)
    def get_flight(self):
        with self.client.get(
            f"/api/v1/flights/{FLIGHT_ID}",
            name="[stress-flight] get_by_id",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "health")
    @task(1)
    def health(self):
        with self.client.get(
            "/health",
            name="[stress-flight] health",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# STRESS 2 – Auth Service  (target: find bcrypt saturation point)
# ═══════════════════════════════════════════════════════════════════════════════

class StressAuth(HttpUser):
    """
    Hammers the auth service with concurrent logins using pre-seeded creds.
    Pure bcrypt-verify load — no registration overhead.
    Identifies the concurrency at which bcrypt queuing causes 504 timeouts.
    Run: -u 300 -r 50 -t 3m
    """
    wait_time = between(0.5, 2)
    host = "http://localhost:8000"

    _token: str = ""
    _refresh: str = ""

    def on_start(self):
        if _CREDS:
            cred = random.choice(_CREDS)
            self._token = _login(self.client, cred)

    @tag("stress", "auth")
    @task(4)
    def login_storm(self):
        if not _CREDS:
            return
        cred = random.choice(_CREDS)
        with self.client.post(
            "/api/v1/auth/login",
            json={"username": cred["username"], "password": cred["password"]},
            name="[stress-auth] login",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                self._token = r.json().get("access_token", "")
                r.success()
            elif r.status_code in (429, 503):
                r.success()  # rate-limited — expected under extreme load
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "auth")
    @task(3)
    def validate_token(self):
        if not self._token:
            return
        with self.client.get(
            "/api/v1/auth/validate",
            headers={"Authorization": f"Bearer {self._token}"},
            name="[stress-auth] validate",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 401, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "auth")
    @task(2)
    def get_me(self):
        if not self._token:
            return
        with self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {self._token}"},
            name="[stress-auth] me",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 401, 404, 429):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "auth")
    @task(1)
    def register_new(self):
        """Occasional new registrations to stress bcrypt hashing."""
        email = f"stress_{_rnd()}@aerolink.test"
        username = f"stress_{_rnd()}"
        with self.client.post(
            "/api/v1/auth/register",
            json={
                "email": email, "username": username,
                "password": "Stress@99999", "full_name": "Stress Tester",
            },
            name="[stress-auth] register",
            catch_response=True,
        ) as r:
            if r.status_code in (201, 409, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# STRESS 3 – Booking Service  (target: 500 concurrent write ops)
# ═══════════════════════════════════════════════════════════════════════════════

class StressBooking(HttpUser):
    """
    500 users creating bookings concurrently using pre-seeded tokens.
    Tests Postgres write throughput, row-level locking, and saga compensation.
    Expect 409s (seat conflict) to rise as seats run out — that is correct behaviour.
    Run: -u 500 -r 50 -t 3m
    """
    wait_time = between(0.2, 1)
    host = "http://localhost:8000"

    _token: str = ""
    _email: str = ""
    _booking_id: str = ""

    def on_start(self):
        if _CREDS:
            cred = random.choice(_CREDS)
            self._token = _login(self.client, cred)
            self._email = cred["username"] + "@aerolink.test"

    @property
    def _auth(self):
        return {"Authorization": f"Bearer {self._token}"}

    @tag("stress", "booking")
    @task(5)
    def create_booking(self):
        if not self._token:
            return
        with self.client.post(
            "/api/v1/bookings",
            headers=self._auth,
            json={
                "flight_id": FLIGHT_ID,
                "seat_class": random.choice(["economy", "business"]),
                "passenger_name": "Stress Tester",
                "passenger_email": self._email,
                "seat_number": f"{random.randint(1, 149)}{random.choice('ABCDEF')}",
            },
            name="[stress-booking] create",
            catch_response=True,
        ) as r:
            if r.status_code == 201:
                self._booking_id = r.json().get("id", "")
                r.success()
            elif r.status_code in (400, 409, 422, 429, 503):
                r.success()  # seat conflict or rate-limit — expected
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "booking")
    @task(3)
    def list_bookings(self):
        if not self._token:
            return
        with self.client.get(
            "/api/v1/bookings",
            headers=self._auth,
            name="[stress-booking] list",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "booking")
    @task(2)
    def cancel_booking(self):
        if not self._token or not self._booking_id:
            return
        with self.client.post(
            f"/api/v1/bookings/{self._booking_id}/cancel",
            headers=self._auth,
            name="[stress-booking] cancel",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 204, 404, 409, 422, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# STRESS 4 – Payment Service  (target: 200 concurrent payment intents)
# ═══════════════════════════════════════════════════════════════════════════════

class StressPayment(HttpUser):
    """
    200 users hammering the payment intent endpoint simultaneously.
    Tests Stripe client pool, idempotency key deduplication under stress,
    and payment-service DB write throughput.
    Run: -u 200 -r 20 -t 3m
    """
    wait_time = between(0.1, 0.5)
    host = "http://localhost:8000"

    _token: str = ""
    _email: str = ""
    _booking_id: str = ""
    _idempotency_key: str = ""

    def on_start(self):
        if _CREDS:
            cred = random.choice(_CREDS)
            self._token = _login(self.client, cred)
            self._email = cred["username"] + "@aerolink.test"
            self._idempotency_key = str(uuid.uuid4())
            self._seed_booking()

    def _seed_booking(self):
        if not self._token:
            return
        with self.client.post(
            "/api/v1/bookings",
            headers={"Authorization": f"Bearer {self._token}"},
            json={
                "flight_id": FLIGHT_ID,
                "seat_class": "economy",
                "passenger_name": "Payment Stress",
                "passenger_email": self._email,
                "seat_number": f"{random.randint(1, 149)}{random.choice('ABCDEF')}",
            },
            name="[stress-payment] seed_booking",
            catch_response=True,
        ) as r:
            if r.status_code == 201:
                self._booking_id = r.json().get("id", "")
                r.success()
            elif r.status_code in (400, 409, 422, 429):
                r.success()
            else:
                r.failure(f"seed {r.status_code}")

    @property
    def _auth(self):
        return {"Authorization": f"Bearer {self._token}"}

    @tag("stress", "payment")
    @task(6)
    def payment_intent(self):
        if not self._token or not self._booking_id:
            return
        with self.client.post(
            "/api/v1/payments/intent",
            headers=self._auth,
            json={
                "booking_id": self._booking_id,
                "amount": round(random.uniform(50, 900), 2),
                "currency": "EUR",
                "idempotency_key": self._idempotency_key,
            },
            name="[stress-payment] intent",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 201, 409, 422, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "payment")
    @task(2)
    def get_payment_config(self):
        with self.client.get(
            "/api/v1/payments/config",
            headers=self._auth,
            name="[stress-payment] config",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 401, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "payment")
    @task(2)
    def get_booking_payment(self):
        if not self._token or not self._booking_id:
            return
        with self.client.get(
            f"/api/v1/payments/booking/{self._booking_id}",
            headers=self._auth,
            name="[stress-payment] by_booking",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# STRESS 5 – Mixed Full-Stack  (all services at 2× normal load)
# ═══════════════════════════════════════════════════════════════════════════════

class StressMixed(HttpUser):
    """
    1000 users hitting all services simultaneously at roughly 2× the intended
    load for each scenario. Tests cross-service contention: DB connection pool
    shared across services, gateway proxy queue, Redis cache.
    Run: -u 1000 -r 50 -t 5m
    """
    wait_time = between(0.2, 1)
    host = "http://localhost:8000"

    _token: str = ""
    _email: str = ""
    _booking_id: str = ""
    _flight_id: str = FLIGHT_ID

    def on_start(self):
        if _CREDS:
            cred = random.choice(_CREDS)
            self._token = _login(self.client, cred)
            self._email = cred["username"] + "@aerolink.test"

    @property
    def _auth(self):
        return {"Authorization": f"Bearer {self._token}"}

    @tag("stress", "mixed", "flight")
    @task(5)
    def search_flights(self):
        origin, dest = random.choice(ROUTES)
        with self.client.get(
            f"/api/v1/flights?origin={origin}&destination={dest}",
            name="[stress-mixed] flight_search",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "mixed", "booking")
    @task(3)
    def create_booking(self):
        if not self._token:
            return
        with self.client.post(
            "/api/v1/bookings",
            headers=self._auth,
            json={
                "flight_id": self._flight_id,
                "seat_class": "economy",
                "passenger_name": "Mixed Stress",
                "passenger_email": self._email,
                "seat_number": f"{random.randint(1, 149)}{random.choice('ABCDEF')}",
            },
            name="[stress-mixed] create_booking",
            catch_response=True,
        ) as r:
            if r.status_code == 201:
                self._booking_id = r.json().get("id", "")
                r.success()
            elif r.status_code in (400, 409, 422, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "mixed", "payment")
    @task(2)
    def payment_intent(self):
        if not self._token or not self._booking_id:
            return
        with self.client.post(
            "/api/v1/payments/intent",
            headers=self._auth,
            json={
                "booking_id": self._booking_id,
                "amount": 199.99,
                "currency": "EUR",
                "idempotency_key": str(uuid.uuid4()),
            },
            name="[stress-mixed] payment_intent",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 201, 400, 409, 422, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "mixed", "baggage")
    @task(2)
    def track_baggage(self):
        if not self._token:
            return
        with self.client.get(
            f"/api/v1/baggage/BAG-{random.randint(1000000000, 9999999999)}",
            headers=self._auth,
            name="[stress-mixed] baggage_track",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "mixed", "profile")
    @task(1)
    def get_profile(self):
        if not self._token:
            return
        with self.client.get(
            "/api/v1/passengers/profile",
            headers=self._auth,
            name="[stress-mixed] passenger_profile",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "mixed", "health")
    @task(1)
    def health(self):
        with self.client.get(
            "/health",
            name="[stress-mixed] health",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# STRESS 6 – Recovery  (spike to 1000 then observe how fast system recovers)
# ═══════════════════════════════════════════════════════════════════════════════

class StressRecovery(HttpUser):
    """
    All 1000 users arrive instantly (spawn-rate=1000).
    Tests whether the gateway queues requests gracefully (429/503) rather than
    crashing, and whether the system returns to normal latency within seconds
    of the spike subsiding (the 3-minute run-time acts as the measurement window).
    Run: -u 1000 -r 1000 -t 3m
    """
    wait_time = between(0.05, 0.2)
    host = "http://localhost:8000"

    @tag("stress", "recovery")
    @task(7)
    def hit_flight_search(self):
        origin, dest = random.choice(ROUTES)
        with self.client.get(
            f"/api/v1/flights?origin={origin}&destination={dest}",
            name="[stress-recovery] flight_search",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "recovery")
    @task(2)
    def hit_health(self):
        with self.client.get(
            "/health",
            name="[stress-recovery] health",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")

    @tag("stress", "recovery")
    @task(1)
    def hit_list_flights(self):
        with self.client.get(
            "/api/v1/flights",
            name="[stress-recovery] list_flights",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 429, 503):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}")
