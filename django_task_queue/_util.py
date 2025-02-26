import pydoc
import signal
import time
import typing
from contextlib import contextmanager
from typing import Optional

from django.db import transaction
from django.db.transaction import get_connection


def get_class_path(klass: type) -> str:
    return klass.__module__ + "." + klass.__qualname__


def import_class_path(class_path, check_subclass_of: Optional[type] = None):
    klass: type = pydoc.locate(class_path)  # noqa
    if klass is None:
        raise ImportError(f"Failed to import '{class_path}'")
    if check_subclass_of and not issubclass(klass, check_subclass_of):
        raise TypeError(f"{class_path} is not a subclass of {check_subclass_of}")
    return klass


def _get_stop_signals() -> list[signal.Signals]:
    _candidate_stop_signals = [
        "SIGBREAK",
        "SIGINT",
        "SIGTERM",
        "SIGKILL",
        "SIGHUP",
    ]

    output = []
    for sig in signal.valid_signals():
        if sig.name in _candidate_stop_signals:
            output.append(sig)
    return output


class WorkerType(typing.Protocol):
    stop: typing.Callable[[], None]
    start: typing.Callable[[], None]
    is_alive: typing.Callable[[], bool]


def run_worker_until_stopped(t: WorkerType, sleep_seconds: float = 1):
    for sig in _get_stop_signals():
        signal.signal(sig, lambda signum, frame: t.stop())

    t.start()

    while t.is_alive():
        try:
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            t.stop()


@contextmanager
def lock_table(model):
    with transaction.atomic():
        cursor = get_connection().cursor()
        cursor.execute(f"LOCK TABLE {model._meta.db_table}") # noqa
        try:
            yield
        finally:
            cursor.close()
