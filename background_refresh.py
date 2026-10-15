"""Cooperative one-read-at-a-time refreshes; foreground edits take priority."""

class BackgroundRefresh:
    def __init__(self, executor, schedule, read, receive, busy):
        self.executor, self.schedule = executor, schedule
        self.read, self.receive, self.busy = read, receive, busy
        self.pending = {}
        self.active = None
        self.generation = 0
        self.closed = False

    def invalidate(self, clear=False):
        self.generation += 1
        if clear:
            self.pending.clear()
        elif self.active:
            _, setting, _ = self.active
            self.pending.setdefault(setting.key, setting)

    def request(self, settings):
        if self.closed:
            return
        for setting in settings:
            self.pending[setting.key] = setting
        self.resume()

    def resume(self):
        if self.closed or self.active or self.busy() or not self.pending:
            return
        key = next(iter(self.pending))
        setting = self.pending.pop(key)
        future = self.executor.submit(self.read, setting)
        self.active = future, setting, self.generation
        self.schedule(20, self._poll)

    def _poll(self):
        if self.closed or self.active is None:
            return
        future, setting, generation = self.active
        if not future.done():
            self.schedule(20, self._poll)
            return
        self.active = None
        value, error = None, None
        try:
            value = future.result()
        except Exception as exc:
            error = str(exc)
        if generation == self.generation and not self.busy():
            self.receive(setting, value, error)
        self.resume()

    def close(self):
        self.closed = True
        self.pending.clear()
