"""
Trace-ID middleware for structlog context propagation.

Extracts X-Trace-Id from incoming requests (set by api-gateway) or
generates a new one, then binds it to the structlog context so every
log line emitted within the request includes the trace_id field.

Usage in each service's main.py:
    from shared.tracing import TraceMiddleware
    app.add_middleware(TraceMiddleware)
"""
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response
