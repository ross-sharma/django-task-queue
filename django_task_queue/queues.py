import logging

from .app_settings import get_setting, Keys
from .models import Task

log = logging.getLogger(__name__)


class BaseQueue:
    tag = '__default__'
    task_priority = None
    max_attempts = None

    @classmethod
    def append(cls, **kwargs):
        task = Task()
        task.data = kwargs
        task.queue_class_name = cls.__queue_class_name()
        task.tag = cls.tag

        task.max_attempts = cls.max_attempts if cls.max_attempts is not None \
            else get_setting(Keys.DEFAULT_TASK_PRIORITY)
        task.priority = cls.task_priority if cls.task_priority is not None \
            else get_setting(Keys.DEFAULT_MAX_ATTEMPTS)

        task.save()
        cls._log('Task queued: %s' % task.data)
        return task

    @classmethod
    def process(cls, **kwargs):
        raise NotImplementedError

    @classmethod
    def count(cls):
        return Task.objects.filter(queue_class_name=cls.__queue_class_name()).count()

    @classmethod
    def __queue_class_name(cls):
        return '.'.join([cls.__module__, cls.__name__])

    @classmethod
    def _log(cls, msg, level=logging.INFO):
        msg = f'({cls.__name__}) {msg}'
        log.log(level=level, msg=msg)
