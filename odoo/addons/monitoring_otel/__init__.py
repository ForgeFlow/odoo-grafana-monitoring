# https://odoo-development.readthedocs.io/en/latest/dev/hooks/post_load.html
import os
import time
import logging
import threading
from uuid import uuid4

from opentelemetry import _logs, metrics, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

import odoo
from odoo.netsvc import (
    PerfFilter,
    DBFormatter,
    WatchedFileHandler,
)
from odoo.service.server import (
    PreforkServer,
    Worker,
    WorkerHTTP,
    WorkerCron,
)

_logger = logging.getLogger(__name__)

def post_load():
    module = __name__.split(".")[-1]
    if module not in odoo.conf.server_wide_modules:
        _logger.error("Module not loaded as server-wide, aborting")
        return

    if odoo.evented:
        odoo_patch_gevent()
    elif odoo.tools.config["workers"]:
        odoo_patch_prefork()
    else:
        _logger.warning("Threaded mode unsupported")

# https://github.com/odoo/odoo/blob/16.0/odoo/service/server.py
def odoo_patch_gevent():
    resource = otel_create_resource()
    otel_configure_metrics_provider(resource)
    otel_metrics = metrics.get_meter("odoo")
    otel_deployment_info = otel_metrics.create_observable_gauge(
        "odoo.deployment_info",
        description="Basic deployment information / presence check",
        callbacks=[lambda _: (yield metrics.Observation(1, {"major_version": odoo.release.major_version}))]
    )

# https://grafana.com/docs/grafana-cloud/monitor-applications/application-observability/instrument/python/#global-interpreter-lock
def odoo_patch_prefork():
    def http_run(self):
        otel_configure_providers()
        if os.environ.get("ODOO_INSTRUMENT_LOGS"):
            otel_instrument_logs()
        if os.environ.get("ODOO_INSTRUMENT_METRICS"):
            otel_instrument_http_metrics()
        if os.environ.get("ODOO_INSTRUMENT_LIBRARIES"):
            otel_instrument_libraries(os.environ["ODOO_INSTRUMENT_LIBRARIES"])
        Worker.run(self)

    def cron_run(self):
        otel_configure_providers()
        if os.environ.get("ODOO_INSTRUMENT_LOGS"):
            otel_instrument_logs()
        if os.environ.get("ODOO_INSTRUMENT_METRICS"):
            otel_instrument_cron_metrics()
        if os.environ.get("ODOO_INSTRUMENT_LIBRARIES"):
            otel_instrument_libraries(os.environ["ODOO_INSTRUMENT_LIBRARIES"])
        Worker.run(self)

    WorkerHTTP.run = http_run
    WorkerCron.run = cron_run

def otel_configure_providers():
    resource = otel_create_resource()
    otel_configure_logs_provider(resource)
    otel_configure_metrics_provider(resource)
    otel_configure_traces_provider(resource)

def otel_create_resource():
    attributes = {
        "service.name": "odoo",
        "service.namespace": os.uname().nodename,
        "service.version": odoo.release.version,
        "service.instance.id": str(uuid4()), # Do we want this?
        "deployment.environment": os.environ.get("ODOO_ENVIRONMENT", "unknown"),
        "worker": os.getpid(),
    }
    resource = Resource.create(attributes)
    return resource

def otel_configure_logs_provider(resource):
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    _logs.set_logger_provider(provider)

def otel_configure_metrics_provider(resource):
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

def otel_configure_traces_provider(resource):
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

def otel_instrument_libraries(libraries):
    libraries = libraries.split(",")
    for library in libraries:
        if library in otel_library_instrumentation:
            _logger.info(f"Instrumenting library '{library}'")
            otel_library_instrumentation[library]()
        else:
            _logger.warning(f"Instrumentation for library '{library}' not found")

# https://github.com/odoo/odoo/blob/16.0/odoo/http.py
# https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation/opentelemetry-instrumentation-wsgi/src/opentelemetry/instrumentation/wsgi
# https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/wsgi/wsgi.html
def otel_instrument_wsgi():
    os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = "http"
    PatchedApplication = type("PatchedApplication", (OpenTelemetryMiddleware, odoo.http.Application), {})
    odoo.http.root = PatchedApplication(odoo.http.root)

# https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation/opentelemetry-instrumentation-psycopg2/src/opentelemetry/instrumentation/psycopg2
# https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/psycopg2/psycopg2.html
def otel_instrument_psycopg2():
    Psycopg2Instrumentor().instrument()

def otel_instrument_logs():
    # https://github.com/open-telemetry/opentelemetry-python/issues/3389
    class CustomHandler(LoggingHandler):
        def emit(self, record):
            if isinstance(record.msg, Exception):
                record.msg = str(record.msg)
            super().emit(record)

    formatter = DBFormatter("%(asctime)s %(pid)s %(levelname)s %(dbname)s %(name)s: %(message)s %(perf_info)s")
    handler = CustomHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    # Ensure our handler processes records before the default handler adds colors
    root_logger.addHandler(root_logger.handlers.pop(0))

# https://github.com/odoo/odoo/blob/16.0/odoo/netsvc.py
def otel_instrument_http_metrics():
    otel_metrics = metrics.get_meter("odoo")
    otel_query_count = otel_metrics.create_gauge(
        "odoo.query_count",
        description="Number of SQL queries performed during the request"
    )
    otel_query_time = otel_metrics.create_gauge(
        "odoo.query_time",
        description="Time spent performing SQL queries during the request"
    )
    otel_remaining_time = otel_metrics.create_gauge(
        "odoo.remaining_time",
        description="Time spent not performing SQL queries during the request"
    )

    class MetricsFilter(PerfFilter):
        def filter(self, record):
            if hasattr(threading.current_thread(), "query_count"):
                query_count = threading.current_thread().query_count
                query_time = threading.current_thread().query_time
                perf_t0 = threading.current_thread().perf_t0
                remaining_time = time.time() - perf_t0 - query_time
                otel_query_count.set(query_count)
                otel_query_time.set(query_time)
                otel_remaining_time.set(remaining_time)
            return super().filter(record)

    werkzeug_logger = logging.getLogger("werkzeug")
    for filt in werkzeug_logger.filters:
        if isinstance(filt, PerfFilter):
            werkzeug_logger.removeFilter(filt)

    metrics_filter = MetricsFilter()
    logging.getLogger("werkzeug").addFilter(metrics_filter)

# TODO: measure cron duration, failures, etc.
def otel_instrument_cron_metrics():
    pass

otel_library_instrumentation = {}
otel_library_instrumentation["wsgi"] = otel_instrument_wsgi
otel_library_instrumentation["psycopg2"] = otel_instrument_psycopg2
