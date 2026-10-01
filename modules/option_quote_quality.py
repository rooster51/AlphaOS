"""Option timestamp coverage; full-chain age is informational, not a selected-leg gate."""
from datetime import datetime
from modules.quote_freshness import normalize_timestamp


def option_quality(legs, now, retrieved_at=None, scope='consumed_contracts'):
    stamps=[];fresh=missing=future=0
    for leg in legs:
        values=[normalize_timestamp(leg.get(k)) for k in ('bid_timestamp','ask_timestamp')]
        ages=[(now-datetime.fromisoformat(v)).total_seconds() for v in values if v]
        stamps.extend(v for v in values if v)
        missing+=any(v is None for v in values)
        future+=any(a < -60 for a in ages)
        fresh+=len(ages)==2 and all(-60<=a<=900 for a in ages)
    newest=max(stamps) if stamps else None;oldest=min(stamps) if stamps else None
    return dict(scope=scope,retrieved_at=retrieved_at,evaluated_at=now.isoformat(),
        newest_option_quote_as_of=newest,oldest_option_quote_as_of=oldest,
        newest_age_seconds=(now-datetime.fromisoformat(newest)).total_seconds() if newest else None,
        oldest_age_seconds=(now-datetime.fromisoformat(oldest)).total_seconds() if oldest else None,
        contract_count=len(legs),fresh_contract_count=fresh,
        fresh_contract_percentage=100*fresh/len(legs) if legs else None,
        missing_timestamp_contract_count=missing,future_timestamp_contract_count=future,
        all_contracts_fresh=bool(legs) and fresh==len(legs),max_age_seconds=900,
        note='Both bid/ask observations must be within the existing 15-minute option warning threshold. Full-chain coverage does not determine selected-leg freshness; provider delay and executable fills are unverified.')
