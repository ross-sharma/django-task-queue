import datetime
import pickle

from django.db import transaction
from django.utils import timezone

from . import _util
from ._exc import QueueImportExc, DupeKeyExc, SerializationExc
from ._types import TaskInfo, Retry


class BaseQueue[T]:
    def __init__(self):
        raise TypeError("BaseQueue should not be instantiated")

    @classmethod
    def add_task(
        cls,
        arg: T,
        note: str | None = None,
        priority: int | None = None,
        first_attempt_datetime: datetime.datetime | None = None,
        dupe_key: str | None = None,
    ) -> TaskInfo[T]:
        if cls == BaseQueue:
            raise TypeError("BaseQueue must be subclassed to be used")

        from .models import Task

        class_path = cls.__class_path()
        cls.__validate_importable_path(class_path)

        task = Task()
        task.queue_class_path = class_path
        task.note = note or ""
        task.priority = priority or 0
        task.next_attempt_datetime = first_attempt_datetime or timezone.now()

        try:
            task.arg_data = pickle.dumps(arg)
        except Exception as e:
            raise SerializationExc[T]("Unable to serialize arg object", arg) from e

        if dupe_key is not None:
            with transaction.atomic():
                task.dupe_key = dupe_key
                with _util.lock_table(Task):
                    if Task.dupe_key_exists(
                        queue_class_path=class_path, dupe_key=dupe_key
                    ):
                        raise DupeKeyExc(dupe_key)
                    task.save()
        else:
            task.save()

        return TaskInfo.create_from_task(task)

    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        raise NotImplementedError

    @classmethod
    def count(cls) -> int:
        from .models import Task

        return Task.queue_count(queue_class_path=cls.__class_path())

    @classmethod
    def __class_path(cls) -> str:
        return _util.get_class_path(cls)

    @classmethod
    def __validate_importable_path(cls, path: str) -> None:
        if path.startswith("__main__"):
            raise QueueImportExc(
                f"{cls.__name__} cannot be imported from '__main__'."
                "You must define your queue in a separate file so that "
                "it can be imported during queue processing.",
                cls,
            )
        try:
            _util.import_class_path(path, check_subclass_of=BaseQueue)
        except Exception as e:
            raise QueueImportExc(f"Class path '{path}' cannot be imported", cls) from e
