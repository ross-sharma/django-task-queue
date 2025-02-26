from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()  # noqa
        username = "admin"
        password = username

        User.objects.filter(username=username).delete()
        User.objects.create_user(
            username,
            password=password,
            is_superuser=True,
            is_staff=True,
        )
        print(f"Superuser created. {username=} {password=}")
