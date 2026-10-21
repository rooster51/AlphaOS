"""Read-only, bounded SPY/QQQ Public audit. No archive writes or raw errors.

Uses existing environment credentials. Reports observations, not entitlements,
executable quotes or investment recommendations. Never sends trading requests.
"""
import json
from modules.daily_public import DailyPublicProvider
from modules.intraday_archive import collect_symbol, load_config
from modules.expiration_coverage import archive_coverage


def main():
    try:
        provider = DailyPublicProvider.from_environment()
    except Exception:
        print(json.dumps(dict(status='unavailable',reason='provider_authentication_or_configuration_unavailable')))
        return 1
    config = load_config()
    for symbol in ('SPY','QQQ'):
        try:
            payload = collect_symbol(provider,symbol,config)
            options = payload['options']
            rows = options['valid_contracts']+options['questionable_contracts']
            print(json.dumps(dict(symbol=symbol,observed_at=payload['observed_at'],
                provider='Public',status=options['status'],
                discovery=options['expiration_discovery'],coverage=archive_coverage(options,payload['session']),
                strike_band=config['strike_band'],excluded_strikes=options['excluded_strike_count'],
                received_contract_count=options['received_contract_count'],
                retained_strike_min=min((r['strike'] for r in rows),default=None),
                retained_strike_max=max((r['strike'] for r in rows),default=None),
                missing_bid_timestamps=sum(r['bid_timestamp'] is None for r in rows),
                missing_ask_timestamps=sum(r['ask_timestamp'] is None for r in rows),
                expiration_failures=options['expiration_failures'],rejections=options['rejection_counts'],
                caveat='Read-only observations; no subscription changes or entitlement guarantees. Quote timestamps remain distinct from collection time.')))
        except Exception:
            print(json.dumps(dict(symbol=symbol,status='unavailable',reason='provider_or_calendar_evidence_unavailable')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
