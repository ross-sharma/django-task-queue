from django.core.management.base import BaseCommand

from django_task_queue.models import FailedTask, Task


class Command(BaseCommand):

    def handle(self, *args, **options):
        Task.objects.all().delete()
        FailedTask.objects.all().delete()
        print("All Task and FailedTask objects deleted.")
