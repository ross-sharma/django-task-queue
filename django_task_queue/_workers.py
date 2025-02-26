import logging
import threading
import time

from django.db import connection
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from . import _util
from ._exc import DtqExc
from ._queues import BaseQueue
from ._types import Retry, TaskInfo

_logger = logging.getLogger("django_task_queue")


class Worker(threading.Thread):
    class ErrorDescriptions:
        QUEUE_TYPE_ERROR = f"Queue class is not a subclass of {BaseQueue.__name__}"
        QUEUE_IMPORT_ERROR = "Unable to import queue class"
        UNHANDLED_EXCEPTION = "Unhandled exception while processing task"

    def __init__(
        self,
        queue_classes: list[type[BaseQueue]] | None = None,
        sleep_seconds_when_empty: float | None = None,
        thread_name=None,
    ):
        self.queue_classes = queue_classes or []
        self.__sleep_seconds_when_empty = (
            sleep_seconds_when_empty if sleep_seconds_when_empty is not None else 1
        )

        self.__stop_flag = threading.Event()
        self._lock_id = threading.current_thread().name
        self.__logger = _logger
        self.__queue_class_paths = [_util.get_class_path(q) for q in self.queue_classes]
        self.__current_task_info: TaskInfo | None = None
        name = thread_name or f"{self.__class__.__name__}-thread"
        super().__init__(name=name)

    def start(self):
        self.__stop_flag.clear()
        super().start()

    def run(self):
        self.__log("Worker started.")
        self._lock_id = threading.current_thread().name

        while not self.__stop_flag.is_set():
            try:
                self.process_one()
            except KeyboardInterrupt:
                self.stop()
            except _NoEligibleTaskExc:
                msg = f"No eligible task found. Sleeping for {self.__sleep_seconds_when_empty} seconds."
                self.__log(msg, level=logging.DEBUG)
                self.__interruptible_sleep(self.__sleep_seconds_when_empty)
            except Exception as e:
                self.__log_exception(e)

        self.__log("Stop flag set. Thread terminating.")
        if threading.current_thread() != threading.main_thread():
            self.__log("Closing db connection", level=logging.DEBUG)
            connection.close()

    def __interruptible_sleep(self, seconds: float):
        start_time = time.time()
        step_length = 1
        while not self.__stop_flag.is_set() and time.time() - start_time < seconds:
            try:
                time.sleep(step_length)
            except KeyboardInterrupt:
                self.stop()

    def request_stop(self):
        self.__stop_flag.set()
        if self.__current_task_info:
            self.__current_task_info.request_stop()

    def stop(self, timeout=None):
        self.request_stop()
        self.join(timeout=timeout)

    def count(self):
        return self.__filter().count()

    def count_eligible_tasks(self):
        return self.__filter_eligible().count()

    def process_one(self):
        from django_task_queue.models import Task

        task: Task = self.__acquire_task()
        self.__log(f"Processing task: {task.queue_class_path=}, {task.note=}")

        try:
            queue_class = _util.import_class_path(
                task.queue_class_path,
                check_subclass_of=BaseQueue,
            )
        except TypeError as e:
            self.__logger.exception(e)
            self.__fail_task(task, e, self.ErrorDescriptions.QUEUE_TYPE_ERROR)
            return
        except Exception as e:
            self.__logger.exception(e)
            self.__fail_task(task, e, self.ErrorDescriptions.QUEUE_IMPORT_ERROR)
            return

        task.last_attempt_datetime = timezone.now()
        task.save()
        self.__current_task_info = TaskInfo.create_from_task(task)

        try:
            result = queue_class.process(self.__current_task_info)
        except Exception as e:
            self.__logger.exception(e)
            self.__fail_task(task, e, self.ErrorDescriptions.UNHANDLED_EXCEPTION)
            return

        if isinstance(result, Retry):
            task.lock_id = ""
            task.is_processing = False
            task.next_attempt_datetime = result.when or timezone.now()
            task.attempt_count += 1 if result.count_attempt else 0
            task.stop_requested = False
            task.save()
        else:
            task.delete()

    def process_all(self):
        while self.count_eligible_tasks():
            self.process_one()

    @transaction.atomic
    def __acquire_task(self):
        from .models import Task

        query = (
            self.__filter_eligible()
            .order_by(
                "-" + Task.priority.field.name,  # # type: ignore
                F(Task.last_attempt_datetime.field.name).asc(nulls_first=True),  # type: ignore
                Task.created_datetime.field.name,  # type: ignore
                Task.attempt_count.field.name,  # type: ignore
            )
            .select_for_update()
        )

        task: Task | None = query.first()
        if not task:
            raise _NoEligibleTaskExc()

        if task.lock_id:
            msg = f"Tried to lock a task that is already locked"
            self.__log(msg, level=logging.CRITICAL)
            raise Exception(msg)

        task.lock_id = self._lock_id
        task.is_processing = True
        task.save()

        self.__log(f"Added lock id {self._lock_id} to {task}.", level=logging.DEBUG)
        return task

    def __fail_task(self, task, exc: Exception, error_description: str):
        from .models import FailedTask, Task

        task: Task

        failed_task = FailedTask(
            task_id=task.pk,
            created_datetime=task.created_datetime,
            note=task.note,
            last_attempt_datetime=task.last_attempt_datetime,
            queue_class_path=task.queue_class_path,
            attempt_count=task.attempt_count,
            priority=task.priority,
            arg_data=task.arg_data,
            error_description=error_description,
            dupe_key=task.dupe_key,
        )
        failed_task.set_exc(exc)

        with transaction.atomic():
            task.delete()
            failed_task.save()

        self.__current_task_info = None

    def __log(self, msg, level=logging.INFO):
        self.__logger.log(level=level, msg=msg)

    def __log_exception(self, exc):
        self.__logger.exception(exc)

    def __filter(self, *args, **kwargs):
        from .models import Task

        _filter = Task.objects.filter()
        if self.__queue_class_paths:
            _filter = _filter.filter(queue_class_path__in=self.__queue_class_paths)
        return _filter.filter(*args, **kwargs)

    def __filter_eligible(self):
        return self.__filter(
            lock_id="",
            next_attempt_datetime__lte=timezone.now(),
        )


class WorkerGroup(threading.Thread):

    def __init__(self, workers: list[Worker]):
        super().__init__(name=f"{self.__class__.__name__}-thread")
        self.stop_flag = threading.Event()
        self.workers = workers
        self.__logger = _logger

    def stop(self, timeout_per_worker=None):
        for w in self.workers:
            self.__log(f"Stopping {w}...")
            w.request_stop()

        for w in self.workers:
            w.join(timeout=timeout_per_worker)
            self.__log(f"{w} stopped.")

    def start(self):
        for w in self.workers:
            w.start()
        super().start()

    def run(self):
        for w in self.workers:
            if not w.is_alive():
                w.start()

        for w in self.workers:
            w.join()

    def __log(self, msg, level=logging.INFO):
        self.__logger.log(msg=msg, level=level)

    @classmethod
    def from_settings(cls, dtq_settings: dict) -> "WorkerGroup":
        worker_confs = dtq_settings.get("workers", [])
        workers: list[Worker] = []

        for conf in worker_confs:
            conf: dict
            paths = conf.get("queue_classes", [])
            num_threads = conf.get("num_threads", 1)
            name = conf.get("name", "dtq-worker")
            sleep_seconds = conf.get("sleep_seconds_when_empty", None)

            queue_classes = [
                _util.import_class_path(p, check_subclass_of=BaseQueue) for p in paths
            ]

            for i in range(num_threads):
                thread_name = f"{name}-{i + 1}"
                worker = Worker(
                    queue_classes=queue_classes,
                    sleep_seconds_when_empty=sleep_seconds,
                    thread_name=thread_name,
                )
                workers.append(worker)

        return WorkerGroup(workers)


class _NoEligibleTaskExc(DtqExc):
    pass
