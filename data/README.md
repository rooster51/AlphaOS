# Daily archive

Live snapshots begin with the first successful configured daily workflow run.
This directory contains no fabricated research or option history.

- `daily_quant/YYYY-MM-DD.json`: immutable underlying research.
- `options/YYYY-MM-DD/{SPY,QQQ}.json.gz`: separate observable option chains.
- `archive_manifest.json`: rebuildable inventory; artifact files are authoritative.

See [setup, credentials, schema and recovery](../docs/daily_quant_schema.md).
