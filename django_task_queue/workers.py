import inspect
import logging
import signal
import threading
import time
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import util
from .app_settings import get_setting, Keys
from .exceptions import NoEligibleTaskException, FatalTaskException, NoIncrementErrorCountException
from .models import Task
from .queues import BaseQueue

_logger = logging.getLogger(__name__)

_stop_signals = list(filter(lambda s: s, [getattr(signal, name, None) for name in (
    'CTRL_C_EVENT',
    'CTRL_BREAK_EVENT',
    'SIGINT',
    'SIGTERM',
    'SIGKILL',
)]))


class BaseWorker(threading.Thread):

    def __init__(self, tags=None, logger=_logger):
        self.tags = tags or ['__default__']
        self.lock_id = uuid4()
        self.min_seconds_between_processing_attempts = get_setting(Keys.DEFAULT_MIN_SECONDS_BETWEEN_ATTEMPTS)
        self._logger = logger
        self.stop_flag = threading.Event()
        self._log_prefix = f'({self.__class__.__name__}, {self.tags})'
        super().__init__()

    def run(self):
        self._log('Thread starting.')
        while not self.stop_flag.is_set():
            try:
                self.process_one()
            except NoEligibleTaskException:
                self._log('No eligible task found. Sleeping.', level=logging.DEBUG)
                time.sleep(1)
        else:
            self._log('Stop flag set. Thread terminating.')

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

        self._log('Processing task: %s' % task)

        try:
            queue = util.import_class(task.queue_class_name, check_subclass_of=BaseQueue)()
            result = queue.process(**task.data)
            self._log('Task processed. Result: %s' % result)
            task.delete()
            return result
        except Exception as e:
            is_no_increment = isinstance(e, NoIncrementErrorCountException)
            if not is_no_increment:
                self.__log_exception(e)
                task.error_count += 1
            else:
                self._log('No increment error: %s' % e)
            task.last_error = str(e)
            task.lock_id = ''

            retry_limit_reached = task.error_count >= task.max_attempts
            is_fatal = isinstance(e, FatalTaskException)

            if retry_limit_reached:
                task.retry_allowed = False
                self._log('Maximum attempts reached for this task.', logging.WARNING)
            elif is_fatal:
                task.retry_allowed = False
                self._log('Task had a fatal error. Will not be retried.', logging.ERROR)

            task.save()
            return e

    def process_all(self):
        while self.count_eligible:
            self.process_one()

    def _log(self, msg, level=logging.INFO):
        msg = f'{self._log_prefix} {msg}'
        self._logger.log(level=level, msg=msg)

    def __log_exception(self, exc):
        self._logger.exception(exc)

    def __filter(self, *args, **kwargs):
        return Task.objects.filter(tag__in=self.tags, *args, **kwargs)

    def __filter_eligible(self):
        last_attempt_limit = timezone.now() - timedelta(seconds=self.min_seconds_between_processing_attempts)

        tasks = self.__filter(lock_id='')
        return tasks.filter(retry_allowed=True).filter(
            Q(last_attempt_datetime__isnull=True) | Q(last_attempt_datetime__lte=last_attempt_limit)
        )


class AllWorkersThread(threading.Thread):

    def __init__(self, logger=_logger, handle_signals=True):
        super().__init__()
        self.__logger = logger

        if handle_signals:
            self.__attach_signal_handlers()

        self.__load_workers()

    def run(self):
        [w.start() for w in self.__workers]
        [w.join() for w in self.__workers]

    def handle_stop_signal(self, sig_num, frame):
        self.__log(f'{self}: Signal received: {sig_num} {frame}')
        [w.stop_flag.set() for w in self.__workers]

    def __load_workers(self):
        worker_class_names = get_setting(Keys.WORKERS)
        self.__log('In __init__(): Worker class names: %s' % worker_class_names)
        self.__workers = []
        for name in worker_class_names:
            klass = util.import_class(name, check_subclass_of=BaseWorker)
            kwargs = {}
            if 'logger' in inspect.signature(klass).parameters:
                kwargs['logger'] = self.__logger
            worker = klass(**kwargs)
            self.__workers.append(worker)

    def __attach_signal_handlers(self):
        success = False
        for sig_num in _stop_signals:
            try:
                signal.signal(sig_num, self.handle_stop_signal)
                self.__log('Attached to signal %s' % sig_num)
                success = True
            except Exception:
                pass
        if not success:
            raise OSError('Unable to attach to any of the following signals: %s' % _stop_signals)

    def __log(self, msg, level=logging.INFO):
        msg = f'{__name__}: {msg}'
        self.__logger.log(msg=msg, level=level)


def start_all_workers():
    thread = AllWorkersThread()
    thread.start()
    thread.join()
