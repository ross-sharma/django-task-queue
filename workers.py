import logging
import signal
import threading
import time
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .exceptions import NoEligibleTaskException, FatalTaskException, NoIncrementErrorCountException
from .models import Task
from . import util


class BaseWorker(threading.Thread):

    DEFAULT_MIN_SECONDS_BETWEEN_PROCESSING_ATTEMPTS = 60

    def __init__(self, tags=None, log=logging.getLogger(__name__)):
        self.tags = tags or ['__default__']
        self.lock_id = uuid4()
        self.min_seconds_between_processing_attempts = self.DEFAULT_MIN_SECONDS_BETWEEN_PROCESSING_ATTEMPTS
        self._log = log
        self._stop_flag = threading.Event()
        self._log_prefix = f'({self.__class__.__name__}, {self.tags})'
        super().__init__()

    def run(self):
        self.log('Thread starting.')
        while not self._stop_flag.is_set():
            try:
                self.process_one()
            except NoEligibleTaskException:
                self.log('No eligible task found. Sleeping.', level=logging.DEBUG)
                print('Task daemon: sleeping')
                time.sleep(1)
        else:
            self.log('Stop flag set. Thread terminating.')

    def log(self, msg, level=logging.INFO):
        msg = f'{self._log_prefix} {msg}'
        self._log.log(level=level, msg=msg)

    def log_exception(self, exc):
        self._log.exception(exc)

    def __filter(self, *args, **kwargs):
        return Task.objects.filter(tag__in=self.tags, *args, **kwargs)

    def __filter_eligible(self):
        last_attempt_limit = timezone.now() - timedelta(seconds=self.min_seconds_between_processing_attempts)

        tasks = self.__filter(lock_id='')
        return tasks.filter(retry_allowed=True).filter(
            Q(last_attempt_datetime__isnull=True) | Q(last_attempt_datetime__lte=last_attempt_limit)
        )

    def signal_handler(self, signum, frame):
        if signum in (signal.SIGTERM, signal.SIGINT):
            self._stop_flag.set()

    @property
    def count(self):
        return self.__filter().count()

    @property
    def count_processing(self):
        return self.__filter().exclude(lock_id='').count()

    @property
    def count_eligible(self):
        return self.__filter_eligible().count()

    @transaction.atomic
    def pop(self):
        tasks = self.__filter_eligible()

        if not tasks.count():
            return None

        tasks = tasks.order_by('priority', 'created_datetime')
        task = tasks[0]
        task.lock_id = self.lock_id
        task.last_attempt_datetime = timezone.now()
        task.save()
        return task

    def process_one(self, task=None):
        task = task or self.pop()
        if not task:
            raise NoEligibleTaskException

        self.log('Processing task: %s' % task)
        queue = util.import_class(task.queue_class_name)()

        try:
            result = queue.process(**task.data)
            self.log('Task processed. Result: %s' % result)
            task.delete()
            return result
        except Exception as e:
            is_no_increment = isinstance(e, NoIncrementErrorCountException)
            if not is_no_increment:
                self.log_exception(e)
                task.error_count += 1
            else:
                self.log('No increment error: %s' % e)
            task.last_error = str(e)
            task.lock_id = ''

            retry_limit_reached = task.error_count >= task.max_attempts
            is_fatal = isinstance(e, FatalTaskException)

            if retry_limit_reached:
                task.retry_allowed = False
                self.log('Maximum attempts reached for this task.', logging.WARNING)
            elif is_fatal:
                task.retry_allowed = False
                self.log('Task had a fatal error. Will not be retried.', logging.ERROR)

            task.save()
            return e

    def process_all(self):
        while self.count_eligible:
            self.process_one()
