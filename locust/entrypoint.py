#!/usr/bin/env python3

import random

import gevent
from locust import HttpUser, task, between
from locust.env import Environment
from locust.log import setup_logging
from locust.stats import stats_history, stats_printer

# https://docs.locust.io/en/stable/writing-a-locustfile.html
class BasicUser(HttpUser):
    host = "http://odoo:8069"
    wait_time = between(1, 5)

    @task(5)
    def dummy_sleep(self):
        seconds = random.randrange(1, 10)
        self.client.get(f"/dummy/sleep/{seconds}")

    @task(3)
    def dummy_database(self):
        iterations = random.randrange(100, 10000)
        self.client.get(f"/dummy/database/{iterations}")

    @task(2)
    def dummy_pass(self):
        self.client.get("/dummy/pass")

    @task(1)
    def dummy_error(self):
        self.client.get("/dummy/error")

# https://docs.locust.io/en/latest/use-as-lib.html
setup_logging("INFO")
env = Environment(user_classes=[BasicUser])
runner = env.create_local_runner()
web_ui = env.create_web_ui("0.0.0.0", 8089)

gevent.spawn(stats_printer(env.stats))
gevent.spawn(stats_history, env.runner)
runner.start(5, spawn_rate=1)

runner.greenlet.join()
web_ui.stop()
