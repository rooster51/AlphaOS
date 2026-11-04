"""Read-only integrity audit for archived market candles.

Supabase ``market_candles`` stores one row per provider/symbol/aggregation and
exact ``bar_time``. Because the unique key is the exact timestamp rather than the
minute bucket, two observations of the same minute with different seconds can
both persist. Duplicate minute buckets have been observed in this archive.

This module never rewrites, deduplicates, deletes or "repairs" raw rows. It groups
raw observations into UTC minute buckets, classifies them, preserves every raw
row in its report, and exposes only buckets that are safe to treat as validated
bars.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from math import isfinite

SCHEMA_VERSION = "candle-integrity-v1"
PRICE_FIELDS = ("open", "high", "low", "close")
VALUE_FIELDS = PRICE_FIELDS + ("volume",)

CAVEATS = (
    "Raw rows are reported unchanged; this audit never rewrites or deletes archive data.",
    "Bars are grouped into UTC minute buckets because the stored unique key is the exact timestamp.",
    "Identical duplicate observations are reported separately from conflicting duplicates.",
    "Conflicting buckets are never treated as validated bars.",
    "Gap statistics compare validated buckets only and do not establish missing bars: "
    "session boundaries, halts and holidays are not modelled here.",
    "A validated bar is an integrity check, not an executable quote or a licensed market-data feed.",
)


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _utc_minute(value):
    """Return the UTC minute bucket for an aware timestamp, else None."""
    if isinstance(value, datetime):
        observed = value
    elif isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            observed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None
    if observed.tzinfo is None:
        return None
    return observed.astimezone(timezone.utc).replace(second=0, microsecond=0)


def _identity(row):
    if not isinstance(row, dict):
        return None
    provider, symbol, aggregation = (row.get("provider"), row.get("symbol"), row.get("aggregation"))
    if not all(isinstance(value, str) and value.strip() for value in (provider, symbol, aggregation)):
        return None
    return provider, symbol, aggregation


def _validated_bar(row):
    """Return (bar, None) for a complete, internally consistent OHLCV row."""
    values = {field: _finite(row.get(field)) for field in VALUE_FIELDS}
    for field in PRICE_FIELDS:
        if values[field] is None or values[field] <= 0:
            return None, "missing_or_invalid_price"
    volume = values["volume"]
    if volume is not None and volume < 0:
        return None, "negative_volume"
    open_, high, low, close = (values[field] for field in PRICE_FIELDS)
    if high < low:
        return None, "high_below_low"
    if high < max(open_, close) or low > min(open_, close):
        return None, "range_inconsistent"
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, None


def _iso(minute):
    return minute.isoformat().replace("+00:00", "Z")


def audit_candle_rows(rows):
    """Audit raw candle rows without mutating them.

    ``rows`` is any sequence of mapping-like records as returned by the archive.
    The report keeps every raw observation, so normalization is additive and
    auditable rather than destructive.
    """
    if not isinstance(rows, (list, tuple)):
        raise TypeError("rows must be a sequence of candle records")

    buckets = {}
    invalid_rows = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            invalid_rows.append({"index": index, "reason": "row_not_object", "raw": row})
            continue
        identity = _identity(row)
        minute = _utc_minute(row.get("bar_time"))
        if minute is None:
            invalid_rows.append({
                "index": index,
                "reason": "invalid_or_naive_timestamp",
                "raw": row,
            })
            continue
        bar, reason = _validated_bar(row)
        if reason is not None:
            invalid_rows.append({"index": index, "reason": reason, "raw": row})
            continue
        if identity is None:
            invalid_rows.append({"index": index, "reason": "invalid_identity", "raw": row})
            continue
        key = identity + (minute,)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = buckets[key] = {
                "provider": identity[0],
                "symbol": identity[1],
                "aggregation": identity[2],
                "bar_time": _iso(minute),
                "minute": minute,
                "observations": [],
            }
        bucket["observations"].append({"index": index, "bar": bar, "raw": row})

    report_buckets = []
    validated_by_series = {}
    identical_duplicate_bucket_count = 0
    conflicting_bucket_count = 0
    duplicate_bucket_count = 0

    for bucket in buckets.values():
        observations = bucket["observations"]
        first = observations[0]["bar"]
        if len(observations) > 1:
            duplicate_bucket_count += 1
            identical = all(entry["bar"] == first for entry in observations[1:])
            if identical:
                identical_duplicate_bucket_count += 1
                state = "duplicate_identical"
            else:
                conflicting_bucket_count += 1
                state = "duplicate_conflicting"
        else:
            state = "validated"

        validated = state == "validated" or state == "duplicate_identical"
        entry = {
            "provider": bucket["provider"],
            "symbol": bucket["symbol"],
            "aggregation": bucket["aggregation"],
            "bar_time": bucket["bar_time"],
            "state": state,
            "observation_count": len(observations),
            "bar": first if validated else None,
            "observations": observations,
        }
        report_buckets.append(entry)
        if validated:
            series = (bucket["symbol"], bucket["aggregation"])
            validated_by_series.setdefault(series, []).append((bucket["minute"], first))

    gaps = {}
    for (symbol, aggregation), entries in sorted(validated_by_series.items()):
        entries.sort(key=lambda item: item[0])
        largest_gap = 0
        for previous, current in zip(entries, entries[1:]):
            gap = int((current[0] - previous[0]).total_seconds())
            largest_gap = max(largest_gap, gap)
        gaps.setdefault(symbol, {})[aggregation] = {
            "validated_bucket_count": len(entries),
            "largest_gap_seconds": largest_gap,
        }

    report_buckets.sort(key=lambda item: (
        item["symbol"], item["aggregation"], item["bar_time"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "raw_row_count": len(rows),
        "bucket_count": len(report_buckets),
        "validated_bar_count": sum(
            1 for bucket in report_buckets if bucket["bar"] is not None),
        "duplicate_bucket_count": duplicate_bucket_count,
        "identical_duplicate_bucket_count": identical_duplicate_bucket_count,
        "conflicting_bucket_count": conflicting_bucket_count,
        "invalid_row_count": len(invalid_rows),
        "buckets": report_buckets,
        "invalid_rows": invalid_rows,
        "gaps": gaps,
        "caveats": list(CAVEATS),
    }


def validated_bars(report):
    """Return only validated bars from a report (raw rows stay in the report)."""
    bars = []
    for bucket in report.get("buckets", []):
        bar = bucket.get("bar")
        if bar is None:
            continue
        bars.append({
            "provider": bucket["provider"],
            "symbol": bucket["symbol"],
            "aggregation": bucket["aggregation"],
            "bar_time": bucket["bar_time"],
            **bar,
        })
    return bars


def summarize_report(report):
    """Safe, low-volume report summary for logs; no raw observations."""
    return {
        "schema_version": report.get("schema_version"),
        "raw_row_count": report.get("raw_row_count"),
        "bucket_count": report.get("bucket_count"),
        "validated_bar_count": report.get("validated_bar_count"),
        "duplicate_bucket_count": report.get("duplicate_bucket_count"),
        "identical_duplicate_bucket_count": report.get("identical_duplicate_bucket_count"),
        "conflicting_bucket_count": report.get("conflicting_bucket_count"),
        "invalid_row_count": report.get("invalid_row_count"),
        "invalid_reasons": sorted({
            item.get("reason") for item in report.get("invalid_rows", [])
        }),
        "gaps": report.get("gaps"),
        "caveats": report.get("caveats"),
    }
