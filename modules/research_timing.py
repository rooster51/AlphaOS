"""Opt-in per-request timings. No evidence, URLs, credentials or exception text."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
import json
import logging
import re
import secrets
from threading import Lock
from time import perf_counter
from modules.research_control import checkpoint, cancellable_research


@dataclass(frozen=True)
class Trace:
    request_id: str
    started: float
    symbol: str | None = None
    mode: str | None = None


_trace = ContextVar('research_timing', default=None)
_lock = Lock()
_counts = dict(request=0, execution=0)
_logger = logging.getLogger('alphaos_api.research.timing')


def emit(stage, phase, *, duration_ms=None, outcome=None, status=None):
    trace = _trace.get()
    if trace is None:
        return
    with _lock:
        counts = dict(_counts)
    value = dict(event='research_timing', request_id=trace.request_id, stage=stage,
        phase=phase, elapsed_ms=round((perf_counter()-trace.started)*1000),
        inflight_requests=counts['request'], active_executions=counts['execution'])
    if trace.symbol is not None:
        value.update(symbol=trace.symbol, research_mode=trace.mode)
    if duration_ms is not None:
        value['duration_ms'] = duration_ms
    if outcome is not None:
        value['outcome'] = outcome
    if isinstance(status, int) and 100 <= status <= 599:
        value['status'] = status
    # The production entrypoint uses WARNING. Use a dedicated logger and a
    # fixed event name so start records survive even if a dependency never ends.
    _logger.warning('%s', json.dumps(value))


@contextmanager
def stage(name):
    checkpoint()
    if _trace.get() is None:
        yield
        checkpoint()
        return
    started = perf_counter()
    emit(name, 'start')
    outcome = 'complete'
    try:
        yield
        checkpoint()
    except BaseException as error:
        outcome = 'cancelled' if isinstance(error, asyncio.CancelledError) else 'error'
        raise
    finally:
        emit(name, 'end', duration_ms=round((perf_counter()-started)*1000), outcome=outcome)


@contextmanager
def execution(symbol, mode):
    trace = _trace.get()
    if trace is None:
        yield
        return
    token = _trace.set(replace(trace, symbol=symbol if symbol in ('SPY','QQQ') else None,
        mode=mode if mode in ('current','historical') else None))
    with _lock:
        _counts['execution'] += 1
    try:
        with stage('research_execution'):
            yield
    finally:
        with _lock:
            _counts['execution'] -= 1
        _trace.reset(token)


class ResearchTimingMiddleware:
    """Observe ASGI messages and signal request-local workers on disconnect."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') != 'POST' or scope.get('path') not in ('/v1/research/market','/v1/research/observation'):
            return await self.app(scope, receive, send)
        supplied = next((v.decode('latin1') for k,v in scope.get('headers', [])
            if k.lower() == b'x-alphaos-request-id'), '')
        request_id = supplied if re.fullmatch('[0-9a-f]{32}', supplied) else secrets.token_hex(16)
        # Share the sanitized ID with the existing response/error boundary.
        scope = dict(scope, headers=[(k,v) for k,v in scope.get('headers', [])
            if k.lower() != b'x-alphaos-request-id'] + [(b'x-alphaos-request-id', request_id.encode())])
        token = _trace.set(Trace(request_id, perf_counter()))
        with _lock:
            _counts['request'] += 1
        disconnected = False
        finished = False
        status = None

        async def observed_receive():
            nonlocal disconnected
            message = await receive()
            if message['type'] == 'http.disconnect' and not disconnected:
                disconnected = True
                cancelled.set()
                emit('client_disconnect', 'observed')
            return message

        async def observed_send(message):
            nonlocal finished, status
            await send(message)
            if message['type'] == 'http.response.start':
                status = message['status']
                emit('response_headers', 'sent', status=status)
            elif message['type'] == 'http.response.body' and not message.get('more_body', False):
                finished = True

        outcome = 'incomplete'
        emit('request', 'start')
        try:
            with cancellable_research() as cancelled:
                await self.app(scope, observed_receive, observed_send)
            outcome = 'disconnected' if disconnected else 'complete' if finished else 'incomplete'
        except BaseException as error:
            outcome = 'cancelled' if isinstance(error, asyncio.CancelledError) else 'error'
            raise
        finally:
            emit('request', 'end', outcome=outcome, status=status)
            with _lock:
                _counts['request'] -= 1
            _trace.reset(token)
