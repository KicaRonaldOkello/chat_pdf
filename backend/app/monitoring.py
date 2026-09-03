"""Observability plumbing: Loki logs, Prometheus metrics, OpenTelemetry tracing.

All are optional — gated by ``settings.*_enabled`` flags so existing
deployments are unaffected.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
from typing import Any

import httpx
from fastapi import FastAPI

log = logging.getLogger(__name__)

# ── Loki log shipping ────────────────────────────────────────────────────────
# Loki accepts JSON push payloads at /loki/api/v1/push.  We use a background
# thread (QueueListener) so that HTTP latency never blocks the caller.

_LOKI_PUSH_PATH = "/loki/api/v1/push"


class _LokiHttpHandler(logging.Handler):
    """Batch-friendly handler: the listener calls ``emit_logs`` with a list."""

    def __init__(self, url: str, application: str, *, http_client: httpx.Client | None = None) -> None:
        super().__init__()
        self._push_url = f"{url.rstrip('/')}{_LOKI_PUSH_PATH}"
        self._application = application
        self._client = http_client or httpx.Client(timeout=5.0)

    def emit_logs(self, records: list[logging.LogRecord]) -> None:
        """Called by QueueListener with a batch of records."""
        streams: dict[str, list[list[str]]] = {}
        for rec in records:
            ts_ns = str(int(rec.created * 1_000_000_000))
            line = self.format(rec)
            # Key streams by application+level so Loki labels stay well-behaved
            stream_key = json.dumps(
                {"application": self._application, "level": rec.levelname},
                sort_keys=True,
            )
            streams.setdefault(stream_key, []).append([ts_ns, line])

        payload = {
            "streams": [
                {"stream": json.loads(k), "values": v} for k, v in streams.items()
            ]
        }
        try:
            self._client.post(
                self._push_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except Exception:
            # Loki is best-effort — never crash the app because logs can't ship
            pass

    # emit is used when the handler is attached directly (no QueueListener).
    # In practice the QueueListener calls emit_logs above instead.
    def emit(self, record: logging.LogRecord) -> None:
        self.emit_logs([record])


_LOKI_JSON_FORMATTER = logging.Formatter(
    json.dumps(
        {
            "timestamp": "%(asctime)s",
            "logger": "%(name)s",
            "level": "%(levelname)s",
            "message": "%(message)s",
        }
    ),
    datefmt="%Y-%m-%dT%H:%M:%S",
)


def setup_loki_logging(url: str, application: str) -> None:
    """Ship structured JSON logs to a Loki instance via HTTP push.

    A background QueueListener is used so network latency never blocks the
    calling thread.  Noisy third-party loggers are dialled down to WARNING
    so they don't flood Loki with DEBUG/INFO chatter.
    """
    loki_handler = _LokiHttpHandler(url, application)
    loki_handler.setFormatter(_LOKI_JSON_FORMATTER)
    loki_handler.setLevel(logging.INFO)

    queue: Queue[Any] = Queue(maxsize=8192)
    qh = QueueHandler(queue)
    listener = QueueListener(queue, loki_handler, respect_handler_level=True)
    listener.start()

    root = logging.getLogger()
    root.addHandler(qh)

    # Keep verbose third-party libraries at WARNING so they don't flood Loki
    # (httpx & openai are already set in main.py; add a few more here)
    for pkg in ("azure.core", "botocore", "urllib3", "httpcore"):
        logging.getLogger(pkg).setLevel(logging.WARNING)

    log.info("Loki logging enabled → %s", url)


# ── Prometheus metrics ───────────────────────────────────────────────────────


def setup_prometheus(app: FastAPI) -> None:
    """Expose ``GET /metrics`` with request rate, latency & in-flight gauges."""
    from prometheus_fastapi_instrumentator import Instrumentator

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=False,
        should_instrument_requests_inprogress=True,
    )
    instrumentator.instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        # Exclude health/metrics endpoints so they don't drown signal
        should_gzip=False,
    )
    # Silence the built-in metric about the metrics endpoint itself
    try:
        from prometheus_fastapi_instrumentator.metrics import default_metric_namespaces

        for ns in default_metric_namespaces:
            ns.should_include_handler = lambda handler, ns=ns: not any(
                x in str(handler) for x in ("/api/health", "/metrics")
            )
    except Exception:
        pass


# ── OpenTelemetry tracing ───────────────────────────────────────────────────


def setup_opentelemetry(service_name: str, endpoint: str) -> None:
    """Enable distributed tracing via OTLP HTTP exporter.

    Instruments FastAPI (inbound requests), httpx (outbound HTTP), and
    SQLAlchemy (database queries) automatically.  Traces are exported to
    *endpoint* (e.g. ``http://localhost:4318``) — typically an OpenTelemetry
    Collector or Grafana Alloy instance.

    Must be called **before** any instrumented library is used, so we call it
    early in the FastAPI lifespan.
    """
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument libraries (FastAPI is done via _instrument_fastapi_app
    # so it sees the final app instance)
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument(
        enable_commenter=True, commenter_options={}
    )

    log.info(
        "OpenTelemetry tracing enabled — service=%s → %s",
        service_name,
        endpoint,
    )


def _instrument_fastapi_app(app: FastAPI) -> None:
    """Attach OTel instrumentation to an already-created FastAPI app.

    Called from main.py *after* the FastAPI() constructor so the instrumentor
    sees the final app.
    """
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls=",".join(
            ["/api/health", "/metrics", "/openapi.json", "/docs", "/redoc"]
        ),
    )
