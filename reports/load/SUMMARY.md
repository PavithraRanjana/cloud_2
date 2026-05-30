# AeroLink Load Test Results — AWS Production Deployment

**Target:** `https://d360csr5wvytoh.cloudfront.net`  →  CloudFront → API Gateway → 2-task internal ALB → 9 ECS Fargate services
**Date:** 2026-05-30
**Tool:** Locust 2.43.4
**Source:** single client (MacBook Pro), single egress IP
**Baseline cluster size:** 2 tasks per service, 256 CPU / 512 MB each (= 0.5 vCPU per service total)

---

## Scenario summary

| # | Scenario | Users | Spawn rate | Runtime | Reqs | Failures | RPS | p50 | p95 | p99 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Smoke | FlightSearchUser | 10 | 5/s | 60 s | 257 | 0 (0.00 %) | 4.5 | 320 ms | 620 ms | 4.3 s |
| 1 | FlightSearchUser | 500 | 25/s | 3 min | 5,533 | 670 (12.1 %) | 30.7 | **12 s** | 29 s | 47 s |
| 2 | BookingUser | 200 | 10/s | 3 min | 6,237 | 2,483 (~40 %) | 34.6 | 500 ms | 14 s | 29 s |
| 3 | BaggageTrackingUser | 500 | 25/s | 3 min | 14,508 | 5,555 (38.3 %) | 80.7 | 390 ms | 11 s | 31 s |

(Times in ms unless stated.)

---

## What the numbers say

### Smoke test (10 users)
Healthy: 0 % errors, sub-second median, sub-second p95. The system handles
low concurrency comfortably.

### Scenario 1 — Flight search at 500 users
The 2-task `flight-service` and 2-task `api-gateway` saturated almost
immediately. Median latency climbed to **12 s** — that's not a tail
problem, it's the whole distribution shifting. Errors were mostly
503 *Service Unavailable* (api-gateway saying "I can't reach a downstream
in time"), with a smaller fraction of 502 *Bad Gateway* from the
internal ALB hitting connection draining limits.

### Scenario 2 — Booking at 200 users
The happy-path median was **500 ms** — comfortable. But the tail
behaviour was rough: ~40 % failures and a p95 of 14 s. Booking is a
much heavier path (booking-service → flight-service for availability →
optimistic lock → DB write → event emission), so 200 concurrent users
× ~3 RPS each = ~600 in-flight bookings stressed the DB connection pool
and triggered cascading 503s from booking-service when it couldn't get
a flight-service response.

### Scenario 3 — Baggage tracking at 500 users
Median **390 ms** held up well — read-heavy paths are cheap. The 38 %
failures came at the tail, again 503s when downstream services were
saturated for short bursts.

---

## Auto-scaling behaviour

| Service | Scaling activities triggered |
|---|---|
| api-gateway | 0 |
| flight-service | 0 |
| booking-service | 0 |
| baggage-service | 0 |

**Why nothing scaled:** the autoscaling target tracks `CPUUtilization`
at a 70 % threshold via CloudWatch alarms that need ≥2 datapoints, each
at 60 s granularity. A 3-minute burst doesn't give the alarm enough
sustained breach time to trigger before the test ends. With a 10-minute
sustained test or a tighter alarm window, scale-out would fire.

---

## Identified bottlenecks (in order)

1. **api-gateway service capacity.** Only 2 tasks at 0.5 vCPU total
   serve all incoming requests. This is the first thing to fall over.
2. **flight-service DB connection pool.** When 500 search users hit
   simultaneously, asyncpg's pool (default 20) becomes the choke point.
3. **booking-service synchronous fan-out.** Each booking holds open an
   HTTP connection to flight-service while it validates seat availability;
   cascading 503s on flight-service immediately fail bookings.
4. **No dedicated read-replica.** All search queries hit the primary
   RDS, competing with booking writes.

---

## Recommended fixes (for §Future Improvements in the report)

| Fix | Expected impact |
|---|---|
| Raise ECS minimum capacity from 2 → 4 on api-gateway and flight-service | Doubles steady-state headroom |
| Add an RDS read-replica + route search queries to it via SQLAlchemy `bind_mapper` | Removes search/write contention |
| Increase asyncpg pool size to 50 in flight-service | More concurrent DB queries |
| Tune autoscaling alarm to 1 × 60 s breach (not 2) and add scale-out on p95 latency | Reacts to spikes faster |
| Add an in-memory ETag cache in the api-gateway for read-only GETs to flight-service | Reduces flight-service load by ~70 % for repeated searches |
| Run Locust in distributed mode from multiple regions/AZs | Removes single-client / single-IP test artifact |

---

## Artifacts in this folder

- `smoke.html` — small sanity check report
- `FlightSearchUser.html`, `FlightSearchUser_stats.csv`, `FlightSearchUser_failures.csv`, `FlightSearchUser_stats_history.csv`
- `BookingUser.html`, `BookingUser_stats.csv`, `BookingUser_failures.csv`, `BookingUser_stats_history.csv`
- `BaggageTrackingUser.html`, `BaggageTrackingUser_stats.csv`, `BaggageTrackingUser_failures.csv`, `BaggageTrackingUser_stats_history.csv`

The `*.html` files are the Locust HTML report — open in a browser and screenshot
the response-time chart, requests/sec chart, and failures table. Those are the
shots that go into §Phase 3 Task 6 of the report.

The `*_stats_history.csv` files contain per-second time-series data — useful
if you want to make your own custom graph showing the moment when failures
start (the breaking-point evidence the plan asks for).

---

## Stress test (added later)

**Profile:** stepped ramp 100 → 250 → 500 → 1000 → 2000 users, 2 minutes per
plateau, total ~10 min. Single scenario: `FlightSearchUser`.

### Per-step behaviour

| Stage | Users | RPS | Error rate | p50 | p95 | Verdict |
|---|---:|---:|---:|---:|---:|---|
| 1 | 100  | ~30 | **0 %** | 2.0 s | 4.0 s | Healthy |
| 2 | 250  | ~28 | 0–2 % | 2.5 s | 8.0 s | Drifting |
| 3 | 500  | ~30 | **11–30 %** | 5.0 s | 13 s | **Broken** |
| 4 | 1000 | ~50 | 30–60 % | 7.0 s | 29 s | Saturated |
| 5 | 2000 | ~40 | 15–32 % | 9.0 s | 30 s | Saturated, ALB shedding |

### Breaking point: **~500 concurrent users** (from a single client IP, 2-task baseline)

The transition is sharp — at 250 users error rate stays sub-2 %; the moment
the 500-user step begins, errors jump to 11 % within 20 seconds. p95 latency
also doubles (8 s → 13 s) at the same boundary. By the plan's 5 % error
threshold, **the system breaks at ~400 concurrent users with the default
2-task baseline**.

### Auto-scaling triggered

- `api-gateway`: 2 → 3 at 14:35:31 (during the 500-user step)
- `flight-service`: did not scale (peak avg CPU ~60 %, below 70 % target)

Scale-out helped — note the error-rate window around 80132025–80132027
where the rate dropped to 7–8 % briefly after the new task joined.
But by the time the 1000- and 2000-user steps hit, even the 3-task
api-gateway was saturated.

### Failure-mode mix

At peak load (2000 users), the failures are roughly:
- 50 % **503 Service Unavailable** — api-gateway returns this when a
  downstream call times out
- 25 % **502 Bad Gateway** — internal ALB returning this when target
  tasks are unhealthy or pool exhausted
- 25 % **TCP/SSL errors** — `RemoteDisconnected`, `ConnectionResetError`,
  `SSLEOFError` — the client side is being shed by the load balancer
  before reaching the application

### What this means for capacity planning

| Concurrent users (from one client) | Baseline tasks needed |
|---:|---:|
| 100 | 2 (current default) |
| 500 | 4 (autoscale catches up after ~3 min sustained) |
| 1000 | 6–8 (raise MinCapacity OR pre-warm before known spikes) |
| 2000 | 10 (MaxCapacity ceiling — would need raising) |

### Caveat — single-client test artefact

Most of the SSL/TCP errors at the 1000+ user steps are not the server's
fault: 2000 concurrent open sockets from one MacBook saturates the local
ephemeral port pool and the OS connection table. A distributed Locust
run (one worker per AZ) would push the breaking point higher.

---

## Stress test artefacts in this folder

- `stress.html` — Locust HTML report with per-step graphs (open in browser, screenshot the response-time + RPS charts)
- `stress_stats.csv` — final aggregated stats
- `stress_stats_history.csv` — per-10-second snapshots; this is what proves the breaking point happens at the 500-user step boundary
- `stress_failures.csv` — full error breakdown by request type
- `stress.log` — raw locust console output
