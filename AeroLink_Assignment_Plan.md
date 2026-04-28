# AeroLink Assignment — Master Plan for 80%+ Grade

## Assessment Weight Breakdown & Target Strategy

| Component | Weight | Target | What Markers Want |
|---|---|---|---|
| Architecture Design | 20% | 85%+ | Professional diagrams, justified decisions, cloud-native patterns |
| Implementation | 40% | 80%+ | Working microservices, clean code, real cloud integration |
| Testing & Results | 20% | 80%+ | Automated tests, load testing with metrics, clear analysis |
| Presentation & Viva | 20% | 80%+ | Confident demo, deep technical understanding, Q&A readiness |

---

## Phase 1: Architecture & Design (Weeks 1–2)

### Task 1 — Cloud-Based Web Application Design

**Goal:** Produce a professional-grade architecture document with diagrams that demonstrate deep understanding of cloud-native patterns.

**Actions:**

1. **Define the microservices** — split the AeroLink monolith into these bounded contexts:
   - `flight-service` — flight schedules, routes, pricing
   - `booking-service` — reservations, ticketing, seat selection
   - `checkin-service` — passenger check-in, boarding passes
   - `baggage-service` — baggage tracking, status updates
   - `passenger-service` — passenger profiles, loyalty, preferences
   - `payment-service` — payment processing, refunds (PCI-DSS scope)
   - `notification-service` — email, SMS, push notifications
   - `gateway-service` — API gateway, routing, rate limiting
   - `auth-service` — authentication, authorization, token management

2. **Create architectural diagrams** (use draw.io, Lucidchart, or PlantUML):
   - **High-level system architecture** — show all microservices, databases, message brokers, API gateway, CDN, load balancers, and external integrations (airports, immigration, payment providers)
   - **AWS deployment diagram** — map each service to specific AWS services: ECS/EKS for containers, Aurora for relational data, DynamoDB for NoSQL, ElastiCache for caching, SQS/SNS/EventBridge for messaging, CloudFront for CDN, Route 53 for DNS
   - **Multi-region deployment diagram** — show active-active across at least 2 AWS regions (e.g., eu-west-1 and ap-southeast-1) with Global Accelerator, cross-region replication, and failover routing
   - **Data flow diagram** — trace a full booking request from the passenger's browser through the gateway, booking service, payment service, notification service, and back
   - **Container orchestration diagram** — show Kubernetes cluster layout with namespaces per service, pod auto-scaling, and service mesh (Istio or AWS App Mesh)

3. **Justify every technology choice** by mapping it to a specific AeroLink requirement:
   - High availability → multi-AZ deployments, health checks, auto-scaling groups
   - Global scalability → multi-region, CloudFront CDN, read replicas
   - Fault tolerance → circuit breakers, retry policies, dead letter queues
   - Real-time sync → EventBridge + SNS fan-out pattern

4. **Include a serverless component** — use AWS Lambda for:
   - Notification dispatch (triggered by SNS/SQS events)
   - Scheduled flight pricing recalculation (triggered by CloudWatch Events)
   - PDF boarding pass generation (triggered by check-in completion event)

**Deliverable:** 8–12 pages of architecture documentation with 5+ professional diagrams.

---

### Task 2 — Distributed Web Application & API Design

**Goal:** Design and document a clean, production-grade API layer with proper gateway routing and event-driven communication.

**Actions:**

1. **Design the API Gateway layer** — use Amazon API Gateway or Kong:
   - Define route table: `/api/v1/flights`, `/api/v1/bookings`, `/api/v1/checkin`, `/api/v1/baggage`
   - Configure rate limiting per client (e.g., 1000 req/min for partner APIs, 100 req/min for public)
   - Add request validation, CORS policies, and API key management
   - Set up JWT validation at the gateway level before routing to services

2. **Design RESTful APIs** for each microservice — for each, define:
   - Endpoints (GET, POST, PUT, DELETE with resource paths)
   - Request/response schemas with clear data contracts
   - HTTP status codes and error response format
   - Pagination strategy (cursor-based for large datasets like flight search results)

3. **Design the event-driven layer** using AWS EventBridge + SQS:
   - Define domain events: `BookingCreated`, `PaymentProcessed`, `CheckInCompleted`, `BaggageStatusChanged`, `FlightScheduleUpdated`, `SeatAvailabilityChanged`
   - Map producers and consumers: e.g., `booking-service` emits `BookingCreated` → consumed by `notification-service`, `baggage-service`, `flight-service` (to update seat count)
   - Design dead-letter queues for failed event processing
   - Document event schemas in AsyncAPI format

4. **Write OpenAPI/Swagger specification** — create a complete `openapi.yaml` covering at minimum the flight-service and booking-service endpoints with schemas, security definitions, and example payloads.

5. **Secure service-to-service communication:**
   - Internal: mTLS via service mesh (Istio) or AWS App Mesh
   - External: HTTPS with API keys + OAuth 2.0 bearer tokens
   - Service discovery: AWS Cloud Map or Kubernetes DNS

**Deliverable:** Full OpenAPI spec, event schema documentation, API gateway configuration, service communication diagrams.

---

### Task 3 — Data Security, Compliance & Consistency

**Goal:** Demonstrate enterprise-grade security thinking and a solid understanding of distributed data challenges.

**Actions:**

1. **Encryption strategy:**
   - At rest: AWS KMS-managed keys for Aurora (AES-256), S3 bucket encryption, DynamoDB encryption, EBS volume encryption
   - In transit: TLS 1.3 everywhere — ALB termination, mTLS between services, encrypted EventBridge payloads for PII
   - Application-level: encrypt PCI-sensitive fields (card numbers) with field-level encryption before storing

2. **Authentication & Authorization flow:**
   - Implement OAuth 2.0 with Authorization Code flow for passenger-facing apps
   - Use JWT access tokens (short-lived, 15 min) + refresh tokens (long-lived, 7 days)
   - Define RBAC roles: `passenger`, `airline-staff`, `airport-operator`, `admin`, `partner-api`
   - Implement ABAC (attribute-based) for fine-grained rules: e.g., airport staff can only access data for their assigned airport
   - Use AWS Cognito or Keycloak as the identity provider

3. **GDPR compliance design:**
   - Data classification: PII fields tagged in schemas
   - Right to erasure: design a `gdpr-service` or use a saga to propagate deletion across services
   - Data minimization: only collect necessary passenger data
   - Consent management: track and enforce consent per data processing purpose
   - Data residency: EU passenger data stays in eu-west-1 using region-aware routing

4. **PCI-DSS compliance:**
   - Isolate the payment-service in a separate VPC subnet with restricted security groups
   - Use a tokenization provider (Stripe, Adyen) so AeroLink never stores raw card numbers
   - Audit logging for all payment operations
   - Network segmentation diagrams showing PCI scope boundary

5. **Data consistency strategy — use the Saga pattern (choreography-based):**
   - Example saga: Create Booking → Reserve Seat → Process Payment → Issue Ticket
   - If payment fails → compensating transaction: Release Seat → Cancel Booking
   - Implement with EventBridge events triggering each step
   - Justify eventual consistency: booking confirmation can tolerate 1–2 second delay; seat availability uses optimistic locking to prevent double-booking
   - Discuss where strong consistency is needed (payment processing) vs. eventual (notification delivery, analytics)

6. **Implement CQRS** for the flight-service:
   - Write model: normalized relational data in Aurora (flight schedules, pricing rules)
   - Read model: denormalized views in DynamoDB or ElastiCache for fast search queries
   - Sync via domain events: `FlightScheduleUpdated` triggers read model rebuild

**Deliverable:** Security architecture document, data flow with encryption points marked, RBAC matrix, saga diagrams, CQRS explanation with diagrams.

---

## Phase 2: Implementation (Weeks 3–5)

### Technology Stack

| Layer | Technology | Justification |
|---|---|---|
| Language | Python (FastAPI) or Node.js (Express/NestJS) | Rapid development, strong AWS SDK support |
| Containerization | Docker + docker-compose (local), ECS/EKS (cloud) | Industry standard, portable |
| API Gateway | Amazon API Gateway or Kong (local) | Managed, scalable, built-in auth |
| Databases | PostgreSQL (Aurora-compatible), DynamoDB (local via LocalStack) | Relational + NoSQL as needed |
| Message Broker | AWS SQS/SNS or RabbitMQ (local) | Event-driven communication |
| Auth | Keycloak (local) or AWS Cognito | OAuth 2.0, JWT, RBAC out of the box |
| Caching | Redis (ElastiCache-compatible) | Session store, read-through cache |
| Monitoring | Prometheus + Grafana (local), CloudWatch (cloud) | Metrics, logging, tracing |

### Implementation Priorities (highest-mark-impact first)

**Week 3 — Core Services**

1. Set up the project mono-repo structure:
   ```
   aerolink/
   ├── services/
   │   ├── flight-service/
   │   ├── booking-service/
   │   ├── checkin-service/
   │   ├── baggage-service/
   │   ├── passenger-service/
   │   ├── payment-service/
   │   ├── notification-service/
   │   └── auth-service/
   ├── api-gateway/
   ├── infrastructure/
   │   ├── docker-compose.yml
   │   ├── kubernetes/
   │   └── terraform/
   ├── docs/
   │   ├── openapi/
   │   └── architecture/
   └── tests/
   ```

2. Implement `flight-service`:
   - CRUD endpoints for flights, routes, schedules
   - Search endpoint with filters (origin, destination, date, class)
   - Seat availability with real-time updates via events
   - PostgreSQL database with proper schema design

3. Implement `booking-service`:
   - Create booking workflow (calls flight-service for availability, reserves seat)
   - Booking status management (pending → confirmed → checked-in → completed)
   - Event emission: `BookingCreated`, `BookingCancelled`

4. Implement `auth-service`:
   - JWT token issuance and validation
   - User registration and login endpoints
   - RBAC middleware that can be shared across services
   - Refresh token rotation

**Week 4 — Supporting Services & Integration**

5. Implement `baggage-service`:
   - Baggage registration linked to bookings
   - Status tracking (checked-in → loaded → in-transit → arrived → collected)
   - Real-time status update events: `BaggageStatusChanged`

6. Implement `payment-service`:
   - Simulated payment processing (mock Stripe integration)
   - Idempotency keys to prevent double charges
   - Compensating transactions for refunds

7. Implement `notification-service`:
   - Event-driven: listens for `BookingCreated`, `CheckInCompleted`, `BaggageStatusChanged`
   - Sends mock email/SMS (log output or use a mock SMTP server)
   - Template-based notification rendering

8. Set up **event bus** (RabbitMQ or Redis Pub/Sub for local, document EventBridge for cloud):
   - Publishers: booking, flight, baggage services
   - Consumers: notification, analytics
   - Dead letter queue for failed messages

9. Set up **API Gateway** (Kong or a simple Express/FastAPI reverse proxy):
   - Route configuration for all services
   - JWT validation middleware
   - Rate limiting
   - Request logging

**Week 5 — Infrastructure & Cloud Deployment**

10. **Docker containerization:**
    - Dockerfile per service (multi-stage builds for smaller images)
    - docker-compose.yml that spins up all services, databases, message broker, Redis, and gateway
    - Health check endpoints for every service (`/health`)

11. **Kubernetes manifests** (for demonstrating cloud-readiness):
    - Deployment + Service YAML per microservice
    - HorizontalPodAutoscaler configs
    - ConfigMaps and Secrets for environment-specific config
    - Ingress controller configuration

12. **Infrastructure as Code** (Terraform or CloudFormation):
    - VPC, subnets, security groups
    - ECS/EKS cluster definition
    - RDS Aurora cluster
    - DynamoDB tables
    - SQS queues and SNS topics
    - Even if not fully deployed, having the IaC files demonstrates cloud competence

13. **Implement circuit breaker pattern:**
    - Use a library like `pybreaker` (Python) or `opossum` (Node.js)
    - Apply to inter-service HTTP calls (e.g., booking → payment)
    - Configure: 5 failures → open circuit for 30 seconds → half-open retry
    - Log circuit state changes

14. **Implement retry policies:**
    - Exponential backoff with jitter for transient failures
    - Max 3 retries for service-to-service calls
    - Idempotency keys to make retries safe

---

## Phase 3: Testing & Performance (Week 6)

### Task 6 — Performance & Scalability Testing

1. **Load testing with Locust or k6:**
   - Scenario 1: Simulate 500 concurrent users searching for flights
   - Scenario 2: Simulate 200 concurrent booking requests
   - Scenario 3: Simulate 1000 concurrent baggage status checks
   - Record: response time (p50, p95, p99), throughput (req/s), error rate (%)
   - Generate graphs: latency over time, throughput under increasing load

2. **Stress testing:**
   - Ramp users from 100 to 2000 over 10 minutes
   - Identify the breaking point (where error rate exceeds 5%)
   - Document system behavior under stress: which service degrades first, queue depths, CPU/memory usage

3. **Results analysis:**
   - Create a table comparing performance across scenarios
   - Identify bottlenecks (database connections, CPU-bound operations, network latency)
   - Propose improvements: connection pooling, caching, read replicas, horizontal scaling

### Task 8 — Testing Strategy

4. **Unit tests** (aim for 70%+ coverage on core services):
   - `flight-service`: test search logic, availability calculations, pricing rules
   - `booking-service`: test booking state machine, seat reservation logic, saga orchestration
   - `auth-service`: test JWT creation/validation, RBAC permission checks
   - Use pytest (Python) or Jest (Node.js)

5. **Integration tests:**
   - Test service-to-service communication via the API gateway
   - Test event-driven flows: publish event → verify consumer processed it
   - Test database operations with a test database (not mocks)
   - Use Testcontainers to spin up real Postgres/Redis for integration tests

6. **API tests with Postman:**
   - Create a Postman collection with requests for every endpoint
   - Write test scripts in Postman to validate response codes, schemas, and business rules
   - Create test environments (local, staging)
   - Export collection and include in submission
   - Run collection via Newman CLI and include output screenshots

7. **Evidence to include:**
   - Screenshot of test run results with pass/fail counts
   - Coverage report output
   - Load test graphs (Locust HTML report or k6 summary)
   - Postman collection runner results

---

## Phase 4: Monitoring & Observability (Week 6, parallel with testing)

### Task 7 — Monitoring & Observability

1. **Logging:**
   - Structured JSON logging in every service (timestamp, service name, trace ID, level, message)
   - Centralize logs: use ELK stack (local) or CloudWatch Logs (cloud)
   - Log correlation: pass a `X-Trace-Id` header across all inter-service calls

2. **Metrics:**
   - Expose Prometheus metrics from each service: request count, latency histogram, error count, active connections
   - Set up Grafana dashboards: one per service + one system-wide overview
   - Include screenshots of dashboards in the report

3. **Distributed tracing:**
   - Use OpenTelemetry SDK to instrument services
   - Trace a request across gateway → booking → flight → payment
   - Visualize with Jaeger (local) or AWS X-Ray (cloud)
   - Include a trace waterfall screenshot showing a full booking request

4. **Health checks and alerting:**
   - `/health` endpoint per service returning status, dependencies, uptime
   - Configure alerting rules: e.g., if error rate > 5% for 5 minutes → alert
   - Document the alerting strategy (even if using mock alerts locally)

---

## Phase 5: Report & Presentation (Week 7)

### Report Structure (aim for 40–50 pages including diagrams)

1. **Executive Summary** (1 page) — problem, solution, key outcomes
2. **Architecture Design** (10–12 pages)
   - System overview and microservice decomposition rationale
   - Cloud architecture with AWS service mapping
   - Multi-region deployment strategy
   - Containerization and orchestration approach
   - Serverless components and justification
3. **Security & Compliance** (6–8 pages)
   - Encryption strategy (at rest + in transit)
   - OAuth 2.0 / JWT / RBAC implementation
   - GDPR and PCI-DSS compliance approach
   - Data consistency: Saga pattern, CQRS, eventual consistency justification
4. **Implementation Overview** (8–10 pages)
   - Technology stack selection and rationale
   - Key code walkthrough for critical flows (booking saga, event handling, circuit breaker)
   - API Gateway configuration
   - Event-driven architecture implementation
   - Docker and Kubernetes setup
5. **Testing & Performance** (8–10 pages)
   - Unit test results and coverage
   - Integration test approach and results
   - API test results (Postman screenshots)
   - Load and stress test results with graphs
   - Performance analysis and improvement recommendations
6. **Monitoring & Observability** (4–5 pages)
   - Logging, metrics, tracing setup
   - Dashboard screenshots
   - Alerting strategy
7. **Challenges & Future Improvements** (2–3 pages)
   - Technical challenges encountered and how they were resolved
   - Limitations of the current implementation
   - Future roadmap: CI/CD pipeline, blue-green deployments, ML-based pricing, GraphQL federation

### Presentation (15 minutes)

1. **Slides:** 15–18 slides max, visually clean, diagram-heavy
   - Slide 1: Title + AeroLink overview
   - Slides 2–4: Architecture and key design decisions
   - Slides 5–7: Live demo plan (show the booking flow end-to-end)
   - Slides 8–9: Security and compliance highlights
   - Slides 10–11: Testing results and performance graphs
   - Slides 12–13: Monitoring dashboards
   - Slide 14: Challenges and lessons learned
   - Slide 15: Future improvements
   - Slide 16: Q&A

2. **Live demo preparation:**
   - Script a smooth demo flow: search flight → book → make payment → check-in → track baggage
   - Have a backup video recording in case docker-compose fails on the day
   - Prepare terminal windows showing: docker containers running, log output, Grafana dashboard

3. **Viva preparation — anticipate these questions:**
   - "Why microservices instead of serverless-first?"
   - "How does your saga handle partial failures?"
   - "What happens if the payment service is down during a booking?"
   - "How do you prevent double-booking the same seat?"
   - "How would you scale this to handle 10x traffic during a flash sale?"
   - "What's your strategy for database migrations across services?"
   - "How does your GDPR deletion work across all services?"
   - "Why did you choose eventual consistency over strong consistency?"

---

## Weekly Timeline Summary

| Week | Focus | Key Deliverables |
|---|---|---|
| 1 | Architecture design, diagrams, API spec | System diagrams, OpenAPI spec, security model |
| 2 | API design, event schemas, data model | Event catalog, database schemas, saga diagrams |
| 3 | Implement core services (flight, booking, auth) | 3 working services with APIs |
| 4 | Implement remaining services, event bus, gateway | Full system running in docker-compose |
| 5 | Kubernetes manifests, IaC, circuit breakers, resilience | Deployable infrastructure, resilience patterns |
| 6 | Testing (unit, integration, load), monitoring setup | Test reports, dashboards, performance graphs |
| 7 | Report writing, presentation prep, demo rehearsal | Final PDF, slides, rehearsed demo |

---

## Critical Tips for 80%+ Grade

1. **Diagrams sell architecture** — invest time in clean, professional diagrams. A marker will spend more time looking at diagrams than reading paragraphs. Use consistent notation (C4 model or AWS Architecture Icons).

2. **Working code beats perfect code** — a fully working system with 6 services beats a half-working system with 9 services. Prioritize the booking flow end-to-end over breadth.

3. **Show cloud thinking even without cloud deployment** — if you can't deploy to AWS, use LocalStack, document what you *would* deploy, and include Terraform/CloudFormation files. Markers award design thinking, not just infrastructure spend.

4. **Test evidence is marks on a plate** — every screenshot of a passing test suite, every load test graph, every Postman collection run is direct evidence of quality. Don't skip this.

5. **The saga pattern is your differentiator** — most students will use simple REST calls. Implementing a choreography-based saga with compensating transactions demonstrates advanced distributed systems knowledge.

6. **Prepare for the viva** — markers often differentiate between a 70 and an 85 during the viva. If you can explain *why* you chose eventual consistency over strong consistency with a concrete example from your system, you're in 80+ territory.
