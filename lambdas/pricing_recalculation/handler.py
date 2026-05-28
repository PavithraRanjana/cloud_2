"""
Lambda 3: Flight Pricing Recalculation
Triggered by CloudWatch scheduled rule (every 5 minutes).
Connects to PostgreSQL to read flight seat availability and adjust prices
using a demand-based algorithm.
Dependencies: psycopg2-binary
"""

import json
import logging
import os

import boto3
import psycopg2

logger = logging.getLogger("pricing_recalculation")
logger.setLevel(logging.INFO)

# PostgreSQL connection parameters
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "aerolink")
DB_USER = os.environ.get("DB_USER", "aerolink")

# DB credentials live in Secrets Manager (managed by RDS). DB_SECRET_ARN points
# at the rds!db-* secret. Fetched once per cold start. If unset, fall back to
# DB_USER + DB_PASSWORD env vars for local dev.
_DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN", "")
_secrets_client = boto3.client("secretsmanager") if _DB_SECRET_ARN else None


def _db_credentials() -> tuple[str, str]:
    if _secrets_client:
        resp = _secrets_client.get_secret_value(SecretId=_DB_SECRET_ARN)
        creds = json.loads(resp["SecretString"])
        return creds.get("username", DB_USER), creds["password"]
    return DB_USER, os.environ.get("DB_PASSWORD", "aerolink")

# Pricing algorithm constants
HIGH_DEMAND_THRESHOLD = 0.20   # <20% seats remaining -> price increase
LOW_DEMAND_THRESHOLD = 0.80    # >80% seats remaining -> price decrease
HIGH_DEMAND_MULTIPLIER = 1.15  # +15%
LOW_DEMAND_MULTIPLIER = 0.90   # -10%

# Price bounds per class
PRICE_BOUNDS = {
    "economy":  {"min": 49.99,  "max": 999.99},
    "business": {"min": 149.99, "max": 2499.99},
    "first":    {"min": 299.99, "max": 4999.99},
}


def _clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(value, max_val))


def _adjust_price(current_price: float, available: int, total: int,
                  seat_class: str) -> float:
    """Apply demand-based pricing adjustment."""
    if total <= 0:
        return current_price

    availability_ratio = available / total
    bounds = PRICE_BOUNDS[seat_class]

    if availability_ratio < HIGH_DEMAND_THRESHOLD:
        new_price = current_price * HIGH_DEMAND_MULTIPLIER
    elif availability_ratio > LOW_DEMAND_THRESHOLD:
        new_price = current_price * LOW_DEMAND_MULTIPLIER
    else:
        return current_price  # No change for mid-range availability

    return round(_clamp(new_price, bounds["min"], bounds["max"]), 2)


def handler(event, context):
    """
    CloudWatch scheduled event handler.
    Queries all flights with status='scheduled' and adjusts prices
    based on seat availability.
    """
    logger.info("Pricing recalculation started")

    user, password = _db_credentials()
    conn = psycopg2.connect(
        host=DB_HOST, port=int(DB_PORT), dbname=DB_NAME,
        user=user, password=password, sslmode="require",
    )
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, flight_number,
                   total_seats_economy,  available_seats_economy,  price_economy,
                   total_seats_business, available_seats_business, price_business,
                   total_seats_first,    available_seats_first,    price_first
            FROM flights
            WHERE status::text = 'SCHEDULED'
        """)
        flights = cursor.fetchall()
        logger.info("Found %d scheduled flights to evaluate", len(flights))

        updated = 0
        for row in flights:
            (flight_id, flight_number,
             total_eco, avail_eco, price_eco,
             total_biz, avail_biz, price_biz,
             total_first, avail_first, price_first) = row

            new_eco = _adjust_price(float(price_eco), avail_eco, total_eco, "economy")
            new_biz = _adjust_price(float(price_biz), avail_biz, total_biz, "business")
            new_fst = _adjust_price(float(price_first), avail_first, total_first, "first")

            if (new_eco != float(price_eco) or new_biz != float(price_biz)
                    or new_fst != float(price_first)):
                cursor.execute("""
                    UPDATE flights
                    SET price_economy = %s,
                        price_business = %s,
                        price_first = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (new_eco, new_biz, new_fst, str(flight_id)))
                updated += 1
                logger.info(
                    "Updated %s: economy %.2f->%.2f, business %.2f->%.2f, first %.2f->%.2f",
                    flight_number,
                    float(price_eco), new_eco, float(price_biz), new_biz,
                    float(price_first), new_fst,
                )

        conn.commit()
        logger.info("Pricing recalculation complete: %d/%d flights updated", updated, len(flights))

        return {
            "statusCode": 200,
            "body": json.dumps({"evaluated": len(flights), "updated": updated}),
        }

    except Exception as e:
        conn.rollback()
        logger.error("Pricing recalculation failed: %s", str(e))
        raise
    finally:
        cursor.close()
        conn.close()
