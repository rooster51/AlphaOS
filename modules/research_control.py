"""Request-local cooperative cancellation; never cache or replace observations."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event

_cancelled = ContextVar('research_cancelled', default=None)


def checkpoint():
    event = _cancelled.get()
    if event is not None and event.is_set():
        raise asyncio.CancelledError()


@contextmanager
def cancellable_research():
    event = Event()
    token = _cancelled.set(event)
    try:
        yield event
    finally:
        event.set()
        _cancelled.reset(token)
