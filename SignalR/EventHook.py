class EventHook:
    def __init__(self, *handlers):
        self._handlers = []
        self.add_hooks(*handlers)

    def add_hooks(self, *handlers):
        self._handlers.extend(handlers)
        return self

    async def async_trigger_hooks(self, *args, **kwargs):
        for handler in self._handlers:
            await handler(*args, **kwargs)

    def trigger_hooks(self, *args, **kwargs):
        for handler in self._handlers:
            handler(*args, **kwargs)
