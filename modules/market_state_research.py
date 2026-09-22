"""Provider orchestration and auditable exports, separate from calculations."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json

from modules.market_state import VERSION, CONVENTIONS, validate_ohlc, market_state_features
from modules.market_outcomes import OUTCOME_CONVENTIONS, forward_outcomes


def build_research_dataset(history, completed_before, metadata=None, expected_sessions=None):
    clean,audit = validate_ohlc(history,completed_before,expected_sessions)
    features = market_state_features(clean,completed_before,expected_sessions)
    outcomes = forward_outcomes(clean,completed_before,expected_sessions)
    meta = dict(metadata or {})
    meta.update(version=VERSION,symbol=clean.symbol.iloc[0],start=str(clean.date.iloc[0].date()),
        end=str(clean.date.iloc[-1].date()),observations=len(clean),audit=audit,
        source_ohlc_sha256=hashlib.sha256(clean.to_csv(index=False).encode()).hexdigest(),
        feature_conventions=CONVENTIONS,outcome_conventions=OUTCOME_CONVENTIONS)
    return dict(features=features,outcomes=outcomes,metadata=meta)


def load_market_state(symbol, period):
    if symbol not in ('SPY','QQQ') or period not in ('FIVE_YEARS','TEN_YEARS'):
        raise ValueError('Select SPY/QQQ and FIVE_YEARS/TEN_YEARS.')
    from modules.public_data import get_public_research_bars
    from modules.history_diagnostics import HistoryError, history_diagnostics
    try:
        history = get_public_research_bars(symbol,period).copy()
    except HistoryError:
        raise
    except Exception:
        raise HistoryError('Public history could not be loaded; verify provider access.',history_diagnostics(symbol,period)) from None
    history['symbol'] = symbol
    now = datetime.now(ZoneInfo('America/New_York'))
    try:
        return build_research_dataset(history,now.date(),dict(source='Public regular-market ONE_DAY OHLC',
        requested_period=period,data_read_at=now.isoformat(),provider_diagnostics=history.attrs.get('provider_diagnostics',{}),
        retrieval_note='Read from existing Public adapter with up to 300-second cache. Exact upstream retrieval timestamp is unavailable.',
        completion_policy='Conservatively exclude all bars dated today or later in America/New_York, even after close; daily timestamps use UTC calendar date.'))
    except ValueError as exc:
        diagnostic = history_diagnostics(symbol,period,history)
        diagnostic['stage'] = 'ohlc_validation_or_features'
        raise HistoryError(str(exc),diagnostic) from None


def export_csv(dataset, kind):
    if kind not in ('features','outcomes'):
        raise ValueError('Export features or outcomes separately.')
    frame = dataset[kind].copy()
    # Self-contained metadata in every CSV, without joining labels to predictors.
    frame['metadata_kind'] = 'available_at_T' if kind=='features' else 'future_research_only'
    frame['metadata_json'] = json.dumps(dataset['metadata'],sort_keys=True,allow_nan=False)
    return frame.to_csv(index=False)
