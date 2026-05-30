# AeroLink — AWS Console Evidence Checklist for the Final Report

This checklist maps the report sections from `AeroLink_Assignment_Plan.md`
to the specific AWS console pages you should screenshot. Every item is
something the markers can use as direct evidence that the design or
implementation actually exists in the cloud — not just on paper.

| Field | Value |
|---|---|
| **Production URL** | https://d360csr5wvytoh.cloudfront.net |
| **API URL** | https://0faoc5vfv9.execute-api.us-east-1.amazonaws.com |
| **Region** | us-east-1 |
| **Stack name** | production-aerolink |

For each shot, include the URL bar (it confirms the AWS region + account),
the timestamp visible in the top-right corner, and any filter/range you set.

---

## Section 2 — Architecture
*(Report pages ~10–12, plan §Phase 1 Task 1)*

**Goal:** prove the cloud architecture diagrams are real, not aspirational.

- [ ] **1. CloudFormation stack overview**
  - **Page:** CloudFormation → Stacks → `production-aerolink` → Overview tab
  - **What it shows:** CREATE_COMPLETE status, stack ID, ~150 resources counted.
  - **Why it matters:** single source of truth for the whole infrastructure.

- [ ] **2. CloudFormation Resources tab** (scroll-capture the full list, or take 3–4 partial shots covering different prefixes: `VPC*`, `ECS*`, `RDS*`, `Lambda*`, `Cognito*`, `S3*`, `CloudFront*`, `ApiGatewayV2*`).
  - **Page:** CloudFormation → Stacks → `production-aerolink` → Resources tab
  - **Why:** each row maps to a box in your architecture diagram.

- [ ] **3. CloudFormation Outputs tab**
  - **Page:** CloudFormation → Stacks → `production-aerolink` → Outputs tab
  - **What it shows:** `CloudFrontDomain`, `ApiGatewayEndpoint`, `RDSEndpoint`, `RedisEndpoint`, `CognitoUserPoolId`, etc.
  - **Why:** shows how the named pieces of the stack expose themselves to the outside world.

- [ ] **4. VPC topology (resource map)**
  - **Page:** VPC → Your VPCs → `production-aerolink-vpc` → Resource map tab
  - **What it shows:** 2 public subnets, 2 private subnets, NAT gateways, IGW.
  - **Why:** confirms the multi-AZ network layout in your architecture diagram.

- [ ] **5. Subnets list filtered by VPC**
  - **Page:** VPC → Subnets, filter by `VPC = production-aerolink-vpc`
  - **Why:** shows AZ assignments and public/private labelling.

- [ ] **6. Route tables**
  - **Page:** VPC → Route tables, filter by VPC
  - **What it shows:** `PublicRouteTable` → IGW, `PrivateRouteTable1/2` → NATs.

- [ ] **7. ECS cluster overview**
  - **Page:** ECS → Clusters → `production-aerolink` → Cluster overview
  - **What it shows:** 9 services, ~18 tasks running, Fargate as the only capacity provider, "Container Insights with enhanced observability" toggle ON.

- [ ] **8. ECS Services list (sorted by service name)**
  - **Page:** ECS → Clusters → `production-aerolink` → Services tab
  - **Why:** confirms all 9 services exist and each runs the desired 2 tasks.

- [ ] **9. RDS DB instance summary**
  - **Page:** RDS → Databases → `production-aerolink-db` → Configuration tab
  - **What it shows:** Multi-AZ = yes, Engine = postgres 15, Storage = gp3, Manage master user password = Yes, etc.

- [ ] **10. ElastiCache cluster**
  - **Page:** ElastiCache → Redis OSS caches → `production-aerolink-redis`
  - **What it shows:** 2 nodes across 2 AZs, automatic failover enabled.

- [ ] **11. CloudFront distribution**
  - **Page:** CloudFront → Distributions → `E2FL1FTSXC0MDJ`
  - **What it shows:** Two origins (S3 frontend bucket + API Gateway), `/api/*` behavior pointing at the API origin.

- [ ] **12. Global Accelerator** (if configured)
  - **Page:** Global Accelerator → Accelerators
  - **Optional:** if your diagram shows it, screenshot it; otherwise skip.

- [ ] **13. Cognito user pool**
  - **Page:** Cognito → User pools → `aerolink-cfn` → App integration tab
  - **What it shows:** Hosted UI URL, the configured callback URLs, App client, the social/identity providers and groups (`admin`, `passenger`, `airline-staff`, `airport-operator`, `partner-api`).

---

## Section 3 — Security & Compliance
*(Report pages ~6–8, plan §Phase 1 Task 3)*

**Goal:** prove the encryption / IAM / network isolation / GDPR / PCI statements you make in the security chapter.

- [ ] **14. Cognito groups (RBAC roles)**
  - **Page:** Cognito → User pools → `aerolink-cfn` → Groups tab
  - **What it shows:** the five groups (`admin`, `passenger`, `airline-staff`, `airport-operator`, `partner-api`). Backs the RBAC matrix in the report.

- [ ] **15. Cognito app client OAuth settings**
  - **Page:** Cognito → User pools → `aerolink-cfn` → App integration → App client list → click the client → Hosted UI section
  - **What it shows:** Authorization code grant, scopes (`openid email profile`), callback URLs. Evidence for the OAuth 2.0 design.

- [ ] **16. Secrets Manager secrets list filtered by `production/aerolink`**
  - **Page:** Secrets Manager → Secrets
  - **Why:** shows the three managed secrets (`app`, `stripe`, `rds!db-...`). Backs the "no plaintext credentials" claim.

- [ ] **17. The RDS-managed secret detail page**
  - **Page:** Secrets Manager → `rds!db-2935031c-...-eFDhME`
  - **What it shows:** "Managed by AWS RDS" badge, rotation enabled, encryption with a KMS key.

- [ ] **18. KMS keys list filtered by alias or by usage**
  - **Page:** KMS → AWS managed keys (and Customer managed if you have any)
  - **Why:** backs the "AES-256 at rest" claim — show the rds-managed key, `aws/secretsmanager`, `aws/s3`.

- [ ] **19. RDS encryption indicator**
  - **Page:** RDS → `production-aerolink-db` → Configuration tab → "Storage encryption" row
  - **What it shows:** Encrypted = Yes, KMS key reference.

- [ ] **20. S3 bucket encryption — DocumentsBucket**
  - **Page:** S3 → Buckets → `production-aerolink-documents-097279986320` → Properties tab → Default encryption section
  - **What it shows:** SSE-S3 (AES-256), Bucket Versioning enabled.

- [ ] **21. S3 bucket block-public-access — DocumentsBucket**
  - **Page:** same bucket → Permissions tab → Block public access section
  - **What it shows:** all four block settings ON.

- [ ] **22. S3 bucket lifecycle rule**
  - **Page:** same bucket → Management tab → Lifecycle rules
  - **What it shows:** "TransitionBoardingPassesToIA" rule moving boarding-pass objects to STANDARD_IA after 90 days. Evidence for data-tiering / cost-optimisation paragraph.

- [ ] **23. Network isolation — RDS security group**
  - **Page:** EC2 → Security groups → `production-aerolink-RDSSecurityGroup` → Inbound rules tab
  - **What it shows:** only the ECS and Lambda SGs allowed on port 5432.

- [ ] **24. ECS task SG**
  - **Page:** EC2 → Security groups → `production-aerolink-ECSSecurityGroup` → Inbound rules tab
  - **What it shows:** tasks accept traffic only from the internal ALB SG and from themselves (for Service Connect).

- [ ] **25. PCI-DSS scope screenshot — payment-service task definition env**
  - **Page:** ECS → Task definitions → `production-payment-service` → (latest revision) → Environment variables panel
  - **What it shows:** `STRIPE_SECRET_KEY` comes from Secrets Manager (Secrets block, not Environment). No plaintext card data is stored. Caption it as "PCI scope reduced via Stripe tokenization".

- [ ] **26. WAF web ACL definition**
  - **Page:** WAF → Web ACLs → `production-aerolink-waf` → Rules tab
  - **What it shows:** the two rate-limit rules (`RateLimitPerIP` at 500/5min and `RateLimitPartnerApiKey` at 5000/5min scoped to requests with `x-api-key`).

- [ ] **27. API Gateway stage throttling**
  - **Page:** API Gateway → `production-aerolink-api` → Stages → `$default` → Default route settings
  - **What it shows:** Throttling burst 200, rate 100 (the substitute for WAF on the HTTP API).

- [ ] **28. EventBridge bus and rules** — proves the choreography saga is real
  - **Page:** EventBridge → Event buses → `aerolink-events` → Rules tab
  - **What it shows:** ~10 rules (`booking-created-to-notifications`, `payment-completed-to-notifications`, etc.). Backs the saga diagram in the security/data-consistency chapter.

- [ ] **29. EventBridge rule detail** (pick `BookingCreated-to-notifications`)
  - **Page:** EventBridge → Rules → click rule → Targets tab
  - **What it shows:** the SQS queue and Lambda targets. Backs the "publisher → bus → consumers" claim.

- [ ] **30. DynamoDB payment-idempotency table**
  - **Page:** DynamoDB → Tables → `payment-idempotency` → Overview tab
  - **What it shows:** table exists, TTL enabled. Backs the "idempotency keys prevent double charges" claim.

---

## Section 4 — Implementation
*(Report pages ~8–10, plan §Phase 2)*

**Goal:** prove the system isn't just designed — it's running.

- [ ] **31. ECS service detail — auth-service**
  - **Page:** ECS → Clusters → `production-aerolink` → Services → `auth-service`
  - **What it shows:** Running tasks 2/2, deployment rollout COMPLETED, service connect configuration block visible.

- [ ] **32. ECS Service Connect topology**
  - **Page:** ECS → Clusters → `production-aerolink` → Service Connect tab
  - **What it shows:** the service map with all 9 services in the `aerolink.local` namespace. Backs the "service mesh" discussion.

- [ ] **33. ECS task definition (any service) Secrets block**
  - **Page:** ECS → Task definitions → `production-flight-service` → latest rev → Storage, networking and environment → Environment variables / Secrets section
  - **What it shows:** `JWT_SECRET`, `DB_PASSWORD` coming from Secrets Manager.

- [ ] **34. ECR repositories list**
  - **Page:** ECR → Private repositories
  - **What it shows:** nine `aerolink/*` repos, each with images.

- [ ] **35. ECR image detail for one repo**
  - **Page:** ECR → `aerolink/booking-service` → Images
  - **What it shows:** `latest` tag, image push date, image digest, size, scan status if scanning is on.

- [ ] **36. CloudFront distribution behaviors**
  - **Page:** CloudFront → Distributions → `E2FL1FTSXC0MDJ` → Behaviors tab
  - **What it shows:** Default behavior to S3 frontend, `/api/*` behavior to API Gateway. Evidence for the CDN/edge claim.

- [ ] **37. CloudFront origins**
  - **Page:** same distribution → Origins tab
  - **What it shows:** the two origins (S3 + ApiGateway HTTPS).

- [ ] **38. S3 frontend bucket contents**
  - **Page:** S3 → `production-aerolink-frontend-097279986320` → Objects tab
  - **What it shows:** `index.html` and `assets/*.js`, `assets/*.css` with recent upload timestamps.

- [ ] **39. API Gateway routes**
  - **Page:** API Gateway → `production-aerolink-api` → Routes
  - **What it shows:** the public routes (login/register/refresh/forgot/reset/stripe-webhook/flights) and the `$default` route with JWT.

- [ ] **40. API Gateway authorizer**
  - **Page:** same API → Authorization
  - **What it shows:** the Cognito JWT authorizer configuration (issuer URL, audience). Backs the "JWT validation at gateway" claim from §Phase 1 Task 2.

- [ ] **41. API Gateway VPC link**
  - **Page:** API Gateway → VPC links → `production-aerolink-vpclink`
  - **What it shows:** VPC link to internal ALB, status Available.

- [ ] **42. Internal ALB target group health**
  - **Page:** EC2 → Target groups → `production-api-gw-tg` → Targets tab
  - **What it shows:** 2 healthy targets. Backs the "ALB + ECS" claim.

- [ ] **43. Lambda functions list**
  - **Page:** Lambda → Functions, filter `production-`
  - **What it shows:** `notification-dispatch`, `boarding-pass-generator`, `pricing-recalculation`, `cognito-post-confirmation`. Backs the "serverless component" requirement of Task 1.

- [ ] **44. Lambda function detail — pricing-recalculation**
  - **Page:** Lambda → `production-pricing-recalculation` → Configuration tab
  - **What it shows:** VPC config, layers (`LambdaInsightsExtension`), trigger (EventBridge schedule). Backs the "scheduled pricing recalculation" Lambda mentioned in Task 1.

- [ ] **45. EventBridge schedule for pricing**
  - **Page:** EventBridge → Rules → `PricingRecalculationScheduleRule`
  - **What it shows:** `rate(5 minutes)` schedule, Lambda target.

- [ ] **46. SQS notifications queue**
  - **Page:** SQS → Queues → `production-aerolink-notifications`
  - **What it shows:** visible messages, in-flight, oldest age. Also show the DLQ configuration. Backs the resilience claim.

- [ ] **47. SQS DLQ**
  - **Page:** SQS → `production-aerolink-notifications-dlq`
  - **What it shows:** redrive policy. Backs the "dead letter queue for failed event processing" line in Task 2.

- [ ] **48. CloudFront URL working end-to-end**
  - **Page:** open https://d360csr5wvytoh.cloudfront.net in the browser, log in, and screenshot the home/flights page rendered. Include the URL bar.
  - **Why:** the demo evidence that the deployed system actually serves real users.

---

## Section 5 — Testing & Performance
*(Report pages ~8–10, plan §Phase 3)*

**Goal:** the AWS evidence to PAIR with your local Locust/k6/Postman
screenshots — show that AWS observed the same numbers from the cloud
side. Run a load test (Locust/k6) against the CloudFront URL and during
that run take the screenshots below.

- [ ] **49. CloudWatch dashboard while load test is running**
  - **Page:** CloudWatch → Dashboards → `production-aerolink`
  - Set time range to "last 1 hour" while the load test is running.
  - **Show:** API Gateway requests spike, ECS CPU climbing, RDS connection count rising.

- [ ] **50. API Gateway p50/p95/p99 latency widget** — zoom into the test window
  - Same dashboard, just the latency widget.

- [ ] **51. ECS auto-scaling activity**
  - **Page:** ECS → Clusters → `production-aerolink` → Services → `flight-service` → Auto Scaling tab
  - **What it shows:** target tracking policy, scaling activities triggered by the load test (DesiredCount changing from 2 → 3 etc.).

- [ ] **52. RDS Performance Insights during the test window**
  - **Page:** RDS → Performance Insights → `production-aerolink-db`
  - Set time range to overlap your load test.
  - **What it shows:** top SQL by wait time, DB load by wait state. Use the "Top SQL" breakdown as a screenshot.

- [ ] **53. Container Insights overview during the test**
  - **Page:** CloudWatch → Container Insights → Performance monitoring → ECS Clusters → `production-aerolink`
  - **What it shows:** cluster-level CPU/memory, container restart count.

- [ ] **54. Container Insights — per-service drilldown**
  - **Page:** same view, click a specific service (e.g. `booking-service`)
  - **What it shows:** per-task CPU/memory time series. The "enhanced observability" version shows container-level too.

- [ ] **55. ALB request count and 5xx during the test**
  - **Page:** CloudWatch → Metrics → `AWS/ApplicationELB` → Per AppELB → `production-aerolink-alb`
  - Pick `RequestCount` and `HTTPCode_Target_5XX_Count`.

- [ ] **56. Stress test breaking point**
  - If you ramp users until error rate > 5%, screenshot the dashboard at that moment with the time range pinned. This is direct evidence for the "identified breaking point" deliverable.

---

## Section 6 — Monitoring & Observability
*(Report pages ~4–5, plan §Phase 4)*

**Goal:** prove the monitoring/logging/tracing stack is real and useful.

- [ ] **57. CloudWatch dashboard — full screenshot** (one big shot per row, or a single stitched image)
  - **Page:** CloudWatch → Dashboards → `production-aerolink`
  - This is the headline observability shot.

- [ ] **58. CloudWatch Logs — log groups list filtered by `/ecs/production/`**
  - **Page:** CloudWatch → Log groups, search `/ecs/production/`
  - **What it shows:** nine ECS log groups + the API GW execution log group.

- [ ] **59. One log group's recent log stream**
  - **Page:** CloudWatch → Log groups → `/ecs/production/booking-service` → pick the most recent stream
  - **What it shows:** structured JSON log lines with `trace_id`, `level`, service name. Backs the "structured logging + trace ID" claim from §Phase 4 step 1.

- [ ] **60. Logs Insights query result** (run a query that finds errors with their `trace_id`)
  - **Page:** CloudWatch → Logs Insights
  - **Sample query:**
    ```
    fields @timestamp, service_name, level, event, trace_id, error
    | filter level = "error"
    | sort @timestamp desc
    | limit 50
    ```
  - Run against `/ecs/production/*` log groups for the last 1 hour.

- [ ] **61. Container Insights — performance monitoring view** (also serves as Section 5/6 evidence)
  - **Page:** CloudWatch → Container Insights → Performance monitoring
  - Set scope to ECS clusters and pick `production-aerolink`. Screenshot the cluster level summary with metric tiles.

- [ ] **62. Container Insights — per-task drilldown**
  - **Page:** from the same screen, click into a single task. Capture the task page that shows CPU, memory, network, storage at the task and container level.

- [ ] **63. RDS Performance Insights (idle window)**
  - **Page:** RDS → Performance Insights → `production-aerolink-db`, range last 1 hour
  - Even at idle, the DB load chart and counter metrics tiles render.

- [ ] **64. Lambda Insights multi-function dashboard**
  - **Page:** CloudWatch → Lambda Insights → Multi-function
  - Filter to `production-*` and screenshot the table view + a per-function drilldown.

- [ ] **65. Lambda Insights — single function detail**
  - **Page:** CloudWatch → Lambda Insights → Single function → `production-pricing-recalculation`
  - **What it shows:** CPU, memory, init duration, function cost over time.

- [ ] **66. CloudWatch alarms list** (if you've created any)
  - **Page:** CloudWatch → Alarms → All alarms
  - If you don't have alarms yet, you can either create a couple of obvious ones (e.g. RDS CPU > 80% for 5 min, SQS DLQ depth > 0) and then screenshot the list, or skip this and note it in §Future Work.

- [ ] **67. X-Ray service map** (only if you instrument)
  - **Page:** X-Ray → Service map
  - The plan calls for distributed tracing with a waterfall screenshot of a booking request. If you have not added the OpenTelemetry/X-Ray SDK yet, do so in the `api-gateway` and one downstream service (`booking-service` is the highest-impact choice). Then take this screenshot of the service map and the trace waterfall.

- [ ] **68. EventBridge invocations metric**
  - **Page:** EventBridge → Rules → `BookingCreated-to-notifications` → Monitoring tab
  - **What it shows:** `TriggeredRules`, `MatchedEvents`, `InvocationsCount`. Backs the event-driven architecture working in production.

---

## Section 7 — Challenges & Future Work
*(Report pages ~2–3, plan §Phase 5)*

You can also lean on AWS evidence here for the "what we'd add" arguments.

- [ ] **69. CodePipeline** (if added) or note it as future work
  - **Page:** CodePipeline → Pipelines
  - The plan lists CI/CD as a "future improvement" item.

- [ ] **70. AWS Cost Explorer** — last 7 days, grouped by service
  - **Page:** Cost Explorer → Reports → New custom report
  - Group by Service for last 7 days. Useful screenshot if the report discusses cost optimisation (lean on it for the "cost review" line).

---

## Quick capture tips

- Set the AWS console region selector to **"US East (N. Virginia)"** before every shot — it's visible top-right and consistent across all images.
- Use the same browser zoom across the report (110% works well).
- Time range matters for metric shots — set to last 1h or last 3h, and make sure the timestamp is visible.
- For dashboards that scroll, paste in pieces but keep the URL bar in the first piece so the marker can see it's the same page.
- Annotate the screenshot in the report body with a one-line caption that says exactly what to look at — markers skim.

---

## What this buys you in grading terms

- **Architecture chapter:** 20% weight. Shots 1–13 plus the diagrams cover the "deployable infrastructure, cloud thinking" criteria.
- **Security chapter:** part of the 20% architecture mark + lots of Implementation marks. Shots 14–30 are direct evidence for every bullet in §Phase 1 Task 3.
- **Implementation chapter:** 40% weight. Shots 31–48 prove the system is actually running on AWS, not just docker-compose.
- **Testing & Performance:** 20% weight. Shots 49–56 are the cloud-side evidence that pairs with your Locust/k6 screenshots.
- **Monitoring & Observability:** contributes to both Implementation and Testing marks. Shots 57–68 are the strongest evidence here.

A clean appendix with these 70 numbered shots will be the easiest way to push the mark above 80%.
