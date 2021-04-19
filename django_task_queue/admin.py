from django.contrib import admin
from django_task_queue.models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'created_datetime',
        'queue_class_name',
        'last_attempt_datetime',
        'last_error',
        'error_count',
        'retry_allowed',
        'priority',
    )

    list_filter = ('queue_class_name',)

