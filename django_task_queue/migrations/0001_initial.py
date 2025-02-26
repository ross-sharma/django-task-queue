# Generated by Django 5.1.6 on 2025-02-25 01:27

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="FailedTask",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("task_id", models.IntegerField(db_index=True)),
                ("created_datetime", models.DateTimeField(db_index=True)),
                ("note", models.CharField(blank=True, db_index=True, max_length=255)),
                (
                    "last_attempt_datetime",
                    models.DateTimeField(db_index=True, null=True),
                ),
                ("queue_class_path", models.CharField(db_index=True, max_length=255)),
                ("attempt_count", models.IntegerField(db_index=True)),
                ("priority", models.IntegerField()),
                ("error_description", models.CharField(db_index=True, max_length=255)),
                (
                    "traceback_str",
                    models.TextField(blank=True, db_index=True, default=""),
                ),
                (
                    "exc_class",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=255
                    ),
                ),
                ("arg_data", models.BinaryField()),
                (
                    "dupe_key",
                    models.CharField(
                        blank=True, db_index=True, max_length=255, null=True
                    ),
                ),
            ],
            options={
                "get_latest_by": "pk",
            },
        ),
        migrations.CreateModel(
            name="Task",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_datetime",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "note",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=255
                    ),
                ),
                (
                    "last_attempt_datetime",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("next_attempt_datetime", models.DateTimeField(db_index=True)),
                (
                    "lock_id",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=63
                    ),
                ),
                ("is_processing", models.BooleanField(db_index=True, default=False)),
                ("queue_class_path", models.CharField(db_index=True, max_length=255)),
                ("attempt_count", models.IntegerField(default=0)),
                ("priority", models.IntegerField(db_index=True)),
                ("arg_data", models.BinaryField()),
                ("stop_requested", models.BooleanField(default=False)),
                (
                    "dupe_key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default=None,
                        max_length=255,
                        null=True,
                    ),
                ),
            ],
            options={
                "unique_together": {("queue_class_path", "dupe_key")},
            },
        ),
    ]
