from django.contrib import admin as _admin

from django_task_queue.models import Task as _Task, FailedTask as _FailedTask


@_admin.register(_Task)
class TaskAdmin(_admin.ModelAdmin):
    list_display = (
        "id",
        _Task.note.field.name,  # type: ignore
        _Task.priority.field.name,  # type: ignore
        _Task.created_datetime.field.name,  # type: ignore
        _Task.last_attempt_datetime.field.name,  # type: ignore
        _Task.next_attempt_datetime.field.name,  # type: ignore
        _Task.attempt_count.field.name,  # type: ignore
        _Task.lock_id.field.name,  # type: ignore
        _Task.queue_class_path.field.name,  # type: ignore
    )

    list_filter = (
        _Task.queue_class_path.field.name, # type: ignore
        _Task.is_processing.field.name, # type: ignore
    )

    search_fields = (
        _Task.note.field.name,  # type: ignore
        _Task.queue_class_path.field.name,  # type: ignore
    )


@_admin.register(_FailedTask)
class FailedTaskAdmin(_admin.ModelAdmin):
    list_display = (
        "id",
        _FailedTask.note.field.name,
        _FailedTask.created_datetime.field.name,
        _FailedTask.queue_class_path.field.name,
        _FailedTask.last_attempt_datetime.field.name,
        _FailedTask.attempt_count.field.name,
        _FailedTask.priority.field.name,
    )

    list_filter = (
        _FailedTask.queue_class_path.field.name,
        _FailedTask.exc_class.field.name,
    )

    search_fields = (
        _FailedTask.note.field.name,
        _FailedTask.error_description.field.name,
        _FailedTask.queue_class_path.field.name,
        _FailedTask.exc_class.field.name,
        _FailedTask.traceback_str.field.name,
    )
