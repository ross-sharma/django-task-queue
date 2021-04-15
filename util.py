from django.utils.module_loading import import_string

from django_task_queue.exceptions import FatalTaskException


def import_class(class_name, check_subclass_of=None):
    klass = import_string(class_name)
    if check_subclass_of and not issubclass(klass, check_subclass_of):
        raise FatalTaskException(f'{class_name} is not a subclass of {check_subclass_of}')
    return klass
