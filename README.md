# Django Task Queue
A simple task queue for Django web framework

## Table of Contents

- [Motivation](#motivation)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Queues](#queues)
  - [Defining a queue](#defining-a-queue)
  - [Adding tasks](#adding-tasks)
  - [Processing tasks](#processing-tasks)
- [Examples](#examples)
  - [Getting the task arguments](#getting-the-task-arguments)
  - [Scheduling a task for later](#scheduling-a-task-for-later)
  - [Prioritizing tasks](#prioritizing-tasks)
  - [Preventing duplicate tasks](#preventing-duplicate-tasks)
  - [Limiting maximum attempts](#limiting-maximum-attempts)
  - [Ignoring attempts](#ignoring-attempts)
  - [Setting a delay before retrying](#setting-a-delay-before-retrying)
  - [Exponential backoff](#exponential-backoff)
  - [Interrupting a long-running task](#interrupting-a-long-running-task)
  - [A complete example](#a-complete-example)
- [Workers](#workers)
  - [Creating workers programmatically](#creating-workers-programmatically)
- [Failed Tasks](#failed-tasks)
 
## Motivation
Django Task Queue is a simple task queue for Django. 
It is designed to be easy to use and to require minimal setup. 
The goal is to provide a simple way to run background tasks in Django,
while still allowing for more advanced features such as retrying, cancelling, and error handling.

Here are some advantages of using Django Task Queue:

- No dependencies other than Django itself
- Tasks can be viewed and edited using the standard Django Admin interface
- Unhandled errors are recorded in the database and can be viewed in Django Admin
- Tasks can be processed in the background using a simple command
- Features a simple and flexible API for prioritizing, scheduling, retrying, cancelling, and error handling
- Worker threads can be configured easily using Django settings
- Tasks can be handled by multiple processes or machines using a shared database
- Type hints are used everywhere, making it easy to use with an IDE



## Installation
Using ```pip```
```commandline
pip install django-task-queue
```
In your project's ```settings.py``` file, add ```django_task_queue```to ```INSTALLED_APPS```:
```python
INSTALLED_APPS = [
    # ...
    "django_task_queue",
]
```
Then, create the database tables by running ```migrate```:
```commandline
python manage.py migrate
```

## Quick Start
*Note: The quick start example omits type hints for the sake of brevity. 
Later examples will include full type hints.*

Define a class that inherits from ```BaseQueue``` and override the ```process``` method.
We'll assume this code is in ```my_queue.py```.
```python
# my_queue.py
from django_task_queue import BaseQueue

class MyQueue(BaseQueue):

    @classmethod
    def process(cls, task_info):
        number = task_info.get_arg()
        print(f"----> QUEUE PROCESSING TASK {number=}")
```

Tasks can now be added to the queue using the ```add_task``` method:
```
MyQueue.add_task(1)
```
Here is a script that adds add three tasks to ```MyQueue``` that could go in any file in your project:
Let's put this inside ```add_tasks.py```.
```python
# add_tasks.py
import django, os

from my_queue import MyQueue

os.environ["DJANGO_SETTINGS_MODULE"] = "my_app.settings"
django.setup()

MyQueue.add_task(1)
MyQueue.add_task(2)
MyQueue.add_task(3)

print("Tasks added to queue.")
print(f"MyQueue now has {MyQueue.count()} tasks waiting.")
```
Execute the script above using ```python add_tasks.py```. You should see the following output:
```
Tasks added to queue.
MyQueue now has 3 tasks waiting.
```

We can process the tasks using the ```dtq_startworkers``` utility command:
```commandline
python manage.py dtq_startworkers
``` 
Output:
```
No DJANGO_TASK_QUEUE setting found. Creating default worker.
250224 10:18:41 django_task_queue INFO Worker-thread: Worker started.
250224 10:18:41 django_task_queue INFO Worker-thread: Processing task: my_queue.MyQueue
----> QUEUE PROCESSING TASK number=1
250224 10:18:41 django_task_queue INFO Worker-thread: Processing task: my_queue.MyQueue
----> QUEUE PROCESSING TASK number=2
250224 10:18:41 django_task_queue INFO Worker-thread: Processing task: my_queue.MyQueue
----> QUEUE PROCESSING TASK number=3
```

The queue is now empty, so the worker will sleep until more tasks are added.
At this point, you could run ```add_tasks.py``` again 
from a different shell to add more tasks.
You can stop the worker by pressing ```Ctrl+C```.

```
250224 10:20:38 django_task_queue INFO MainThread: Stopping <Worker(Worker-thread, started 17416)>...
250224 10:20:39 django_task_queue INFO Worker-thread: Stop flag set. Thread terminating.
250224 10:20:39 django_task_queue INFO MainThread: <Worker(Worker-thread, stopped 17416)> stopped.
```

## Configuration
The quick start example above creates a single worker thread that processes all tasks.
We can define a ```DJANGO_TASK_QUEUE``` setting in ```settings.py``` to configure the workers.

Here is a minimal configuration that creates four workers instead of the default of one:

```python
DJANGO_TASK_QUEUE = {
    "workers": [
        { "num_threads": 4 },
    ],
}
```

Running ```python manage.py dtq_startworkers``` with this configuration will create four workers, each with one thread.
```
DJANGO_TASK_QUEUE setting found. Creating worker group...
250224 10:38:58 django_task_queue INFO dtq-worker-1: Worker started.
250224 10:38:58 django_task_queue INFO dtq-worker-2: Worker started.
250224 10:38:58 django_task_queue INFO dtq-worker-3: Worker started.
250224 10:38:58 django_task_queue INFO dtq-worker-4: Worker started.
```

Here is an full example of a configuration:

```python
DJANGO_TASK_QUEUE = {
    "workers": [
        {
            "name": "quicktasks",
            "num_threads": 1,
            "sleep_seconds_when_empty": 0.5,
            "queue_classes": [
                "django_task_queue.examples.DoNothingQueue",
                "django_task_queue.examples.MaxAttemptsQueue",
                "django_task_queue.examples.FailQueue",
            ],
        },
        
        {
            "name": "longtasks",
            "num_threads": 2,
            "sleep_seconds_when_empty": 1.25,
            "queue_classes": [
                "django_task_queue.examples.StoppableTaskQueue"
            ],
        },
    ]
}
```
In the example above, we define two sets of workers.
All of the options for each worker are optional.
Here are the settings for each set of worker:
 
| Name | Description |
|-|-|
| ```name``` | Optional `str`. Default `dtq-worker`Gets used in the thread names and shows up in log messages. <br/> The actual thread names will be ```dtq-worker-1```, ```dtq-worker-2```, etc. |
| ```num_threads``` | Optional `int`. Default `1`. Defines how many worker instances (threads) are created                                                                                                  |
|```sleep_seconds_when_empty``` |  Optional `int`. Default `1`. Defines how many seconds the workers should sleep when there are no tasks in the queue                                                        |
|```queue_classes``` | Optional `list[str]`. Default `[]`. A list of queue classes that the workers should process. <br/>If the list is empty, the workers will process **all queues**.                                         |

## Queues
### Defining a queue
All queues classes must inherit from the `BaseQueue` class. The `process` method must be overridden.

When defining a queue, we must first determine what data the task needs to process.
Any type that can be serialized with the ```pickle``` module can be used as an argument.
Using generics, we can enable type-hinting for the argument.

Here is an example that uses a custom `dataclass` as an argument. 
This is the recommended way to pass data to the queue:

```python
from typing import Optional
from dataclasses import dataclass

from django_task_queue import BaseQueue, TaskInfo, Retry


@dataclass
class Person:
    name: str
    age: int 
   
    
class PersonQueue[T: Person](BaseQueue[T]):

    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Optional[Retry]:
        person = task_info.get_arg()
        print(f"Processing {person}")
        return None
```

### Adding tasks
Use the `add_task` method of the queue class to add tasks to the queue.
```python
alice = Person("Alice", 25)
PersonQueue.add_task(alice)
```

The add_task method has some optional arguments that can be used to customize the task.
Its full signature is:
```python
    @classmethod
    def add_task(
        cls,
        arg: T,
        note: str | None = None,
        priority: int | None = None,
        first_attempt_datetime: datetime.datetime | None = None,
        dupe_key: str | None = None,
    ) -> TaskInfo[T]:
```
| Parameter | Description
|-|-|
|`arg`| Required. This is the data that the queue will process. <br/>It can be of any type that can be serialized with the `pickle` module.|
|`note`| Optional `str`. A note that can be used to describe the task. <br/>The note is for informational purposes only. <br/> Task notes are searchable from the Django Admin interface.|
|`priority` | Optional `str`. The priority of the task. <br/>Tasks with higher priority values are processed before tasks with lower priority values. <br/>The default priority is 0.|
|`first_attempt_datetime`| Optional `datetime`. Specifies a time before which the task should not be processed. <br/>Can be used to schedule tasks for processing at a later time.|
|`dupe_key`| Optional `str`. A unique key that can be used to prevent duplicate tasks from being added to the queue. <br/>If a task with the same dupe key already exists in the queue, the `add_task` will throw a `django_task_queue.DupeKeyExc`.

The `add_task` method returns a `TaskInfo` object that can be used to retrieve the task's arguments and other information.
It contains necessary information and methods intended for usage in the `process` method of the queue.
It is returned by the `add_task` for informational purposes only.
For more information about `TaskInfo`, see the [examples](#examples) section.


### Processing tasks
All queues must override the `process` method. This method is called by the worker to process the task.
There are three ways the `process` method can return:
- If the `process` method return `None`, the task is considered complete and removed from the queue.
- If the `process` method returns a `Retry` object, the task is retried according to the `Retry` object's settings.
- If the `process` method raises an exception, the task is considered failed, and is removed from the queue.
The failed task will be saved in the `FailedTask` table, which can be viewed in Django Admin.
 
The `process` method can return a `Retry` object to specify how a task should be retried. 
See [examples](#examples) for usage information.

| Parameter | Description |
|-|-|
|when| Optional `datetime`. Default `None`. The task will not be eligible for processing until after this value. <br/> If `None`, the task will be eligible for processing immediately.|
|count_attempt| Optional `bool`. Default `True`. If `False`, the task's `attempt_count` will not be incremented.|


## Examples
### Getting the task arguments
The task arguments that were passed to the `add_task` method can be retrieved using the `get_arg` 
method of the `TaskInfo` object. May throw a `django_task_queue.DeserializionExc` if the data cannot be deserialized.
In most cases, it is safe to ignore the exception and allow it to be raised, 
causing the task to be removed from the queue and added to the `FailedTask` table.
```python
from django_task_queue import BaseQueue, TaskInfo, DeserializationExc, Retry

class MyQueue[T:str](BaseQueue):

    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        try:
            arg_text = task_info.get_arg()
        except DeserializationExc as e:
            print(f"Error deserializing task arguments: {e}")
            raise
        
        print(f"Processing task with arguments: {arg_text}")
        return None
```

### Scheduling a task for later
The optional `first_attempt_datetime` argument of the `add_task` method can be used to schedule a task for processing at a later time.
```python
from django_task_queue.examples import DoNothingQueue
from django.utils import timezone

# Task will not be eligible for processing until five minutes from now
when = timezone.now() + timezone.timedelta(minutes=5)
DoNothingQueue.add_task(None, first_attempt_datetime=when)
```


### Prioritizing tasks
Tasks can be assigned a priority. Higher priority tasks will always be tried before lower priority tasks.
The default priority is 0.
```python
from django_task_queue.examples import DoNothingQueue

# Task will be tried before other tasks with a lower priority
DoNothingQueue.add_task(None, priority=1)
```

### Preventing duplicate tasks
Tasks can be prevented from being added to the queue if they have the same `dupe_key`.
If the `dupe_key` is not `None`, and a task with the same `dupe_key` already exists in the queue,
a `DupeKeyExc` will be raised.
```python
from django_task_queue.examples import DoNothingQueue
from django_task_queue import DupeKeyExc


DoNothingQueue.add_task(None, dupe_key="my dupe key") # No problem

try:
    DoNothingQueue.add_task(None, dupe_key="my dupe key") # dupe key collision
except DupeKeyExc:
    # handle this exception
    pass
```

### Limiting maximum attempts
This example shows how to use the `Retry` class to limit the number of times a task can be retried.
When processing the task, the `attempt_count` attribute of the `task_info` object can be used to determine how many 
times the task has been previously attempted.
```python
from django_task_queue import BaseQueue, TaskInfo, Retry

class MaxAttemptsQueue[T: None](BaseQueue[T]):
    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        if task_info.attempt_count >= 5:
            raise Exception("Max attempts reached")
        return Retry()
```

### Ignoring attempts
Sometimes, a task can fail for reasons that do not warrant increasing the attempt count.
For example, we might want to ignore an attempt if it fails due to a network error.
In this case, we can return a `Retry` object with `count_attempt=False`.

```python
from django_task_queue import BaseQueue, TaskInfo, Retry

class IgnoreAttemptExample[T: int](BaseQueue[T]):
    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        return Retry(count_attempt=False)
```

<a id="retry-when"></a>
### Setting a delay before retrying
The `Retry` class can be used to specify a time when the task should be retried.

```python
from django_task_queue import BaseQueue, TaskInfo, Retry
from django.utils import timezone

class DelayedRetryExample[T: int](BaseQueue[T]):
    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        return Retry(when=timezone.now() + timezone.timedelta(seconds=60))
```

### Exponential backoff
This example shows how to use the `Retry` class to implement exponential backoff.
Each time the task fails, it is retried with a delay that increases exponentially,
until it reaches its `max_attempts` argument.
```python
import time
from django.utils import timezone
from django_task_queue import BaseQueue, TaskInfo, Retry

class ExponentialBackoff[T: None](BaseQueue[T]):

    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        arg = task_info.get_arg()
        time.sleep(1)

        if task_info.attempt_count >= arg.max_attempts:
            raise Exception("Max attempts reached")

        delay = 2**task_info.attempt_count
        print(f"Task failed, retrying after {delay} seconds")
        retry_time = timezone.now() + timezone.timedelta(seconds=delay)
        return Retry(when=retry_time)
```

### Interrupting a long-running task
This example shows how to interrupt a long-running task when the worker is stopped.
When a worker is stopped, it must wait for any currently running tasks to finish before it can exit.
Therefore, for long-running tasks, it is advisable to periodically call `task_info.stop_requested()` to see
if the worker is requesting that the task be stopped.
```python
import time
from django_task_queue import BaseQueue, TaskInfo, Retry

class StoppableTaskQueue[T: None](BaseQueue[T]):

    @classmethod
    def process(cls, task_info: TaskInfo[T]) -> Retry | None:
        start_time = time.time()
        print("Processing for 30 seconds...")
        while time.time() - start_time < 30:
            time.sleep(0.5) # Poll the stop flag every 0.5 seconds
            if task_info.stop_requested():
                print("Task stopped by worker.")
                return Retry(count_attempt=False)
        return None
```

### A complete example
This example shows how previous examples can be combined for a real-life situation.
It calls a method `_long_running_task`, which simulates a long-running task that can fail for various reasons.
The processing time of `_long_running_task` is determined by the argument passed to the task.
- On success, the task is removed from the queue.
- If it raises a `NetworkError` or `TooManyRequests`, the task is retried after a delay specified in the task argument.
The task's attempt count is not incremented.
- If it raises any other `Exception`, the task is retried with exponential backoff, up to a maximum number specified in 
the task argument.
- If the maximum number of attempts is reached, the task is removed from the queue and added to the `FailedTask` table.
- If the worker is stopped while the task is running, processing is cancelled and the task gets retried 
without incrementing the attempt count.

```python
from django_task_queue import BaseQueue, TaskInfo, Retry
import dataclasses


@dataclasses.dataclass
class CompleteExampleArg:
    retry_delay_seconds: float
    long_task_seconds: float
    max_attempts: int


class CompleteExampleQueue(BaseQueue[CompleteExampleArg]):
    class NetworkError(Exception):
        pass

    class TooManyRequests(Exception):
        pass

    class TaskStopped(Exception):
        pass

    @classmethod
    def process(cls, task_info: TaskInfo[CompleteExampleArg]) -> Retry | None:
        from django.utils import timezone

        arg = task_info.get_arg()
        print()
        print(f"Processing: {task_info.note}")
        print(f"Attempt {task_info.attempt_count} of {arg.max_attempts}")

        try:
            cls._long_running_task(arg, task_info)

        except (cls.NetworkError, cls.TooManyRequests) as e:
            retry_when = timezone.now() + timezone.timedelta(
                seconds=arg.retry_delay_seconds
            )
            print(
                f"Got {e.__class__.__name__}, retrying after "
                f"{arg.retry_delay_seconds:.1f} seconds\n"
            )
            return Retry(count_attempt=False, when=retry_when)

        except cls.TaskStopped:
            print(f"Task stopped by worker.\n")
            return Retry(count_attempt=False)

        except Exception:
            backoff_delay = 2**task_info.attempt_count
            if task_info.attempt_count >= arg.max_attempts:
                raise
            print(
                f"Unknown error. Attempt count={task_info.attempt_count}."
                f"Retrying after {backoff_delay} seconds\n"
            )
            retry_when = timezone.now() + timezone.timedelta(seconds=backoff_delay)
            return Retry(count_attempt=True, when=retry_when)

        # Call succeeded, so return None to remove the task.
        print("Task succeeded.\n")
        return None

    @classmethod
    def _long_running_task(
        cls, 
        arg: CompleteExampleArg,
        task_info: TaskInfo[CompleteExampleArg],
    ):
        import time
        import random

        start_time = time.time()
        time.sleep(1)

        match random.randint(1, 4):
            case 1:
                raise cls.NetworkError()
            case 2:
                raise cls.TooManyRequests()
            case 3:
                raise Exception()
            case _:
                print(f"Processing for {arg.long_task_seconds:.1f} seconds...")
                while time.time() - start_time < arg.long_task_seconds:
                    time.sleep(1)  # Poll the stop flag once per second
                    if task_info.stop_requested():
                        raise cls.TaskStopped()
        return None 
```





## Workers
### Creating workers programmatically
The `django_task_queue.WorkerGroup` is a subclass of `threading.Thread` and can be used
to control a group of workers programmatically.
Here is an example where we create a `WorkerGroup` with various workers processing different
queues. 

```python
from django_task_queue import WorkerGroup, Worker
from django_task_queue.examples import DoNothingQueue, MaxAttemptsQueue, FailQueue

workers = [
    Worker(
        thread_name="worker-1",
        sleep_seconds_when_empty=1,
        queue_classes=[DoNothingQueue, FailQueue],
    ),
    Worker(
        thread_name="worker-2",
        sleep_seconds_when_empty=2,
        queue_classes=[MaxAttemptsQueue],
    ),
]

wg = WorkerGroup(workers)
wg.start()

while wg.is_alive():
    import time
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        wg.stop()
```

The `WorkerGroup` and `Worker` are controlled like any other `threading.Thread` object.
In addition to the methods of `threading.thread`, `WorkerGroup` and `Worker` have the following methods:
- `stop()` This sets a flag that tells the workers to stop processing tasks. 
This method will wait for all threads to stop before returning.
- `request_stop()` This sets a flag that tells the workers to stop processing tasks.
This method will return immediately.

## Failed Tasks
A task can be removed from the queue for various reasons and put into the `FailedTask` table for the following reasons:
- The `process` of the queue raised an `Exception`
- The queue class could not be imported by the worker
- The worker detected that the queue class is not a subclass of `BaseQueue`
 
The `FailedTask` objects will contain all the information about the task,
including the arguments passed to the `add_task` method.
In addition, it will store a traceback of the exception that caused the task to fail.

## Django Admin
The `Task` and `FailedTask` can be viewed and edited using the Django Admin interface.
Notably, the "note" field of the  can be used to search for `Tasks` and `FailedTasks`.
The `traceback_str`, `exc_class`, and `error_description` fields of `FailedTasks` are also searchable.

[<img src="https://github.com/ross-sharma/django-task-queue/blob/updates-2025/img/tasks_admin.jpg?raw=true" alt="drawing" width="200"/>](https://raw.githubusercontent.com/ross-sharma/django-task-queue/refs/heads/updates-2025/img/tasks_admin.jpg)

[<img src="https://github.com/ross-sharma/django-task-queue/blob/updates-2025/img/failedtasks_admin.jpg?raw=true" alt="drawing" width="200"/>](https://raw.githubusercontent.com/ross-sharma/django-task-queue/refs/heads/updates-2025/img/failedtasks_admin.jpg)
