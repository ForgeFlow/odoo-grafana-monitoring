FROM odoo:16.0

USER root
ADD config /etc/odoo
ADD addons /mnt/extra-addons
RUN pip3 install -r /mnt/extra-addons/monitoring_otel/requirements.txt
USER odoo
