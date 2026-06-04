# AeroLink Postman Collection

End-to-end Postman collection for testing the AeroLink microservices
platform — every public endpoint exposed through the api-gateway, plus
a one-click smoke-test folder that runs the full passenger journey
in order.

## Files

| File | Purpose |
|---|---|
| `AeroLink.postman_collection.json` | The collection itself — request bodies, tests, pre-request scripts |
| `AeroLink_Local.postman_environment.json` | Targets `http://localhost:8000` (docker-compose) with the seeded test users |
| `AeroLink_AWS.postman_environment.json` | Targets the live CloudFront URL — fill in real Cognito credentials before use |

## Import into Postman

1. Open Postman → click **Import** (top-left)
2. Drop in all three JSON files at once (or one by one)
3. In the top-right environment dropdown, pick either
   **AeroLink Local (docker-compose)** or
   **AeroLink AWS (production CloudFront)**

## Run the full passenger journey in one click

The collection contains a folder called **Smoke / End-to-End Flow**
with eight steps in order:

1. Register a new user (timestamped username so the test is repeatable)
2. Log in (saves JWT to `accessToken`)
3. Search flights (saves the first result's id to `flightId`)
4. Create booking (saves `bookingId`)
5. Create payment intent (saves `paymentIntentId`)
6. Check in
7. Register baggage
8. Fetch notifications

Click **Run** on that folder → Postman fires all eight in order, runs
the tests assertions on each response, and shows pass/fail per request.
This is the assignment-evidence shot for "API tested end to end".

## Run the per-area folders manually

For exploratory testing — `Auth`, `Flights`, `Bookings`, `Payments`,
`Baggage`, `Check-in`, `Passengers`, `Notifications` — each folder is
a standalone group of requests. The collection-level Bearer auth
inserts the `accessToken` automatically on every protected request.

**To get an `accessToken`**: run `Auth → Login (passenger)` first
(uses the username + password from the environment). The test script
in that request saves the token into the `accessToken` collection
variable; every subsequent request picks it up automatically.

For admin-only operations (e.g. `Flights → Create flight (admin)`),
run `Auth → Login (admin)` instead — it logs in as the admin user
defined in the environment and overwrites `accessToken` with the admin
JWT.

## Run from the command line with Newman

The CLI runner is `newman` — comes with `npm install -g newman`:

```bash
# Smoke test against local docker-compose
newman run AeroLink.postman_collection.json \
  -e AeroLink_Local.postman_environment.json \
  --folder "Smoke / End-to-End Flow" \
  --reporters cli,html \
  --reporter-html-export ../../reports/postman_smoke.html

# Whole collection against AWS
newman run AeroLink.postman_collection.json \
  -e AeroLink_AWS.postman_environment.json \
  --reporters cli,htmlextra \
  --reporter-htmlextra-export ../../reports/postman_aws.html
```

The HTML report from `newman run --reporters html` is what to
screenshot for the assignment report's §6 Testing chapter.

## What the collection covers

| Folder | Endpoints | Tests |
|---|---:|---:|
| Health | 1 | 2 |
| Auth | 7 | 14 |
| Flights | 3 | 6 |
| Bookings | 4 | 7 |
| Payments | 2 | 3 |
| Baggage | 3 | 2 |
| Check-in | 3 | 1 |
| Passengers | 3 | 0 |
| Notifications | 3 | 2 |
| Smoke / End-to-End Flow | 8 | 8 |
| **Total** | **37** | **45** |

Tests check status codes, response shape, and capture IDs into
collection variables for chained requests.

## Variables

Collection-level variables (also defined per environment):

| Variable | Purpose | Set by |
|---|---|---|
| `baseUrl` | API root — switch per environment | Environment file |
| `username`, `password` | Passenger credentials | Environment file |
| `adminUsername`, `adminPassword` | Admin credentials | Environment file |
| `accessToken`, `refreshToken` | Active JWT | `Auth → Login` test script |
| `userId` | Current user id | Login / Register |
| `flightId` | First flight from search | `Flights → Search` test script |
| `bookingId` | Created booking id | `Bookings → Create booking` test script |
| `paymentIntentId` | Stripe intent id | `Payments → Create intent` test script |
| `baggageId`, `checkinId`, `notificationId` | Resource ids | Per-resource POST/list test scripts |

You generally don't need to set these manually — the chained requests
populate them as you progress through the collection.

## Why this collection exists

The assignment plan calls for *"API tests with Postman — create a
Postman collection with requests for every endpoint, write test
scripts to validate response codes, schemas, and business rules,
export collection, run via Newman CLI and include output screenshots"*.

This collection is the deliverable for that requirement. The
**Smoke / End-to-End Flow** folder doubles as the "passenger
journey demo" you can fire from a fresh laptop in under 30 seconds
with `newman run`.
