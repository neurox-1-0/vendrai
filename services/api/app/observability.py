from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings
from app.database import engine

_configured = False


def _provider(service_name: str) -> TracerProvider:
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": settings.APP_ENV,
            }
        )
    )
    exporter = OTLPSpanExporter(
        endpoint=f"{settings.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip('/')}/v1/traces"
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def configure_observability(app, service_name: str | None = None) -> None:
    global _configured
    if _configured or not settings.OTEL_ENABLED:
        return
    provider = _provider(service_name or settings.OTEL_SERVICE_NAME)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="health/live,health/ready",
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine,
        tracer_provider=provider,
        enable_commenter=False,
    )
    _configured = True


def configure_worker_observability(worker_name: str) -> None:
    global _configured
    if _configured or not settings.OTEL_ENABLED:
        return
    from app.workers.database import worker_engine

    provider = _provider(f"neurox-{worker_name}")
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    SQLAlchemyInstrumentor().instrument(
        engine=worker_engine.sync_engine,
        tracer_provider=provider,
        enable_commenter=False,
    )
    _configured = True


def current_traceparent() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return f"00-{context.trace_id:032x}-{context.span_id:016x}-01"
