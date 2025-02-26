from argparse import ArgumentParser

from django.core.management.base import BaseCommand

import django_task_queue as dtq
from ... import _util

from django.conf import settings


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser):
        parser.add_argument("--noconfig", default=False, action="store_true")

    def handle(self, noconfig: bool, **options):
        attr = "DJANGO_TASK_QUEUE"
        wg = dtq.WorkerGroup([dtq.Worker()])

        if noconfig:
            print(f"Ignoring config.")
        elif not hasattr(settings, attr):
            print(f"No {attr} setting found. Creating default worker.")
        else:
            print(f"{attr} setting found. Creating worker group...")
            dtq_settings = settings.DJANGO_TASK_QUEUE
            wg = dtq.WorkerGroup.from_settings(dtq_settings)

        _util.run_worker_until_stopped(wg)
