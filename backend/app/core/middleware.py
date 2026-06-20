import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP Requests",
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP Request Latency",
    ["method", "endpoint"]
)

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path

        # Don't track metrics endpoint itself to avoid infinite loops/noise
        if endpoint == "/metrics":
            return await call_next(request)

        start_time = time.time()
        status = "500"
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        except Exception as e:
            raise e
        finally:
            duration = time.time() - start_time
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects production-grade security headers and a unique request ID into every response."""

    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID for distributed tracing correlation
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        response = await call_next(request)

        # Core security headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # Content Security Policy — allows DeckGL, Chart.js, CARTO tiles
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com; "
            "font-src 'self' fonts.gstatic.com; "
            "img-src 'self' data: blob: *.cartocdn.com *.openstreetmap.org; "
            "connect-src 'self' ws: wss: api.gdeltproject.org api.openweathermap.org gcaptain.com; "
            "frame-ancestors 'none';"
        )

        # Only set HSTS in production (breaks local HTTP dev)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        return response
