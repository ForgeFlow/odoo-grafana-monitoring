# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Monitoring OpenTelemetry",
    "summary": "Export Odoo telemetry using OpenTelemetry",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "ForgeFlow",
    "website": "https://gitlab.forgeflow.io/forgeflow/cloud-odoo-addons",
    "external_dependencies": {
        "python": [
            "opentelemetry-api", "opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-grpc",
            "opentelemetry-instrumentation-wsgi", "opentelemetry-instrumentation-psycopg2"
        ]
    },
    "post_load": "post_load",
}
