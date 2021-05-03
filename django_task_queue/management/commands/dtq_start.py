from django.core.management.base import BaseCommand

from django_task_queue.workers import AllWorkersThread


class Command(BaseCommand):

    def handle(self, *args, **options):
        thread = AllWorkersThread()
        thread.start()
