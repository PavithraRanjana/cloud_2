# AeroLink — Airline Booking Microservices Platform

A cloud-native airline booking system built with FastAPI microservices, demonstrating distributed systems patterns including the Saga pattern, CQRS, circuit breakers, event-driven architecture, and JWT-based RBAC.

---

## Architecture Overview

AeroLink is composed of **9 services** orchestrated via Docker Compose, backed by PostgreSQL, Redis, and AWS services emulated locally via LocalStack.

```
Client → API Gateway (:8000)
           ├── auth-service        :8001  JWT auth, bcrypt, Cognito
           ├── flight-service      :8002  CQRS, optimistic locking, Redis cache
           ├── booking-service     :8003  Saga, distributed seat lock, circuit breaker
           ├── payment-service     :8004  Stripe, idempotency, webhook validation
           ├── baggage-service     :8005  Tag generation, status tracking
           ├── checkin-service     :8006  Seat assignment, PDF boarding passes
           ├── passenger-service   :8007  Encryption, GDPR, loyalty tiers
           └── notification-service :8008  SQS long-poll, SES email, dedup
```

All services share a single PostgreSQL database (tables per service) and a single Redis instance (separate logical DB per service).

### Architecture Diagrams

| Diagram | Description |
|---|---|
| [`diagrams/01_system_overview.png`](diagrams/01_system_overview.png) | Full system — services, data layer, AWS, Stripe, SES |
| [`diagrams/02_service_communication.png`](diagrams/02_service_communication.png) | All synchronous HTTP calls between services |
| [`diagrams/03_event_driven_architecture.png`](diagrams/03_event_driven_architecture.png) | EventBridge → SQS → notification, Lambda, DLQ |
| [`diagrams/04_booking_saga.png`](diagrams/04_booking_saga.png) | 3-phase booking saga + compensating transactions |
| [`diagrams/05_infrastructure.png`](diagrams/05_infrastructure.png) | Docker containers, Redis DB mapping, LocalStack |

---

## Key Patterns Implemented

| Pattern | Where |
|---|---|
| **Saga** (choreography) | Booking → Payment → Check-in with compensation on failure |
| **CQRS** | Flight search reads from Redis cache; writes go to PostgreSQL |
| **Circuit Breaker** | All inter-service HTTP calls via `pybreaker` (fail_max=5, reset=30s) |
| **Retry with backoff** | `tenacity` — 3 attempts, exponential backoff + jitter |
| **Optimistic locking** | Flight seat updates use a `version` column to prevent double-booking |
| **Distributed lock** | Redis `SET NX` (15 s TTL) guards seat reservation during booking creation |
| **Idempotency** | Payment intents keyed by `idempotency_key` (Redis + DB) |
| **Event-driven** | EventBridge → SQS → notification-service for all domain events |
| **RBAC** | Roles: `passenger`, `admin`, `airline-staff`, `airport-operator`, `partner-api` |
| **GDPR** | Right-to-erasure cascade across booking, notification, and passenger services |
| **Encryption** | Passport numbers encrypted at rest (passenger-service) |
| **Audit log** | Immutable audit table for payment and GDPR operations |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Compose v2)
- Python 3.10 (for running tests and load tests locally)
- `awscli` — for inspecting LocalStack resources (`pip install awscli`)

---

## Quick Start

### 1. Clone and start all services

```bash
git clone https://github.com/PavithraRanjana/cloud_2.git
cd cloud_2
docker-compose up -d
```

First boot takes ~2 minutes. LocalStack initialises EventBridge, SQS, S3, DynamoDB, Lambda, and Cognito automatically via `infrastructure/localstack/init-aws.sh`.

### 2. Verify everything is healthy

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy", "services": {...}}
```

### 3. Register and log in

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","username":"you","password":"Test123!","full_name":"Your Name"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"you","password":"Test123!"}'
```

Save the `access_token` from the login response for authenticated requests.

---

## Service Ports

| Service | Port | Purpose |
|---|---|---|
| API Gateway | 8000 | Single entry point — JWT validation, routing |
| Auth Service | 8001 | Register, login, refresh, validate |
| Flight Service | 8002 | Search, list, manage flights |
| Booking Service | 8003 | Create, cancel, list bookings |
| Payment Service | 8004 | Payment intents, Stripe webhook, refunds |
| Baggage Service | 8005 | Register baggage, track by tag |
| Check-in Service | 8006 | Check in, boarding pass (HTML + PDF) |
| Passenger Service | 8007 | Profile, loyalty points, GDPR consent |
| Notification Service | 8008 | Email notifications, DLQ management |
| PostgreSQL | 5432 | Shared relational database |
| Redis | 6379 | Cache + distributed locks (8 logical DBs) |
| LocalStack | 4566 | AWS services emulation |

---

## API Reference

The full OpenAPI specification is in [`OpenAPI/openapi.json`](OpenAPI/openapi.json).

You can browse it interactively at:
- **Swagger UI:** `http://localhost:800{N}/docs` on any individual service port
- **ReDoc:** `http://localhost:800{N}/redoc`

### Core endpoints

```
POST   /api/v1/auth/register           Register a new user
POST   /api/v1/auth/login              Obtain access + refresh tokens
POST   /api/v1/auth/refresh            Refresh an access token
GET    /api/v1/auth/me                 Current user info

GET    /api/v1/flights                 Search flights (origin, destination, date, cabin_class)
GET    /api/v1/flights/{id}            Flight details

POST   /api/v1/bookings                Create a booking (triggers saga)
GET    /api/v1/bookings                List my bookings
GET    /api/v1/bookings/{id}           Booking details
POST   /api/v1/bookings/{id}/cancel    Cancel booking (releases seats)

GET    /api/v1/payments/config         Stripe publishable key
POST   /api/v1/payments/intent         Create a payment intent
POST   /api/v1/payments/stripe/webhook Stripe event webhook
POST   /api/v1/payments/{id}/refund    Refund a payment

POST   /api/v1/checkin                 Check in for a flight
GET    /api/v1/checkin/{booking_id}/boarding-pass      HTML boarding pass
GET    /api/v1/checkin/{booking_id}/boarding-pass/pdf  PDF boarding pass

POST   /api/v1/baggage                 Register baggage
GET    /api/v1/baggage/{tag_number}    Track baggage by tag
GET    /api/v1/baggage/booking/{id}    All baggage for a booking

GET    /api/v1/passengers/profile      Get passenger profile
POST   /api/v1/passengers/profile      Create profile
PUT    /api/v1/passengers/profile      Update profile
POST   /api/v1/passengers/consent      Record GDPR consent

GET    /api/v1/notifications           My notifications
PATCH  /api/v1/notifications/{id}/read Mark as read
```

---

## Running Tests

```bash
# Create and activate virtual environment
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Unit + Integration tests

```bash
pytest tests/unit/ tests/integration/ -v
```

- **363 tests** — 0 failures
- **90.5% code coverage** (threshold: 80%)
- Coverage report generated at `reports/coverage_html/index.html`

### Load tests (requires running Docker stack)

```bash
cd tests/load

# Run a specific scenario
locust -f locustfile.py FlightSearchUser --headless -u 50 -r 5 -t 2m

# All 11 scenarios (see locustfile.py for full list)
locust -f locustfile.py AuthUser            --headless -u 20  -r 5  -t 2m
locust -f locustfile.py FlightSearchUser    --headless -u 100 -r 10 -t 3m
locust -f locustfile.py BookingUser         --headless -u 30  -r 5  -t 3m
locust -f locustfile.py PaymentUser         --headless -u 20  -r 5  -t 2m
locust -f locustfile.py BaggageTrackingUser --headless -u 50  -r 10 -t 2m
locust -f locustfile.py CheckInUser         --headless -u 30  -r 5  -t 2m
locust -f locustfile.py PassengerUser       --headless -u 20  -r 5  -t 2m
locust -f locustfile.py NotificationUser    --headless -u 30  -r 5  -t 2m
locust -f locustfile.py TokenRefreshUser    --headless -u 50  -r 10 -t 2m
locust -f locustfile.py SoakUser            --headless -u 20  -r 2  -t 30m
locust -f locustfile.py EndToEndUser        --headless -u 10  -r 1  -t 5m
```

HTML reports are written to `tests/load/reports/`.

### Stress tests (breaking-point analysis)

```bash
cd tests/load

locust -f stress_test.py StressFlightSearch --headless -u 2000 -r 100 -t 5m
locust -f stress_test.py StressAuth         --headless -u 300  -r 50  -t 3m
locust -f stress_test.py StressBooking      --headless -u 500  -r 50  -t 3m
locust -f stress_test.py StressPayment      --headless -u 200  -r 20  -t 3m
locust -f stress_test.py StressMixed        --headless -u 1000 -r 50  -t 5m
locust -f stress_test.py StressRecovery     --headless -u 1000 -r 1000 -t 3m
```

#### Stress test results summary

| Scenario | Users | Failure rate | Notes |
|---|---|---|---|
| StressFlightSearch | 2,000 | 0% | Flight service never errors; Postgres queues all requests |
| StressAuth | 300 | 1.9% | bcrypt at rounds=10 + async thread pool; p50 login ~12 s |
| StressBooking | 500 | 0% | Optimistic locking handles concurrency cleanly |
| StressPayment | 200 | 0.6% | ~19 connection resets at extreme load |
| StressMixed | 1,000 | 0% | All business operations stable |
| StressRecovery | 1,000 | 0% | Spike load queued and processed without errors |

---

## AWS Services (LocalStack)

All AWS services run locally via LocalStack. The following resources are provisioned automatically on first boot:

| Resource | Name / Config |
|---|---|
| EventBridge bus | `aerolink-events` |
| EventBridge rules | 10 rules routing domain events to SQS |
| SQS queue | `aerolink-notifications` |
| SQS DLQ | `aerolink-notifications-dlq` (maxReceiveCount=3) |
| S3 bucket | `aerolink-documents` (boarding pass PDFs) |
| DynamoDB table | `payment-idempotency` |
| Lambda | `boarding-pass-generator` — PDF on CheckInCompleted |
| Lambda | `pricing-recalculation` — dynamic pricing every 5 min |
| Lambda | `notification-dispatch` — utility/debug |
| Cognito User Pool | `aerolink-local` (groups: passenger, admin) |
| IAM Role | `lambda-execution-role` |

---

## Environment Variables

Key variables (set in `docker-compose.yml`):

| Variable | Default | Purpose |
|---|---|---|
| `JWT_SECRET` | `aerolink-jwt-secret-key-change-in-production` | HS256 signing key |
| `COGNITO_USER_POOL_ID` | *(set by LocalStack init)* | Enables RS256 Cognito validation |
| `STRIPE_SECRET_KEY` | `sk_test_...` | Stripe test key |
| `INTERNAL_API_KEY` | `aerolink-internal-dev-key` | Service-to-service auth |
| `ENABLE_SQS_POLLING` | `true` | Enables notification-service SQS consumer |

---

## Project Structure

```
cloud_2/
├── api-gateway/              API Gateway (FastAPI reverse proxy)
├── services/
│   ├── auth-service/
│   ├── flight-service/
│   ├── booking-service/
│   ├── payment-service/
│   ├── baggage-service/
│   ├── checkin-service/
│   ├── passenger-service/
│   └── notification-service/
├── shared/                   Shared library (auth, DB, events, resilience, …)
├── lambdas/
│   ├── boarding-pass-generator/
│   ├── pricing-recalculation/
│   └── notification-dispatch/
├── infrastructure/
│   └── localstack/init-aws.sh   AWS resource provisioning script
├── tests/
│   ├── unit/                 Service-level tests with mocked dependencies
│   ├── integration/          Multi-service tests via httpx transport bridge
│   └── load/                 Locust load + stress test scenarios
├── diagrams/                 Architecture diagrams (PNG + Python source)
├── OpenAPI/                  OpenAPI specifications per service
├── frontend/                 React frontend (Vite)
└── docker-compose.yml
```

---

## Estimated AWS Cost (Production)

For a low-traffic deployment (manual testing + demo):

| Approach | Monthly cost |
|---|---|
| Single EC2 t3.medium (docker-compose, all-in-one) | ~$33 |
| Managed services (EC2 t3.small + RDS + ElastiCache) | ~$44 |

All usage-based AWS services (SQS, EventBridge, Lambda, S3, DynamoDB, Cognito, SES) fall within the free tier at this traffic level.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI 0.136, Pydantic v2, Uvicorn |
| Database | PostgreSQL 15, SQLAlchemy 2.0 (async), asyncpg |
| Cache / locks | Redis 7, redis-py |
| Auth | python-jose (JWT HS256/RS256), passlib + bcrypt (rounds=10) |
| Resilience | pybreaker (circuit breaker), tenacity (retry) |
| Events | boto3, EventBridge + SQS |
| Payment | stripe-python |
| PDF generation | fpdf2 |
| Testing | pytest, pytest-asyncio, Locust |
| Containerisation | Docker Compose |
| AWS emulation | LocalStack |
