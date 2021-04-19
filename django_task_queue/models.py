import json

from django.db import models


class Task(models.Model):

    created_datetime = models.DateTimeField(db_index=True, auto_now_add=True)
    last_attempt_datetime = models.DateTimeField(db_index=True, null=True)
    lock_id = models.CharField(blank=True, max_length=64)
    queue_class_name = models.CharField(db_index=True, max_length=256)
    data_json = models.TextField(default='null')
    last_error = models.TextField(blank=True)
    tag = models.CharField(db_index=True, max_length=128)
    error_count = models.IntegerField(default=0)
    retry_allowed = models.BooleanField(default=True, db_index=True)
    max_attempts = models.IntegerField()
    priority = models.IntegerField()

    def __str__(self):
        return '%s (%s)' % (self.queue_class_name, self.data_json[:50])

    def __repr__(self):
        return '%s (%s)' % (self.queue_class_name, self.data)

    @property
    def data(self):
        return json.loads(self.data_json)

    @data.setter
    def data(self, data):
        self.data_json = json.dumps(data, default=str)
