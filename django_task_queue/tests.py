import datetime
import os
import pydoc
import threading
import warnings
from dataclasses import dataclass
from pickle import UnpicklingError

from django.test import TestCase
from django.utils import timezone

import django_task_queue as dtq
from django_task_queue.examples import DoNothingQueue, FailQueue, MaxAttemptsQueue
from django_task_queue.models import FailedTask, Task


class DtqTestCase(TestCase):

    def setUp(self):
        self.worker = dtq.Worker()

    def tearDown(self):
        if self.worker.is_alive():
            try:
                self.worker.stop(timeout=5)
            except Exception as e:
                warnings.warn(str(e))

    def assert_failed_task_matches_task_info(
        self,
        failed_task: FailedTask,
        task_info: dtq.TaskInfo,
    ):
        self.assertEqual(failed_task.task_id, task_info.task_id)
        self.assertEqual(failed_task.note, task_info.note)
        self.assertEqual(failed_task.priority, task_info.priority)
        self.assertEqual(failed_task.attempt_count, task_info.attempt_count)
        self.assertEqual(failed_task.dupe_key, task_info.dupe_key)
        self.assert_bytes_equal(failed_task.arg_data, task_info.arg_data)

    def assert_bytes_equal(self, v1, v2):
        # Postgresql returns memoryview objects when reading BinaryFields
        if type(v1) == memoryview:
            v1 = v1.tobytes()
        if type(v2) == memoryview:
            v2 = v2.tobytes()
        self.assertEqual(v1, v2)

    def assert_failed_task_count_equals(self, expected_count: int):
        actual_count = FailedTask.objects.count()
        if actual_count == expected_count:
            return
        msg = f"Expected {expected_count} FailedTask objects, but found {actual_count}"
        raise AssertionError(msg)


class BaseQueueAbstractTest(DtqTestCase):

    def test__basequeue_cannot_be_instantiated(self):
        with self.assertRaises(Exception):
            dtq.BaseQueue()

    def test__cannot_call_add_task_on_base_queue(self):
        with self.assertRaises(Exception):
            dtq.BaseQueue.add_task(None)


class TaskCreationTests(DtqTestCase):
    @dataclass
    class Arg:
        @dataclass
        class NestedArg:
            value: int

        float_: float
        int_: int
        str_: str
        date_: datetime.date
        datetime_: datetime.datetime
        nested_type_: NestedArg

    class Queue[T:"TaskCreationTests.Arg"](dtq.BaseQueue[T]):
        @classmethod
        def process(cls, task_info):
            return None

    def setUp(self):
        super().setUp()
        self.note = "test description"
        self.priority = 999
        self.first_attempt_datetime = timezone.make_aware(
            timezone.datetime(year=2000, month=1, day=1)
        )
        self.obj = self.Arg(
            float_=1.1,
            int_=1,
            str_="test",
            date_=datetime.date(2000, 1, 2),
            datetime_=datetime.datetime(2000, 1, 2),
            nested_type_=self.Arg.NestedArg(value=1),
        )

        self.task_info = self.Queue.add_task(
            self.obj,
            note=self.note,
            priority=self.priority,
            first_attempt_datetime=self.first_attempt_datetime,
        )

    def test__queue_count(self):
        self.assertEqual(self.Queue.count(), 1)

    def test__saved_object_type(self):
        self.assertIsInstance(self.task_info.get_arg(), self.Arg)
        self.assertIsInstance(
            self.task_info.get_arg().nested_type_,
            self.Arg.NestedArg,
        )

    def test__saved_object_equality(self):
        self.assertEqual(self.task_info.get_arg(), self.obj)
        self.assertEqual(self.task_info.get_arg().nested_type_, self.obj.nested_type_)

    def test__task_info_attributes(self):
        self.assertEqual(self.task_info.attempt_count, 0)
        self.assertEqual(self.task_info.priority, self.priority)
        self.assertEqual(self.task_info.note, self.note)
        self.assertEqual(
            self.task_info.next_attempt_datetime,
            self.first_attempt_datetime,
        )

    def test__task_exists(self):
        self.assertTrue(self.task_info.task_exists())


class TaskCreationArgsOmittedTests(DtqTestCase):

    def setUp(self):
        super().setUp()
        self.task_info = DoNothingQueue.add_task(None)

    def test__task_info_attributes(self):
        self.assertEqual(self.task_info.attempt_count, 0)
        self.assertEqual(self.task_info.priority, 0)
        self.assertEqual(self.task_info.note, "")
        self.assertEqual(self.task_info.dupe_key, None)
        self.assertLessEqual(self.task_info.next_attempt_datetime, timezone.now())

    def test__task_exists(self):
        self.assertTrue(self.task_info.task_exists())


class QueueClassPathCannotBeImported(DtqTestCase):
    def test__append_fails(self):
        self.queue_class: type[dtq.BaseQueue] = type("MyQueue", (dtq.BaseQueue,), {})  # type: ignore
        with self.assertRaises(dtq.QueueImportExc):
            self.queue_class.add_task(None)


class SerializationErrorTests(DtqTestCase):
    def test__data_not_pickleable__raises_error(self):
        obj = threading.Thread()  # Not pickleable
        try:
            DoNothingQueue.add_task(obj)
        except dtq.SerializationExc as e:
            self.assertEqual(e.obj, obj)
            self.assertEqual(DoNothingQueue.count(), 0)
            self.assert_failed_task_count_equals(0)
        else:
            self.fail(f"{dtq.SerializationExc.__name__} not raised")


class TaskFinishTests(DtqTestCase):

    class WriteToEnvQueue(dtq.BaseQueue):
        @classmethod
        def process(cls, task_info: dtq.TaskInfo):
            key, value = task_info.get_arg()
            os.environ[key] = value

    def setUp(self):
        super().setUp()
        self.key = "ENV_TEST_KEY"
        self.value = "ENV_TEST_VALUE"
        os.environ[self.key] = ""
        self.task_info = self.WriteToEnvQueue.add_task(
            (self.key, self.value),
        )
        self.worker.process_one()

    def test__task_was_processed(self):
        self.assertEqual(os.environ[self.key], self.value)

    def test__task_removed(self):
        self.assertFalse(self.task_info.task_exists())

    def test__worker_count_updated(self):
        self.assertEqual(
            0,
            self.worker.count(),
            self.worker.count_eligible_tasks(),
        )

    def test__queue_count_updated(self):
        self.assertEqual(0, self.WriteToEnvQueue.count())

    def test__failed_task_not_created(self):
        self.assert_failed_task_count_equals(0)


class DupeKeyTests(DtqTestCase):

    def test__key_exists_in_same_queue__raises_exc(self):
        key = "some string"
        t = DoNothingQueue.add_task(None, dupe_key=key)
        self.assertTrue(t.task_exists())
        self.assertEqual(1, DoNothingQueue.count())

        # Try adding another task with same dupe key. It should fail.
        with self.assertRaises(dtq.DupeKeyExc):
            DoNothingQueue.add_task(None, dupe_key=key)
        self.assertEqual(1, DoNothingQueue.count())

        # Process the first task
        self.worker.process_one()
        self.assertFalse(t.task_exists())
        self.assertEqual(0, DoNothingQueue.count())

        # Task with same dupe key can now be added
        DoNothingQueue.add_task(None, dupe_key=key)
        self.assertEqual(1, DoNothingQueue.count())

    def test__key_exists_in_another_queue__no_exc(self):
        key = "some string"
        DoNothingQueue.add_task(None, dupe_key=key)
        MaxAttemptsQueue.add_task(1, dupe_key=key)
        self.assertEqual(1, DoNothingQueue.count())
        self.assertEqual(1, MaxAttemptsQueue.count())


class TaskRetryDelayTests(DtqTestCase):

    class DelayQueue[T: timezone.datetime](dtq.BaseQueue[T]):
        @classmethod
        def process(cls, task_info: dtq.TaskInfo[T]) -> dtq.Retry:
            return dtq.Retry(when=task_info.get_arg())

    def setUp(self):
        super().setUp()
        self.task_info = self.DelayQueue.add_task(
            timezone.now() + timezone.timedelta(hours=1),
        )
        self.worker.process_one()

    def test__tasks_exists(self):
        self.assertTrue(self.task_info.task_exists())

    def test__task_not_eligible(self):
        self.assertEqual(self.worker.count_eligible_tasks(), 0)

    def test__queue_count(self):
        self.assertEqual(self.DelayQueue.count(), 1)

    def test__no_failed_task(self):
        self.assert_failed_task_count_equals(0)


class TaskRetryArgsOmittedTests(DtqTestCase):
    class Queue[T: None](dtq.BaseQueue[T]):

        @classmethod
        def process(cls, task_info: dtq.TaskInfo[T]) -> dtq.Retry:
            return dtq.Retry()

    def setUp(self):
        super().setUp()
        task_info = self.Queue.add_task(None)
        self.worker.process_one()
        self.new_task_info = task_info.refresh()

    def test__task_eligible_immediately(self):
        self.assertEqual(self.Queue.count(), 1)
        self.assertEqual(self.worker.count_eligible_tasks(), 1)

    def test__attempt_count_incremented(self):
        self.assertEqual(self.new_task_info.attempt_count, 1)

    def test__no_failed_task(self):
        self.assert_failed_task_count_equals(0)


class RetryAttemptCountTests(DtqTestCase):

    class Queue[T: bool](dtq.BaseQueue[T]):
        @classmethod
        def process(cls, task_info: dtq.TaskInfo[T]) -> dtq.Retry:
            return dtq.Retry(count_attempt=task_info.get_arg())

    def test__count_attempt_is_true(self):
        task_info = self.Queue.add_task(True)
        self.worker.process_one()
        new_task_info = task_info.refresh()
        self.assertEqual(new_task_info.attempt_count, 1)

    def test__count_attempt_is_false(self):
        task_info = self.Queue.add_task(False)
        self.worker.process_one()
        new_task_info = task_info.refresh()
        self.assertEqual(new_task_info.attempt_count, 0)


class TaskFailedDueToImportErrorTests(DtqTestCase):

    def setUp(self):
        super().setUp()
        self.task_info = DoNothingQueue.add_task(None)
        task: Task = Task.objects.get(pk=self.task_info.task_id)
        task.queue_class_path = "invalid.path.Queue"
        task.save()
        self.worker.process_one()
        self.failed_task: FailedTask = FailedTask.objects.first()

    def test__failed_task_count(self):
        self.assert_failed_task_count_equals(1)

    def test__task_deleted(self):
        self.assertEqual(DoNothingQueue.count(), 0)
        self.assertFalse(self.task_info.task_exists())

    def test__failed_task_attributes_copied_from_task(self):
        self.assert_failed_task_matches_task_info(self.failed_task, self.task_info)

    def test__failed_task_error_details(self):
        self.assertEqual(pydoc.locate(self.failed_task.exc_class), ImportError)
        self.assertIn(ImportError.__name__, self.failed_task.traceback_str)
        self.assertEqual(
            dtq.Worker.ErrorDescriptions.QUEUE_IMPORT_ERROR,
            self.failed_task.error_description,
        )


class TaskFailedDueToDeserializationError(DtqTestCase):
    class Queue(dtq.BaseQueue):
        @classmethod
        def process(cls, task_info: dtq.TaskInfo):
            task_info.get_arg()
            return

    def setUp(self):
        super().setUp()
        task_info = self.Queue.add_task(None, dupe_key="key")
        task: Task = Task.objects.get(pk=task_info.task_id)
        task.arg_data = b"upickleable data"
        task.save()
        self.task_info = task_info.refresh()
        self.worker.process_one()
        self.failed_task = FailedTask.objects.first()

    def test__failed_task_created(self):
        self.assert_failed_task_count_equals(1)

    def test__task_deleted(self):
        self.assertEqual(DoNothingQueue.count(), 0)
        self.assertFalse(self.task_info.task_exists())

    def test__failed_task_attributes_copied_from_task(self):
        self.assert_failed_task_matches_task_info(self.failed_task, self.task_info)

    def test__failed_task_error_details(self):
        self.assertEqual(
            pydoc.locate(self.failed_task.exc_class),
            dtq.DeserializationExc,
        )
        self.assertIn(UnpicklingError.__name__, self.failed_task.traceback_str)
        self.assertIn(dtq.DeserializationExc.__name__, self.failed_task.traceback_str)
        self.assertEqual(
            dtq.Worker.ErrorDescriptions.UNHANDLED_EXCEPTION,
            self.failed_task.error_description,
        )


class ResetStopRequestTests(DtqTestCase):
    def test__stop_request_reset(self):
        task_info = MaxAttemptsQueue.add_task(2)

        self.assertFalse(task_info.stop_requested())
        task_info.request_stop()
        self.assertTrue(task_info.stop_requested())

        self.worker.process_one()
        task_info = task_info.refresh()
        self.assertFalse(task_info.stop_requested())
        self.assertEqual(task_info.attempt_count, 1)

        self.worker.process_one()
        self.assertFalse(task_info.task_exists())


class TaskFailedDueToUnhandledExc(DtqTestCase):

    class CustomExc(Exception):
        pass

    def setUp(self):
        super().setUp()
        self.exc = self.CustomExc("some exception message")
        self.task_info = FailQueue.add_task(self.exc, dupe_key="key")
        self.worker.process_one()
        self.failed_task = FailedTask.objects.first()

    def test__failed_task_count(self):
        self.assert_failed_task_count_equals(1)

    def test__task_deleted(self):
        self.assertEqual(FailQueue.count(), 0)
        self.assertFalse(self.task_info.task_exists())

    def test__failed_task_attributes_copied_from_task(self):
        self.assert_failed_task_matches_task_info(self.failed_task, self.task_info)

    def test__failed_task_error_details(self):
        self.assertEqual(
            pydoc.locate(self.failed_task.exc_class),
            self.CustomExc,
        )
        self.assertIn(self.CustomExc.__name__, self.failed_task.traceback_str)
        self.assertIn(str(self.exc), self.failed_task.traceback_str)
        self.assertEqual(
            dtq.Worker.ErrorDescriptions.UNHANDLED_EXCEPTION,
            self.failed_task.error_description,
        )


class TaskFailedDueQueueTypeError(DtqTestCase):

    def setUp(self):
        super().setUp()
        task_info = DoNothingQueue.add_task(None, dupe_key="key")
        task: Task = Task.objects.get(pk=task_info.task_id)
        task.queue_class_path = (
            "django.db.models.Model"  # Valid path, but not a subclass of BaseQueue
        )
        task.save()
        self.task_info = task_info.refresh()
        self.worker.process_one()
        self.failed_task = FailedTask.objects.first()

    def test__failed_task_count(self):
        self.assert_failed_task_count_equals(1)

    def test__task_deleted(self):
        self.assertEqual(DoNothingQueue.count(), 0)
        self.assertFalse(self.task_info.task_exists())

    def test__failed_task_attributes_copied_from_task(self):
        self.assert_failed_task_matches_task_info(self.failed_task, self.task_info)

    def test__failed_task_error_details(self):
        self.assertEqual(
            pydoc.locate(self.failed_task.exc_class),
            TypeError,
        )
        self.assertIn(TypeError.__name__, self.failed_task.traceback_str)
        self.assertEqual(
            dtq.Worker.ErrorDescriptions.QUEUE_TYPE_ERROR,
            self.failed_task.error_description,
        )


class WorkerProcessAllTests(DtqTestCase):
    def setUp(self):
        super().setUp()
        self.nothing_task_info = DoNothingQueue.add_task(None)
        self.exc_task_info = FailQueue.add_task(Exception())
        self.retry_task_info = MaxAttemptsQueue.add_task(3)
        self.worker.process_all()

    def test__queues_empty(self):
        self.assertEqual(DoNothingQueue.count(), 0)
        self.assertEqual(FailQueue.count(), 0)
        self.assertEqual(MaxAttemptsQueue.count(), 0)

    def test__tasks_deleted(self):
        self.assertEqual(self.nothing_task_info.task_exists(), False)
        self.assertEqual(self.exc_task_info.task_exists(), False)
        self.assertEqual(self.retry_task_info.task_exists(), False)

    def worker_empty(self):
        self.assertEqual(self.worker.count(), 0)
        self.assertEqual(self.worker.count_eligible_tasks(), 0)


class WorkerPriorityTests(DtqTestCase):
    def setUp(self):
        super().setUp()
        self.low = DoNothingQueue.add_task(None, priority=-1)
        self.med = DoNothingQueue.add_task(None, priority=0)
        self.high = DoNothingQueue.add_task(None, priority=1)

    def test__priority_respected(self):
        self.worker.process_one()
        self.assertEqual(self.low.task_exists(), True)
        self.assertEqual(self.med.task_exists(), True)
        self.assertEqual(self.high.task_exists(), False)

        self.worker.process_one()
        self.assertEqual(self.low.task_exists(), True)
        self.assertEqual(self.med.task_exists(), False)

        self.worker.process_one()
        self.assertEqual(self.low.task_exists(), False)


class WorkerQueueFilteringTests(DtqTestCase):
    def setUp(self):
        super().setUp()
        self.nothing_task_info = DoNothingQueue.add_task(None)
        self.exc_task_info = FailQueue.add_task(Exception())
        self.retry_task_info = MaxAttemptsQueue.add_task(3)
        self.worker = dtq.Worker(
            queue_classes=[
                MaxAttemptsQueue,
                FailQueue,
            ]
        )

    def test__count_eligible_tasks(self):
        self.assertEqual(self.worker.count_eligible_tasks(), 2)
        self.worker.process_all()
        self.assertEqual(self.worker.count_eligible_tasks(), 0)

    def test__included_queues__task_processed(self):
        self.worker.process_all()
        self.assertFalse(self.exc_task_info.task_exists())
        self.assert_failed_task_count_equals(1)
        self.assertFalse(self.retry_task_info.task_exists())

    def test__excluded_queues__task_remains(self):
        self.worker.process_all()
        self.assertEqual(DoNothingQueue.count(), 1)
        self.assertTrue(self.nothing_task_info.task_exists())


class WorkerFirstAttemptDatetimeTests(DtqTestCase):
    def setUp(self):
        super().setUp()
        self.task_info = DoNothingQueue.add_task(
            None,
            first_attempt_datetime=timezone.now() + timezone.timedelta(days=1),
        )
        self.task = Task.objects.get(pk=self.task_info.task_id)

    def test__worker_respects_first_attempt_datetime(self):
        self.assertEqual(self.worker.count_eligible_tasks(), 0)
        self.task.next_attempt_datetime = timezone.now()
        self.task.save()
        self.assertEqual(self.worker.count_eligible_tasks(), 1)


class TaskLockTests(DtqTestCase):

    def setUp(self):
        super().setUp()
        self.task_info = DoNothingQueue.add_task(None)
        self.task = Task.objects.get(pk=self.task_info.task_id)

    def test__task_locked_with_other_id(self):
        self.assertEqual(1, self.worker.count_eligible_tasks())
        self.task.lock_id = "any string"
        self.task.save()
        self.assertEqual(0, self.worker.count_eligible_tasks())


class RefreshOnTaskInfoAfterTaskDeleted(DtqTestCase):
    def test__returns_same_data(self):
        task_info = DoNothingQueue.add_task(None)
        self.worker.process_one()
        self.assertFalse(task_info.task_exists())
        refreshed_task_info = task_info.refresh()
        self.assertEqual(task_info, refreshed_task_info)


class TaskPriorityTieBreakerTests(DtqTestCase):
    # When priority is the same, the lowest attempt count is processed first
    # Test processing oldest task first if attempt count is the same
    # To test this, we create tasks that fail and check the order
    # of the FailedTask objects

    def test__attempt_count_same__oldest_task_first(self):
        exc = Exception()
        t1 = FailQueue.add_task(exc)
        t2 = FailQueue.add_task(exc)
        self.worker.process_all()
        self.assert_failed_task_matches_task_info(FailedTask.objects.first(), t1)
        self.assert_failed_task_matches_task_info(FailedTask.objects.last(), t2)

    def test__tie_break_lowest_last_attempt_datetime_first(self):
        exc = Exception()
        t1 = FailQueue.add_task(exc)
        t2 = FailQueue.add_task(exc)
        t3 = FailQueue.add_task(exc)

        task1: Task = t1._get_task()
        task2: Task = t2._get_task()
        task3: Task = t3._get_task()

        now = timezone.now()
        task1.created_datetime = task2.created_datetime = task3.created_datetime
        task1.last_attempt_datetime = now - timezone.timedelta(days=1)
        task2.last_attempt_datetime = now - timezone.timedelta(days=2)
        task3.last_attempt_datetime = None
        task1.save()
        task2.save()
        task3.save()
        t1 = t1.refresh()
        t2 = t2.refresh()
        t3 = t3.refresh()

        self.worker.process_all()

        self.assert_failed_task_count_equals(3)
        f1, f2, f3 = FailedTask.objects.all()
        self.assert_failed_task_matches_task_info(f1, t3)
        self.assert_failed_task_matches_task_info(f2, t2)
        self.assert_failed_task_matches_task_info(f3, t1)

    def test__tie_break_lowest_created_datetime_first(self):
        exc = Exception()
        t1 = FailQueue.add_task(exc)
        t2 = FailQueue.add_task(exc)

        task = t2._get_task()
        task.created_datetime = timezone.now() - timezone.timedelta(days=1)
        task.save()

        self.worker.process_all()
        self.assert_failed_task_matches_task_info(FailedTask.objects.first(), t2)
        self.assert_failed_task_matches_task_info(FailedTask.objects.last(), t1)

    def test__tie_break_lowest_attempt_count_first(self):
        exc = Exception()
        t1 = FailQueue.add_task(exc)
        t2 = FailQueue.add_task(exc)

        task1: Task = t1._get_task()
        task2: Task = t2._get_task()
        task1.attempt_count = 1
        task2.created_datetime = task1.created_datetime
        task1.save()
        task2.save()

        t1 = t1.refresh()
        t2 = t2.refresh()

        self.worker.process_all()
        self.assert_failed_task_matches_task_info(
            FailedTask.objects.first(),
            t2,
        )
        self.assert_failed_task_matches_task_info(
            FailedTask.objects.last(),
            t1,
        )


class WorkerThreadControlTests(DtqTestCase):
    def test__worker_stops(self):
        self.worker.start()
        self.assertTrue(self.worker.is_alive())
        self.worker.stop(timeout=2)
        self.assertFalse(self.worker.is_alive())


class AllWorkerThreadStopTests(DtqTestCase):
    def setUp(self):
        super().setUp()
        self.worker1 = dtq.Worker()
        self.worker2 = dtq.Worker()
        self.worker_group = dtq.WorkerGroup([self.worker1, self.worker2])

    def tearDown(self):
        super().tearDown()
        if self.worker_group.is_alive():
            try:
                self.worker_group.stop(timeout_per_worker=5)
            except Exception as e:
                warnings.warn(str(e))

    def test__start_and_stop(self):
        self.worker_group.start()
        self.assertTrue(self.worker_group.is_alive())
        self.assertTrue(self.worker1.is_alive())
        self.assertTrue(self.worker2.is_alive())

        self.worker_group.stop(timeout_per_worker=5)
        self.assertFalse(self.worker_group.is_alive())
        self.assertFalse(self.worker1.is_alive())
        self.assertFalse(self.worker2.is_alive())


class WorkerGroupFromSettingsTest(DtqTestCase):

    def setUp(self):
        super().setUp()
        self.settings = {
            "workers": [
                {
                    "queue_classes": [
                        "django_task_queue.tests.DoNothingQueue",
                        "django_task_queue.tests.MaxAttemptsQueue",
                    ],
                    "num_threads": 1,
                },
                {
                    "queue_classes": [
                        "django_task_queue.tests.FailQueue",
                    ],
                    "num_threads": 2,
                },
            ]
        }
        self.worker_group = dtq.WorkerGroup.from_settings(self.settings)

    def test__correct_work_types(self):
        self.assertIsInstance(self.worker_group, dtq.WorkerGroup)
        workers = self.worker_group.workers

        self.assertEqual(3, len(workers))

        worker1 = workers[0]
        self.assertEqual(
            worker1.queue_classes,
            [DoNothingQueue, MaxAttemptsQueue],
        )

        worker2 = workers[1]
        self.assertEqual(
            worker2.queue_classes,
            [FailQueue],
        )
