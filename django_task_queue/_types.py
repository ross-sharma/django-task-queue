import datetime
import pickle
from dataclasses import dataclass

from ._exc import DeserializationExc


@dataclass(frozen=True)
class TaskInfo[T]:
    task_id: int
    note: str
    priority: int
    next_attempt_datetime: datetime.datetime
    attempt_count: int
    queue_class_path: str
    dupe_key: str | None
    arg_data: bytes

    @classmethod
    def create_from_task(cls, task) -> "TaskInfo[T]":
        from .models import Task

        task: Task
        return TaskInfo(
            task_id=task.pk,
            note=task.note,
            priority=task.priority,
            next_attempt_datetime=task.next_attempt_datetime,
            attempt_count=task.attempt_count,
            queue_class_path=task.queue_class_path,
            dupe_key=task.dupe_key,
            arg_data=task.arg_data,
        )

    def task_exists(self) -> bool:
        from .models import Task

        return Task.objects.filter(pk=self.task_id).exists()

    def refresh(self) -> "TaskInfo[T]":
        from .models import Task

        try:
            task: Task = self._get_task()
        except Task.DoesNotExist:
            return self
        return TaskInfo.create_from_task(task)

    def stop_requested(self) -> bool:
        from .models import Task

        try:
            task: Task = self._get_task()
            return task.stop_requested
        except Task.DoesNotExist:
            return False

    def request_stop(self):
        from .models import Task

        Task.objects.filter(pk=self.task_id).update(stop_requested=True)

    def _get_task(self):
        from .models import Task

        return Task.objects.get(pk=self.task_id)

    def get_arg(self) -> T:
        from .models import Task

        t: Task = self._get_task()

        try:
            return pickle.loads(t.arg_data)
        except Exception as e:
            raise DeserializationExc(
                f"{e.__class__.__name__} raised while trying to un-pickle data",
                t.arg_data,
            ) from e


@dataclass(frozen=True)
class Retry:
    when: datetime.datetime | None = None
    count_attempt: bool = True
