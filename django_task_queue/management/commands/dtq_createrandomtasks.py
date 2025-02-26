import random
from argparse import ArgumentParser

from django.core.management.base import BaseCommand
from django.db import transaction

import django_task_queue as dtq


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser):
        parser.add_argument("--num_tasks", "-n", type=int, default=10)

    @transaction.atomic
    def handle(self, num_tasks: int, **options):
        self.__is_verbose = options.get("verbosity", 1) > 1  # noqa
        sep = "\t"

        self._verbose(f"Creating {num_tasks} tasks...")
        self._verbose(
            "Id",
            "Queue".ljust(20),
            "Note",
            sep=sep,
        )
        self._verbose("=" * 50)

        for _ in range(num_tasks):
            t = create_random_task()
            self._verbose(
                t.task_id,
                t.queue_class_path.split(".")[-1].ljust(20),
                t.note,
                sep=sep,
            )
        print(f"Created {num_tasks} tasks")

    def _verbose(self, *args, **kwargs):
        if self.__is_verbose:
            print(*args, **kwargs)


def create_random_task() -> dtq.TaskInfo:
    classes = [
        dtq.examples.DoNothingQueue,
        dtq.examples.FailQueue,
        dtq.examples.MaxAttemptsQueue,
        dtq.examples.StoppableTaskQueue,
        dtq.examples.ExponentialBackoff,
        dtq.examples.CompleteExampleArg,
    ]

    klass = random.choice(classes)

    match klass:
        case dtq.examples.DoNothingQueue:
            t = dtq.examples.DoNothingQueue.add_task(None, "Do nothing")
        case dtq.examples.FailQueue:
            t = dtq.examples.FailQueue.add_task(
                Exception("random failure"),
                "Will fail",
            )
        case dtq.examples.MaxAttemptsQueue:
            attempts = random.randint(1, 10)
            t = dtq.examples.MaxAttemptsQueue.add_task(
                3,
                note=f"Max {attempts} attempts",
            )
        case dtq.examples.StoppableTaskQueue:
            task_time = 1 + 10 * random.random()
            t = dtq.examples.StoppableTaskQueue.add_task(task_time)
        case dtq.examples.ExponentialBackoff:
            arg = dtq.examples.BackoffArg(
                failure_chance=random.random(),
                max_attempts=random.randint(5, 5),
            )
            t = dtq.examples.ExponentialBackoff.add_task(
                arg,
                note=f"fail chance {arg.failure_chance:.1f}, {arg.max_attempts} attempts",
            )

        case dtq.examples.CompleteExampleArg:
            delay = random.random() * 10
            task = random.randint(2, 5)
            attempts = random.randint(1, 5)

            arg = dtq.examples.CompleteExampleArg(
                retry_delay_seconds=delay,
                long_task_seconds=task,
                max_attempts=attempts,
            )

            t = dtq.examples.CompleteExampleQueue.add_task(
                arg, note=f"{delay=:.1f}s,{task=:.1f}s,{attempts=}"
            )

        case _:
            raise ValueError(f"Unknown class: {klass}")

    return t
