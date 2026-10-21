"""Encode already-normalized, redacted values; never bypass the safety walk."""
import json
import orjson


def encode_json(value):
    try:
        return orjson.dumps(value)
    except TypeError:
        # Preserve arbitrary-size integer semantics on legacy endpoints.
        return json.dumps(value,ensure_ascii=False,allow_nan=False,
                          separators=(',',':')).encode('utf-8')
