import logging
import sys
import structlog
from opentelemetry import trace


def _add_otel_context(logger, method, event_dict):
    """Inject OpenTelemetry trace_id and span_id into every structured log record."""
    try:
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            ctx = current_span.get_span_context()
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:
        pass
    return event_dict


def setup_logging():
    # Configure stdlib logging to pass messages to structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_otel_context,               # OpenTelemetry trace correlation
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
