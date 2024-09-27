import time
import logging

from odoo import models

_logger = logging.getLogger(__name__)

class MonitoringDummy(models.Model):
    _name = "monitoring.dummy"
    _description = "Dummy functions to generate monitoring data"

    def dummy_python_sleep(self, seconds):
        time.sleep(seconds)

    def dummy_postgres_sleep(self, seconds):
        self.env.cr.execute(f"SELECT PG_SLEEP({seconds})")

    def dummy_postgres_work(self, iterations):
        for i in range(iterations):
            values = ",".join([f"({i})" for j in range(i, i+10)])
            self.env.cr.execute(f"""
                SELECT SUM(value)
                FROM (VALUES {values})
                AS v(value)
            """)
