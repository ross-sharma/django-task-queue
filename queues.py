import logging
from .models import Task, DEFAULT_MAX_ATTEMPTS, DEFAULT_TASK_PRIORITY
from .workers import BaseWorker

log = logging.getLogger(__name__)


class BaseQueue:

    tag = '__default__'
    max_attempts = DEFAULT_MAX_ATTEMPTS
    task_priority = DEFAULT_TASK_PRIORITY

    @classmethod
    def get_worker(cls):
        return BaseWorker(tags=[cls.tag])

    @classmethod
    def append(cls, **kwargs):
        task = Task()
        task.data = kwargs
        task.queue_class_name = cls.queue_class_name()
        task.tag = cls.tag
        task.max_attempts = cls.max_attempts
        task.priority = cls.task_priority
        task.save()
        cls._log('Task queued: %s' % task.data)
        return task

    @classmethod
    def process(cls, **kwargs):
        raise NotImplementedError

    @classmethod
    def count(cls):
        return Task.objects.filter(queue_class_name=cls.queue_class_name()).count()

    @classmethod
    def queue_class_name(cls):
        return '.'.join([cls.__module__, cls.__name__])

    @classmethod
    def _log(cls, msg, level=logging.INFO):
        msg = f'({cls.__name__}) {msg}'
        log.log(level=level, msg=msg)
