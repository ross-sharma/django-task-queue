from django.utils.module_loading import import_string


def import_class(class_name):
    return import_string(class_name)
