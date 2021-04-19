class TaskQueueException(Exception):
    pass


class NoEligibleTaskException(TaskQueueException):
    pass


# If this exception is raised by a queue while processing a task,
# the task will not be attempted again.
class FatalTaskException(TaskQueueException):
    pass


# Error count will not be incremented if this exception is raised
class NoIncrementErrorCountException(TaskQueueException):
    pass
