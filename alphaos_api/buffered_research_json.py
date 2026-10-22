"""Buffer full research JSON without retaining a second candidate object graph.

No bytes are emitted until all sanitization and encoding succeeds. Fragments
contain only bytes produced by the existing safe encoder, never caller bytes.
"""
import orjson


def encode_research_response(value, *, sanitize, encode):
    if not (isinstance(value, dict) and value.get('schema_version') == 'alphaos-interface-v2'
            and isinstance(value.get('research'), dict)
            and isinstance(value['research'].get('research_session'), dict)):
        return encode(sanitize(value))
    session = value['research']['research_session']
    arrays = {key: session[key] for key in ('candidates', 'excluded')
              if isinstance(session.get(key), list)}
    if not arrays:
        return encode(sanitize(value))
    # The header keeps original insertion order and every response field.
    projected_session = dict(session)
    projected_session.update({key: [] for key in arrays})
    projected = dict(value, research=dict(value['research'], research_session=projected_session))
    # First sanitize the root header so the existing sanitizer snapshots its
    # own complete secret/key policy and root nonfinite-number semantics once.
    state = {}
    cleaned = sanitize(projected, _state=state, _release=True)
    for key, entries in arrays.items():
        chunks = []
        for entry in entries:
            # Shared observations within an entry retain existing list memoization.
            # Only primitive key/string policy is reused between entries.
            chunks.append(encode(sanitize(entry, _state=state, _release=True)))
        cleaned['research']['research_session'][key] = orjson.Fragment(b'[' + b','.join(chunks) + b']')
    try:
        return encode(cleaned)
    except TypeError:
        # A legacy integer outside native encoder range can require the standard
        # JSON fallback, which does not understand internal Fragment values.
        return encode(sanitize(value))
