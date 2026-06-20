import os
import logging
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import SpanKind

logger = logging.getLogger("logi-resilience")

def setup_telemetry(app=None, service_name="logi-resilience-backend"):
    """
    Sets up the OpenTelemetry TracerProvider, hooks up the Jaeger OTLP span exporter,
    and instruments FastAPI (if provided).
    """
    resource = Resource(attributes={
        ResourceAttributes.SERVICE_NAME: service_name
    })

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Use OTLP Exporter to send traces to Jaeger
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
    
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        span_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(span_processor)
        logger.info("OpenTelemetry OTLP Exporter configured for Jaeger at %s", otlp_endpoint)
    except Exception as exc:
        logger.warning("Failed to configure OpenTelemetry OTLP Exporter: %s", exc)

    # Instrument FastAPI if app context exists
    if app:
        FastAPIInstrumentor.instrument_app(app)


# Celery Context Propagation Signals
# These connect automatic tracing context propagation between FastAPI (producer) and Celery workers (consumer)
try:
    from celery.signals import before_task_publish, task_prerun, task_postrun, worker_process_init
    
    @worker_process_init.connect
    def setup_celery_worker_telemetry(*args, **kwargs):
        """
        Runs inside the Celery worker process upon initialization. Sets up trace provider.
        """
        logger.info("Initializing OpenTelemetry TracerProvider inside Celery worker process...")
        setup_telemetry(app=None, service_name="logi-resilience-worker")

    @before_task_publish.connect
    def before_task_publish_handler(headers=None, properties=None, **kwargs):
        """
        Runs on client side when dispatching task. Inject the trace context into headers.
        """
        if headers is None:
            return
        propagate.inject(headers)

    @task_prerun.connect
    def task_prerun_handler(task_id, task, *args, **kwargs):
        """
        Runs on worker side before task starts. Extract context and start span.
        """
        request = task.request
        headers = getattr(request, "headers", {})
        context = propagate.extract(headers) if headers else None
        
        tracer = trace.get_tracer("celery-worker")
        span = tracer.start_span(
            f"celery_task: {task.name}",
            context=context,
            kind=SpanKind.CONSUMER
        )
        task.__active_span = span
        
        # Attach span to local execution context
        from opentelemetry.trace import set_span_in_context
        ctx = set_span_in_context(span)
        from opentelemetry.context import attach
        task.__active_token = attach(ctx)

    @task_postrun.connect
    def task_postrun_handler(task_id, task, state, retval, *args, **kwargs):
        """
        Runs on worker side when task completes. Detach context and end span.
        """
        token = getattr(task, "__active_token", None)
        if token:
            from opentelemetry.context import detach
            detach(token)
            
        span = getattr(task, "__active_span", None)
        if span:
            if state == "FAILURE":
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(retval))
            span.end()
except ImportError:
    logger.debug("Celery signals skipped because Celery is not installed or available in this context.")
