"""Bounded bcrypt work for the trusted website Worker; no credential persistence/logs."""
import json
import re
from threading import BoundedSemaphore

import bcrypt
from fastapi import Request
from starlette.concurrency import run_in_threadpool

from .contracts import APIError

_slots = BoundedSemaphore(2)
_hash = re.compile(r'\$2[aby]\$12\$[./A-Za-z0-9]{53}')


def _verify(password: bytes, password_hash: bytes) -> bool:
    if not _slots.acquire(blocking=False):
        raise APIError('authentication_busy', 503)
    try:
        return bcrypt.checkpw(password, password_hash)
    except ValueError:
        raise APIError('invalid_request', 422) from None
    finally:
        _slots.release()


async def verify_website_password(request: Request):
    # Router authentication runs first. Never use query parameters or models that
    # could include plaintext credentials in validation/exception representations.
    if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
        raise APIError('invalid_request', 422)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 2048:
            raise APIError('request_too_large', 413)
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        payload = json.loads(data, object_pairs_hook=unique)
        if not isinstance(payload, dict) or set(payload) != {'password', 'password_hash'}:
            raise ValueError()
        password, password_hash = payload['password'], payload['password_hash']
        if not isinstance(password, str) or not isinstance(password_hash, str):
            raise ValueError()
        encoded = password.encode('utf-8')
        if not 1 <= len(encoded) <= 72 or not _hash.fullmatch(password_hash):
            raise ValueError()
    except (ValueError, TypeError, UnicodeError):
        raise APIError('invalid_request', 422) from None
    return {'verified': await run_in_threadpool(_verify, encoded, password_hash.encode('ascii'))}
