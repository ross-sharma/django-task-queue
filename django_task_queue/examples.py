import dataclasses
import random
import time

from django.utils import timezone

from django_task_queue import BaseQueue, TaskInfo, Retry


class DoNothingQueue[T: None](BaseQueue[T]):
    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        return None


class FailQueue[T: Exception](BaseQueue[T]):
    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        raise task_info.get_arg()


class MaxAttemptsQueue[T: int](BaseQueue[T]):
    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        current_attempt = task_info.attempt_count + 1
        if current_attempt >= task_info.get_arg():
            return None
        return Retry()


class StoppableTaskQueue[T: float](BaseQueue[T]):

    @classmethod
    def add_task(cls, num_seconds: T, **_kwargs) -> TaskInfo[T]:
        note = f"Sleep for {num_seconds:.1f} seconds"
        return super().add_task(arg=num_seconds, note=note)

    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        num_seconds = task_info.get_arg()
        start_time = time.time()
        while time.time() - start_time < num_seconds:
            time.sleep(0.5)
            if task_info.stop_requested():
                return Retry(count_attempt=False)
        return None


@dataclasses.dataclass
class BackoffArg:
    failure_chance: float
    max_attempts: int


class ExponentialBackoff[T: BackoffArg](BaseQueue[T]):

    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        arg = task_info.get_arg()
        time.sleep(1)

        if random.random() >= arg.failure_chance:
            print("Task succeeded")
            return None

        if task_info.attempt_count >= arg.max_attempts:
            raise Exception("Max attempts reached")

        delay = 2**task_info.attempt_count
        print(f"Task failed, retrying after {delay} seconds")
        retry_time = timezone.now() + timezone.timedelta(seconds=delay)
        return Retry(when=retry_time)


@dataclasses.dataclass
class CompleteExampleArg:
    retry_delay_seconds: float
    long_task_seconds: float
    max_attempts: int


class CompleteExampleQueue(BaseQueue[CompleteExampleArg]):
    class NetworkError(Exception):
        pass

    class TooManyRequests(Exception):
        pass

    class TaskStopped(Exception):
        pass

    @classmethod
    def process(cls, task_info: TaskInfo[CompleteExampleArg]) -> Retry | None:
        from django.utils import timezone

        arg = task_info.get_arg()
        print()
        print(f"Processing: {task_info.note}")
        print(f"Attempt {task_info.attempt_count} of {arg.max_attempts}")

        try:
            cls._long_running_task(arg, task_info)

        except (cls.NetworkError, cls.TooManyRequests) as e:
            retry_when = timezone.now() + timezone.timedelta(
                seconds=arg.retry_delay_seconds
            )
            print(
                f"Got {e.__class__.__name__}, retrying after {arg.retry_delay_seconds:.1f} seconds\n"
            )
            return Retry(count_attempt=False, when=retry_when)

        except cls.TaskStopped:
            print(f"Task stopped by worker.\n")
            return Retry(count_attempt=False)

        except Exception:
            backoff_delay = 2**task_info.attempt_count
            if task_info.attempt_count >= arg.max_attempts:
                raise
            print(
                f"Unknown error. Attempt count={task_info.attempt_count}. Retrying after {backoff_delay} seconds\n"
            )
            retry_when = timezone.now() + timezone.timedelta(seconds=backoff_delay)
            return Retry(count_attempt=True, when=retry_when)

        # Call succeeded, so return None to remove the task.
        print("Task succeeded.\n")
        return None

    @classmethod
    def _long_running_task(
        cls, arg: CompleteExampleArg, task_info: TaskInfo[CompleteExampleArg]
    ):
        import time
        import random

        start_time = time.time()
        time.sleep(1)

        match random.randint(1, 4):
            case 1:
                raise cls.NetworkError()
            case 2:
                raise cls.TooManyRequests()
            case 3:
                raise Exception()
            case _:
                print(f"Processing for {arg.long_task_seconds:.1f} seconds...")
                while time.time() - start_time < arg.long_task_seconds:
                    time.sleep(1)  # Poll the stop flag once per second
                    if task_info.stop_requested():
                        raise cls.TaskStopped()
        return None
