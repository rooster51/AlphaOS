# AlphaOS intraday archive

This directory is reserved for immutable point-in-time market observations.

Initial universe: SPY and QQQ.

Each collection stores:
- the Public underlying quote and provider timestamps;
- available option expirations from 0 through 7 calendar DTE;
- contracts within 5% of observed spot;
- bid, ask, last, provider mid, volume, open interest, IV and Greeks when Public supplies them;
- collection/request timestamps and validation/quality metadata.

Snapshots are partitioned by symbol and New York session date:

`snapshots/symbol=QQQ/date=YYYY-MM-DD/HHMMSS.json.gz`

The archive stores observations, not recommendations or AlphaOS strategy output. Missing provider values are retained as missing and are never fabricated.

The first version intentionally uses compressed JSON so observations can be audited directly. A columnar/object-storage backend can be added behind the archive interface after collection reliability and volume are measured.
