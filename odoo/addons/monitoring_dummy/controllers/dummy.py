import time
import random

from odoo.http import Controller, route, request
from odoo.exceptions import UserError

class MonitoringDummyController(Controller):
    @route("/dummy/sleep/<int:seconds>", auth="public", methods=["GET"])
    def dummy_sleep(self, seconds):
        seconds = max(2, seconds)
        python_seconds = random.randrange(1, seconds)
        postgres_seconds = seconds - python_seconds
        request.env["monitoring.dummy"].dummy_python_sleep(python_seconds)
        request.env["monitoring.dummy"].dummy_postgres_sleep(postgres_seconds)
        return "OK"

    @route("/dummy/database/<int:iterations>", auth="public", methods=["GET"])
    def dummy_database(self, iterations):
        iterations = max(1, iterations)
        request.env["monitoring.dummy"].dummy_postgres_work(iterations)
        return "OK"

    @route("/dummy/pass", auth="public", methods=["GET"])
    def dummy_pass(self):
        return "OK"

    @route("/dummy/error", auth="public", methods=["GET"])
    def dummy_error(self):
        raise UserError("ERROR")
