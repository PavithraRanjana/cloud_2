#!/bin/bash
# Initialize AWS resources in LocalStack for AeroLink

echo "=== Initializing AeroLink AWS Resources ==="

# Create EventBridge event bus
awslocal events create-event-bus --name aerolink-events
echo "Created EventBridge event bus: aerolink-events"

# Create SQS queues for each consumer service
# Create DLQ first so we can reference its ARN
awslocal sqs create-queue --queue-name aerolink-notifications-dlq
DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/aerolink-notifications-dlq \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)

# Create main queue with redrive policy pointing to DLQ (max 3 receives before DLQ)
awslocal sqs create-queue \
  --queue-name aerolink-notifications \
  --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"
echo "Created SQS queues with DLQ redrive policy (maxReceiveCount=3)"

# Get queue ARN for the notification queue
NOTIFICATION_QUEUE_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/aerolink-notifications \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)

echo "Notification Queue ARN: $NOTIFICATION_QUEUE_ARN"

# Create EventBridge rules to route events to SQS

# Rule 1: BookingCreated -> notification queue
awslocal events put-rule \
  --name booking-created-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["booking-service"],"detail-type":["BookingCreated"]}'

awslocal events put-targets \
  --rule booking-created-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: BookingCreated -> notifications"

# Rule 2: PaymentCompleted -> notification queue
awslocal events put-rule \
  --name payment-completed-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["payment-service"],"detail-type":["PaymentCompleted"]}'

awslocal events put-targets \
  --rule payment-completed-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: PaymentCompleted -> notifications"

# NOTE: payment-processed-to-notifications is intentionally NOT created here.
# payment-service publishes PaymentCompleted (not PaymentProcessed).

# Rule 3: CheckInCompleted -> notification queue
awslocal events put-rule \
  --name checkin-completed-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["checkin-service"],"detail-type":["CheckInCompleted"]}'

awslocal events put-targets \
  --rule checkin-completed-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: CheckInCompleted -> notifications"

# Rule 4: BaggageStatusChanged -> notification queue
awslocal events put-rule \
  --name baggage-status-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["baggage-service"],"detail-type":["BaggageStatusChanged"]}'

awslocal events put-targets \
  --rule baggage-status-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: BaggageStatusChanged -> notifications"

# Rule 5: BookingCancelled -> notification queue
awslocal events put-rule \
  --name booking-cancelled-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["booking-service"],"detail-type":["BookingCancelled"]}'

awslocal events put-targets \
  --rule booking-cancelled-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: BookingCancelled -> notifications"

# Rule 6: PaymentFailed -> notification queue
awslocal events put-rule \
  --name payment-failed-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["payment-service"],"detail-type":["PaymentFailed"]}'

awslocal events put-targets \
  --rule payment-failed-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: PaymentFailed -> notifications"

# Rule 7: BaggageRegistered -> notification queue
awslocal events put-rule \
  --name baggage-registered-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["baggage-service"],"detail-type":["BaggageRegistered"]}'

awslocal events put-targets \
  --rule baggage-registered-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: BaggageRegistered -> notifications"

# Rule 8: PaymentRefunded -> notification queue
awslocal events put-rule \
  --name payment-refunded-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["payment-service"],"detail-type":["PaymentRefunded"]}'

awslocal events put-targets \
  --rule payment-refunded-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: PaymentRefunded -> notifications"

# Rule 9: FlightScheduleUpdated -> notification queue
awslocal events put-rule \
  --name flight-schedule-updated-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["flight-service"],"detail-type":["FlightScheduleUpdated"]}'

awslocal events put-targets \
  --rule flight-schedule-updated-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: FlightScheduleUpdated -> notifications"

# Rule 10: SeatAvailabilityChanged -> notification queue
awslocal events put-rule \
  --name seat-availability-to-notifications \
  --event-bus-name aerolink-events \
  --event-pattern '{"source":["flight-service"],"detail-type":["SeatAvailabilityChanged"]}'

awslocal events put-targets \
  --rule seat-availability-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=notification-queue,Arn=$NOTIFICATION_QUEUE_ARN"

echo "Created rule: SeatAvailabilityChanged -> notifications"

# Create S3 bucket for boarding passes / documents
awslocal s3 mb s3://aerolink-documents
echo "Created S3 bucket: aerolink-documents"

# Create DynamoDB table for payment idempotency keys
# payment-service writes idempotency_key -> payment_id to prevent double-charges
awslocal dynamodb create-table \
  --table-name payment-idempotency \
  --attribute-definitions \
    AttributeName=idempotency_key,AttributeType=S \
  --key-schema \
    AttributeName=idempotency_key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

echo "Created DynamoDB table: payment-idempotency"

# ──────────────────────────────────────────────
# Cognito User Pool (LocalStack Pro)
# ──────────────────────────────────────────────

echo ""
echo "=== Setting up Cognito User Pool ==="

POOL_ID=$(awslocal cognito-idp create-user-pool \
  --pool-name aerolink-local \
  --policies '{"PasswordPolicy":{"MinimumLength":8,"RequireUppercase":false,"RequireLowercase":false,"RequireNumbers":false,"RequireSymbols":false}}' \
  --auto-verified-attributes email \
  --query 'UserPool.Id' --output text)

echo "Created Cognito User Pool: $POOL_ID"

CLIENT_ID=$(awslocal cognito-idp create-user-pool-client \
  --user-pool-id "$POOL_ID" \
  --client-name aerolink-local-client \
  --no-generate-secret \
  --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH ALLOW_USER_SRP_AUTH \
  --query 'UserPoolClient.ClientId' --output text)

echo "Created Cognito App Client: $CLIENT_ID"

# Create RBAC groups (same as production CloudFormation)
for GROUP in passenger admin airport-operator partner-api; do
  awslocal cognito-idp create-group \
    --group-name "$GROUP" \
    --user-pool-id "$POOL_ID"
  echo "Created group: $GROUP"
done

# Create one test user per role (password: Test1234!)
for ROLE in passenger admin airport-operator; do
  USERNAME="test-$ROLE"
  awslocal cognito-idp admin-create-user \
    --user-pool-id "$POOL_ID" \
    --username "$USERNAME" \
    --user-attributes Name=email,Value="${USERNAME}@aerolink.test" Name=email_verified,Value=true \
    --temporary-password "Temp1234!" \
    --message-action SUPPRESS
  awslocal cognito-idp admin-set-user-password \
    --user-pool-id "$POOL_ID" \
    --username "$USERNAME" \
    --password "Test1234!" \
    --permanent
  awslocal cognito-idp admin-add-user-to-group \
    --user-pool-id "$POOL_ID" \
    --username "$USERNAME" \
    --group-name "$ROLE"
  echo "Created test user: $USERNAME (group: $ROLE, password: Test1234!)"
done

_create_named_user() {
  local USERNAME="$1" EMAIL="$2" GROUP="$3"
  # Redirect to stderr so the JSON output is not captured when called as $(...)
  awslocal cognito-idp admin-create-user \
    --user-pool-id "$POOL_ID" --username "$USERNAME" \
    --user-attributes Name=email,Value="$EMAIL" Name=email_verified,Value=true \
    --message-action SUPPRESS >&2
  awslocal cognito-idp admin-set-user-password \
    --user-pool-id "$POOL_ID" --username "$USERNAME" --password "Test1234!" --permanent >&2
  awslocal cognito-idp admin-add-user-to-group \
    --user-pool-id "$POOL_ID" --username "$USERNAME" --group-name "$GROUP" >&2
  # Only the sub UUID goes to stdout
  awslocal cognito-idp admin-get-user \
    --user-pool-id "$POOL_ID" --username "$USERNAME" \
    --query 'UserAttributes[?Name==`sub`].Value|[0]' --output text
}

# Create real named users — existing accounts with DB history.
TESTUSER_SUB=$(_create_named_user   "testuser"   "test@aerolink.com"       "admin")
PARTNERAPI_SUB=$(_create_named_user "partnerapi" "partner@airlines.com"     "partner-api")
SUPERADMIN_SUB=$(_create_named_user "superadmin" "superadmin@aerolink.com"  "admin")
SYSADMIN_SUB=$(_create_named_user   "sysadmin"   "sysadmin@aerolink.com"    "admin")
echo "Created named users: testuser partnerapi superadmin sysadmin"

# Create ranjana — real user with booking history in the DB.
# Her Cognito sub changes on every LocalStack restart (Cognito always assigns a new UUID).
# We write RANJANA_SUB to cognito.env so setup-local-cognito.sh can remap the DB.
awslocal cognito-idp admin-create-user \
  --user-pool-id "$POOL_ID" \
  --username "ranjana" \
  --user-attributes Name=email,Value=dranjana56@gmail.com Name=email_verified,Value=true \
  --message-action SUPPRESS
awslocal cognito-idp admin-set-user-password \
  --user-pool-id "$POOL_ID" \
  --username "ranjana" \
  --password "Test1234!" \
  --permanent
awslocal cognito-idp admin-add-user-to-group \
  --user-pool-id "$POOL_ID" \
  --username "ranjana" \
  --group-name "passenger"
RANJANA_SUB=$(awslocal cognito-idp admin-get-user \
  --user-pool-id "$POOL_ID" \
  --username "ranjana" \
  --query 'UserAttributes[?Name==`sub`].Value|[0]' --output text)
echo "Created user: ranjana (passenger, password: Test1234!, sub: $RANJANA_SUB)"

# Write IDs to shared config so services can pick them up via env_file
# This file's presence also signals the health check that init is complete.
CONFIG_DIR=/etc/localstack/init/localstack-config
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_DIR/cognito.env" <<EOF
COGNITO_USER_POOL_ID=${POOL_ID}
COGNITO_CLIENT_ID=${CLIENT_ID}
RANJANA_SUB=${RANJANA_SUB}
TESTUSER_SUB=${TESTUSER_SUB}
PARTNERAPI_SUB=${PARTNERAPI_SUB}
SUPERADMIN_SUB=${SUPERADMIN_SUB}
SYSADMIN_SUB=${SYSADMIN_SUB}
EOF
echo "Wrote Cognito IDs to $CONFIG_DIR/cognito.env"

# ──────────────────────────────────────────────
# Lambda Functions
# ──────────────────────────────────────────────

echo ""
echo "=== Setting up Lambda Functions ==="

LAMBDA_SRC=/opt/code/localstack/lambdas

# Create IAM execution role for Lambda functions
awslocal iam create-role \
  --role-name lambda-execution-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

awslocal iam attach-role-policy \
  --role-name lambda-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

LAMBDA_ROLE_ARN=$(awslocal iam get-role --role-name lambda-execution-role --query 'Role.Arn' --output text)
echo "Created Lambda execution role: $LAMBDA_ROLE_ARN"

# --- Lambda 1: Notification Dispatch (SQS-triggered, no external deps) ---
echo "Packaging notification_dispatch Lambda..."
cd /tmp && rm -rf lambda_notification && mkdir lambda_notification
cp $LAMBDA_SRC/notification_dispatch/handler.py lambda_notification/
cd lambda_notification && zip -r /tmp/notification_dispatch.zip .

awslocal lambda create-function \
  --function-name notification-dispatch \
  --runtime python3.10 \
  --handler handler.handler \
  --role "$LAMBDA_ROLE_ARN" \
  --zip-file fileb:///tmp/notification_dispatch.zip \
  --timeout 30 \
  --architectures arm64 \
  --environment "Variables={AWS_DEFAULT_REGION=eu-west-1}"

echo "Created Lambda: notification-dispatch"

# NOTE: notification-dispatch Lambda does NOT get an SQS event source mapping.
# notification-service (port 8008) already polls aerolink-notifications via long-poll,
# persists to DB, and sends SES email. Adding a Lambda SQS trigger would cause both
# to compete for the same messages. notification-dispatch exists as a utility Lambda
# that can be invoked directly for debugging or fallback purposes.
echo "Skipped SQS->notification-dispatch mapping (notification-service owns queue polling)"

# --- Lambda 2: Boarding Pass Generator (EventBridge-triggered, needs fpdf2) ---
echo "Packaging boarding_pass_generator Lambda..."
cd /tmp && rm -rf lambda_boarding && mkdir lambda_boarding
cp $LAMBDA_SRC/boarding_pass_generator/handler.py lambda_boarding/
pip install fpdf2 -t lambda_boarding/ --quiet 2>/dev/null
cd lambda_boarding && zip -r /tmp/boarding_pass_generator.zip .

awslocal lambda create-function \
  --function-name boarding-pass-generator \
  --runtime python3.10 \
  --handler handler.handler \
  --role "$LAMBDA_ROLE_ARN" \
  --zip-file fileb:///tmp/boarding_pass_generator.zip \
  --timeout 60 \
  --memory-size 256 \
  --architectures arm64 \
  --environment "Variables={S3_BUCKET=aerolink-documents,AWS_ENDPOINT_URL=http://host.docker.internal:4566,AWS_DEFAULT_REGION=eu-west-1}"

echo "Created Lambda: boarding-pass-generator"

# Get Lambda ARN for EventBridge target
BOARDING_PASS_LAMBDA_ARN=$(awslocal lambda get-function \
  --function-name boarding-pass-generator \
  --query 'Configuration.FunctionArn' --output text)

# Add boarding-pass-generator as a second target on the existing CheckInCompleted rule
awslocal events put-targets \
  --rule checkin-completed-to-notifications \
  --event-bus-name aerolink-events \
  --targets "Id=boarding-pass-lambda,Arn=$BOARDING_PASS_LAMBDA_ARN"

# Grant EventBridge permission to invoke the boarding pass Lambda
awslocal lambda add-permission \
  --function-name boarding-pass-generator \
  --statement-id eventbridge-checkin-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:eu-west-1:000000000000:rule/aerolink-events/checkin-completed-to-notifications"

echo "Added boarding-pass-generator as target for CheckInCompleted events"

# --- Lambda 3: Pricing Recalculation (scheduled, uses pg8000 pure-Python driver) ---
echo "Packaging pricing_recalculation Lambda..."
cd /tmp && rm -rf lambda_pricing && mkdir lambda_pricing
cp $LAMBDA_SRC/pricing_recalculation/handler.py lambda_pricing/
pip install pg8000 -t lambda_pricing/ --quiet 2>/dev/null
cd lambda_pricing && zip -r /tmp/pricing_recalculation.zip .

awslocal lambda create-function \
  --function-name pricing-recalculation \
  --runtime python3.10 \
  --handler handler.handler \
  --role "$LAMBDA_ROLE_ARN" \
  --zip-file fileb:///tmp/pricing_recalculation.zip \
  --timeout 120 \
  --memory-size 256 \
  --architectures arm64 \
  --environment "Variables={DB_HOST=postgres,DB_PORT=5432,DB_NAME=aerolink,DB_USER=aerolink,DB_PASSWORD=aerolink,AWS_DEFAULT_REGION=eu-west-1}"

echo "Created Lambda: pricing-recalculation"

# Get Lambda ARN for CloudWatch Events target
PRICING_LAMBDA_ARN=$(awslocal lambda get-function \
  --function-name pricing-recalculation \
  --query 'Configuration.FunctionArn' --output text)

# Create CloudWatch scheduled rule (every 5 minutes)
awslocal events put-rule \
  --name pricing-recalculation-schedule \
  --schedule-expression "rate(5 minutes)" \
  --state ENABLED

awslocal events put-targets \
  --rule pricing-recalculation-schedule \
  --targets "Id=pricing-lambda,Arn=$PRICING_LAMBDA_ARN"

# Grant EventBridge permission to invoke the pricing Lambda
awslocal lambda add-permission \
  --function-name pricing-recalculation \
  --statement-id eventbridge-schedule-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:eu-west-1:000000000000:rule/pricing-recalculation-schedule"

echo "Created scheduled rule: pricing-recalculation-schedule (rate: 5 minutes)"

# ──────────────────────────────────────────────

# List all created resources
echo ""
echo "=== AeroLink AWS Resources Summary ==="
echo "EventBridge Bus: aerolink-events"
awslocal events list-rules --event-bus-name aerolink-events --query 'Rules[].Name' --output table
echo ""
echo "SQS Queues:"
awslocal sqs list-queues --query 'QueueUrls' --output table
echo ""
echo "S3 Buckets:"
awslocal s3 ls
echo ""
echo "DynamoDB Tables:"
awslocal dynamodb list-tables --output table
echo ""
echo "Lambda Functions:"
awslocal lambda list-functions --query 'Functions[].FunctionName' --output table
echo ""
echo "=== Initialization Complete ==="
