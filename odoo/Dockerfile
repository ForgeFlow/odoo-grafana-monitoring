FROM odoo:16.0

USER root
RUN --mount=type=bind,source=addons,target=/mnt/extra-addons \
    pip3 install -r /mnt/extra-addons/monitoring_otel/requirements.txt
USER odoo
