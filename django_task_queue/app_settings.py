class Keys:
    WORKERS = 'WORKERS'
    DEFAULT_MAX_ATTEMPTS = 'DEFAULT_MAX_ATTEMPTS'
    DEFAULT_TASK_PRIORITY = 'DEFAULT_TASK_PRIORITY'
    DEFAULT_MIN_SECONDS_BETWEEN_ATTEMPTS = 'DEFAULT_MIN_SECONDS_BETWEEN_ATTEMPTS'


_defaults = {
    Keys.WORKERS: ['django_task_queue.workers.BaseWorker'],
    Keys.DEFAULT_MAX_ATTEMPTS: 5,
    Keys.DEFAULT_TASK_PRIORITY: 100,
    Keys.DEFAULT_MIN_SECONDS_BETWEEN_ATTEMPTS: 60,
}


def get_setting(key):
    from django.conf import settings as project_settings
    return getattr(project_settings, 'DJANGO_TASK_QUEUE', {}).get(key, _defaults[key])
