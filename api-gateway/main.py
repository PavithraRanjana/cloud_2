import sys
import os
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import structlog
from shared.config import BaseConfig
from shared.auth import decode_token
from shared.logging import setup_logging
from shared.tracing import TraceMiddleware

config = BaseConfig(service_name="api-gateway")
setup_logging(config.service_name)
logger = structlog.get_logger()

START_TIME = time.time()

# Route table: path prefix -> service URL
ROUTES = {
    "/api/v1/auth": config.auth_service_url,
    "/api/v1/flights": config.flight_service_url,
    "/api/v1/bookings": config.booking_service_url,
    "/api/v1/payments": config.payment_service_url,
    "/api/v1/baggage": config.baggage_service_url,
    "/api/v1/checkin": config.checkin_service_url,
    "/api/v1/passengers": config.passenger_service_url,
    "/api/v1/notifications": config.notification_service_url,
}

# Endpoints that don't require JWT
PUBLIC_PATHS = {
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/flights",
    "/api/v1/payments/stripe/webhook",  # Stripe authenticates via signature header
    "/health",
}

app = FastAPI(title="AeroLink API Gateway", version="1.0.0")
app.add_middleware(TraceMiddleware)

_cors_origins_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def is_public_path(path: str) -> bool:
    for public in PUBLIC_PATHS:
        if path.startswith(public):
            return True
    return False


def resolve_service(path: str) -> str | None:
    for prefix, url in sorted(ROUTES.items(), key=lambda x: -len(x[0])):
        if path.startswith(prefix):
            return url
    return None


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "api-gateway",
        "uptime_seconds": time.time() - START_TIME,
        "routes": list(ROUTES.keys()),
    }


@app.get("/debug/token")
async def debug_token(request: Request):
    """Temporary: returns the exact token validation error for the provided Bearer token."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return {"error": "No Bearer token provided"}
    token = auth_header.split(" ", 1)[1]
    try:
        user = decode_token(token, secret=config.jwt_secret)
        return {"valid": True, "user": user}
    except Exception as e:
        return {"valid": False, "error": str(e), "error_type": type(e).__name__}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gateway_proxy(request: Request, path: str):
    full_path = f"/{path}"
    trace_id = str(uuid.uuid4())

    client_ip = request.client.host if request.client else "unknown"

    # Authentication for protected paths
    if not is_public_path(full_path):
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ", 1)[1]
                decode_token(token, secret=config.jwt_secret)
            except Exception as e:
                logger.warning("auth_failed", error=str(e), path=full_path)
                raise HTTPException(status_code=401, detail="Invalid or expired token")
        else:
            raise HTTPException(status_code=401, detail="Missing authorization header")

    # Route to service
    service_url = resolve_service(full_path)
    if not service_url:
        raise HTTPException(status_code=404, detail="Route not found")

    target_url = f"{service_url}{full_path}"

    # Forward request
    headers = dict(request.headers)
    headers["X-Trace-Id"] = trace_id
    headers["X-Forwarded-For"] = client_ip
    # Remove host header to avoid conflicts
    headers.pop("host", None)

    body = await request.body()

    logger.info("gateway_request",
                method=request.method, path=full_path,
                target=target_url, trace_id=trace_id)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=dict(request.query_params),
            )

        logger.info("gateway_response",
                     method=request.method, path=full_path,
                     status=resp.status_code, trace_id=trace_id)

        from fastapi.responses import Response
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers),
            media_type=resp.headers.get("content-type"),
        )
    except httpx.ConnectError:
        logger.error("service_unavailable", target=service_url, trace_id=trace_id)
        raise HTTPException(status_code=503, detail=f"Service unavailable")
    except httpx.ReadTimeout:
        logger.error("service_timeout", target=service_url, trace_id=trace_id)
        raise HTTPException(status_code=504, detail="Service timeout")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
