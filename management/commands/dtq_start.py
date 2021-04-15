from django.core.management.base import BaseCommand

from django_task_queue import workers


class Command(BaseCommand):

    def handle(self, *args, **options):
        workers.start_all_workers()
