import traceback

from django.db import models
from django.db.models import Manager
from django.utils import timezone

_note_max_length = 255


class Task(models.Model):
    objects: Manager
    DoesNotExist: type[Exception]

    class Meta:
        unique_together = ("queue_class_path", "dupe_key")

    created_datetime: timezone.datetime = models.DateTimeField(
        db_index=True,
        auto_now_add=True,
    )
    note = models.CharField(
        max_length=_note_max_length,
        blank=True,
        default="",
        db_index=True,
    )
    last_attempt_datetime = models.DateTimeField(
        db_index=True,
        null=True,
        blank=True,
    )
    next_attempt_datetime = models.DateTimeField(db_index=True)
    lock_id = models.CharField(
        blank=True,
        max_length=63,
        db_index=True,
        default="",
    )
    is_processing = models.BooleanField(default=False, db_index=True)
    queue_class_path = models.CharField(db_index=True, max_length=255)
    attempt_count = models.IntegerField(default=0)
    priority = models.IntegerField(db_index=True)
    arg_data = models.BinaryField()
    stop_requested = models.BooleanField(default=False)
    dupe_key = models.CharField(
        max_length=255,
        blank=True,
        default=None,
        null=True,
        db_index=True,
    )

    def __str__(self) -> str:
        klass = self.queue_class_path.split(".")[-1]
        return f"Task({klass})"

    @classmethod
    def dupe_key_exists(cls, queue_class_path, dupe_key) -> bool:
        return Task.objects.filter(
            queue_class_path=queue_class_path, dupe_key=dupe_key
        ).exists()

    @classmethod
    def queue_count(cls, queue_class_path: str) -> int:
        return Task.objects.filter(queue_class_path=queue_class_path).count()


class FailedTask(models.Model):
    objects: Manager

    class Meta:
        get_latest_by = "pk"

    task_id = models.IntegerField(db_index=True)
    created_datetime = models.DateTimeField(db_index=True)
    note = models.CharField(max_length=_note_max_length, blank=True, db_index=True)
    last_attempt_datetime = models.DateTimeField(db_index=True, null=True)
    queue_class_path = models.CharField(db_index=True, max_length=255)
    attempt_count = models.IntegerField(db_index=True)
    priority = models.IntegerField()
    error_description = models.CharField(max_length=255, db_index=True)
    traceback_str = models.TextField(blank=True, default="", db_index=True)
    exc_class = models.CharField(max_length=255, blank=True, default="", db_index=True)
    arg_data = models.BinaryField()
    dupe_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
    )

    def set_exc(self, e: Exception):
        klass = e.__class__
        self.exc_class = klass.__module__ + "." + klass.__qualname__
        self.traceback_str = "\n".join(traceback.format_exception(e))
