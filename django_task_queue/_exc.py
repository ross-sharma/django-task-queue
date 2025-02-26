class DtqExc(Exception):
    pass


class QueueImportExc(DtqExc):
    def __init__(self, msg: str, queue_class: type):
        super().__init__(msg)
        self.queue_class = queue_class


class SerializationExc[T](DtqExc):
    def __init__(self, msg: str, obj: T):
        super().__init__(msg)
        self.obj = obj


class DeserializationExc(DtqExc):
    def __init__(self, msg: str, data: bytes):
        super().__init__(msg)
        self.data = data


class DupeKeyExc(DtqExc):
    def __init__(self, dupe_key: str):
        msg = f"A task with dupe key '{dupe_key}' already exists"
        super().__init__(msg)
        self.dupe_key = dupe_key