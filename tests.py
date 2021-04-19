import signal
from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone
from django.utils.timezone import make_aware

from django_task_queue.exceptions import (
    NoEligibleTaskException,
    FatalTaskException,
    NoIncrementErrorCountException,
)
from django_task_queue.queues import BaseQueue
from django_task_queue.workers import BaseWorker, AllWorkersThread


class AdditionQueue(BaseQueue):

    @classmethod
    def append(cls, x, y):
        return super().append(x=x, y=y)

    @classmethod
    def process(cls, x, y):
        return x + y


class ErrorQueue(BaseQueue):
    max_attempts = 2

    class ForcedException(Exception):
        pass

    @classmethod
    def append(cls, msg):
        return super().append(msg=msg)

    @classmethod
    def process(cls, msg):
        raise ErrorQueue.ForcedException(msg)


class FatalErrorQueue(BaseQueue):
    max_attempts = 10

    @classmethod
    def append(cls, msg):
        return super().append(msg=msg)

    @classmethod
    def process(cls, msg):
        raise FatalTaskException(msg)


class NoIncrementErrorCountQueue(BaseQueue):
    max_attempts = 1

    @classmethod
    def append(cls, msg):
        return super().append(msg=msg)

    @classmethod
    def process(cls, msg):
        raise NoIncrementErrorCountException(msg)


class TaggedQueue(BaseQueue):
    tag = 'my tag'

    def process(self, **kwargs):
        pass


class BaseQueueTests(TestCase):

    def setUp(self):
        self.queue_class = AdditionQueue
        self.worker = BaseWorker()

    def __append_task(self):
        return self.queue_class.append(1, 2)

    def test__add_task__creates_task(self):
        self.assertEqual(0, self.worker.count)
        task = self.__append_task()
        self.assertEqual(1, self.worker.count)
        self.assertEqual(
            task.data,
            {'x': 1, 'y': 2},
        )
        self.assertEqual(1, self.queue_class.count())

    def test__process_one__empty_queue__raises_exception(self):
        self.assertRaises(NoEligibleTaskException, self.worker.process_one)

    def test__process_one__task_has_lock_id__throws_no_eligible_task_exception(self):
        task = self.__append_task()
        task.lock_id = 1
        task.save()
        self.assertRaises(NoEligibleTaskException, self.worker.process_one)

    def test__pop__multiple_eligible_tasks__return_oldest_one(self):
        self.__append_task()
        task2 = self.__append_task()
        task2.created_datetime = make_aware(datetime(2000, 1, 1))
        task2.save()
        self.assertEqual(task2.id, self.worker.pop().id)

    def test__pop__sets_unique_lock_id(self):
        self.__append_task()
        self.__append_task()

        worker1 = BaseWorker()
        worker2 = BaseWorker()
        pop1 = worker1.pop()
        pop2 = worker2.pop()

        self.assertEqual(self.worker.count_processing, 2)
        self.assertNotEqual(pop1.lock_id, pop2.lock_id)

        # Both tasks now locked. Test that pop returns None using different worker instances.
        self.assertIsNone(self.worker.pop())
        self.assertIsNone(worker1.pop())
        self.assertIsNone(worker2.pop())

    def test__pop__sets_last_attempt_datetime(self):
        task = self.__append_task()
        self.assertIsNone(task.last_attempt_datetime)
        self.worker.pop()
        task.refresh_from_db()
        self.assertIsNotNone(task.last_attempt_datetime)

    def test__process_one__returns_without_error__removes_task(self):
        self.__append_task()
        result = self.worker.process_one()
        self.assertEqual(3, result)
        self.assertEqual(0, self.worker.count_processing)
        self.assertEqual(0, self.worker.count)

    def test__process_one__raises_exception__sets_error_fields(self):
        msg = 'An error message'
        task = ErrorQueue.append(msg)
        result = self.worker.process_one()  # Task raised an exception
        self.assertEqual(result.__class__, ErrorQueue.ForcedException)
        self.assertEqual(0, self.worker.count_processing)
        self.assertEqual(1, self.worker.count)

        # Check error was processed correctly
        task.refresh_from_db()
        self.assertEqual(msg, task.last_error)
        self.assertEqual('', task.lock_id)
        self.assertIsNotNone(task.last_attempt_datetime)
        self.assertTrue(timezone.now() - task.last_attempt_datetime < timedelta(seconds=1))

        # The task cannot be attempted again for some time
        self.assertRaises(NoEligibleTaskException, self.worker.process_one)

        # After setting the following property to zero, pop should return the task again
        self.worker.min_seconds_between_processing_attempts = 0
        self.assertEqual(task.id, self.worker.pop().id)

    def test__tag_filtering(self):
        TaggedQueue.append()

        # The default worker should not process this task
        self.assertIsNone(self.worker.pop())

        # A worker with the matching tag will process the task
        tagged_worker = BaseWorker(tags=[TaggedQueue.tag, 'another tag'])
        self.assertIsNotNone(tagged_worker.pop())

        # The tagged worker should not process default tasks
        AdditionQueue.append(1, 2)
        self.assertIsNone(tagged_worker.pop())

    def test__error_count_limit(self):
        task = ErrorQueue.append('error limit test')
        self.worker.min_seconds_between_processing_attempts = 0

        self.worker.process_one()
        task.refresh_from_db()
        self.assertEqual(task.error_count, 1)
        self.assertEqual(task.retry_allowed, True)
        self.assertEqual(self.worker.count_eligible, 1)

        self.worker.process_one()
        task.refresh_from_db()
        self.assertEqual(task.error_count, 2)
        self.assertEqual(task.retry_allowed, False)
        self.assertEqual(self.worker.count_eligible, 0)

    def test__fatal_task_exception(self):
        task = FatalErrorQueue.append('fatal task error')
        self.worker.process_one()
        task.refresh_from_db()
        self.assertFalse(task.retry_allowed)
        self.assertEqual(0, self.worker.count_eligible)

    def test__no_increment_error_count_exception(self):
        task = NoIncrementErrorCountQueue.append(msg='no increment')
        self.worker.process_one()
        task.refresh_from_db()
        self.assertTrue(task.retry_allowed)
        self.assertEqual(task.error_count, 0)


class WorkerTests(TestCase):

    def test__all_workers_thread(self):
        thread = AllWorkersThread()
        thread.start()
        self.assertTrue(thread.is_alive())
        thread.handle_stop_signal(signal.SIGINT, frame=None)
        thread.join(5)
        self.assertFalse(thread.is_alive())
