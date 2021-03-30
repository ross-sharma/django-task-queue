from django.apps import AppConfig


class DjangoTaskQueueConfig(AppConfig):
    name = 'django_task_queue'

    def ready(self):
        from django.conf import settings
        from . import app_settings
        project_settings = settings.get_setting('DJANGO_TASK_QUEUE', {})
        for key, val in project_settings.items():
            setattr(app_settings, key, val)
