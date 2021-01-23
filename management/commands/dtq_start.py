import signal

from django.conf import settings
from django.core.management.base import BaseCommand

from django_task_queue.util import import_class


class Command(BaseCommand):

    def handle(self, *args, **options):
        dtq_settings = {}
        if hasattr(settings, 'DJANGO_TASK_QUEUE'):
            dtq_settings = settings.DJANGO_TASK_QUEUE
        worker_class_names = dtq_settings.get('WORKERS', ['django_task_queue.workers.BaseWorker'])
        workers = [import_class(name)() for name in worker_class_names]

        def signal_handler(signum, frame):
            print('Signal received: %s, %s' % (signum, frame))
            [t.signal_handler(signum, frame) for t in workers]

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        [w.start() for w in workers]
        [w.join() for w in workers]
