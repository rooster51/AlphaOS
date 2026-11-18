"""Deterministic quote-supported paper simulation; never submits orders.

Inputs are trusted-adapter records, not authenticated market data. No candle
pricing, midpoint fills, interpolation, assignment or overnight continuation.
"""
from dataclasses import dataclass, asdict
from copy import deepcopy
from datetime import date, timedelta
from math import isfinite
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from modules.options_archive import timestamp
from modules.premium_engine import analyze

NY = ZoneInfo('America/New_York')
MODES = ('historical_backtest', 'forward_paper', 'scenario_analysis', 'hypothetical_example')


@dataclass(frozen=True)
class Policy:
    capital: float = 100
    min_credit: float = 20
    max_credit_loss: float = 80
    max_debit: float = 50
    fee_per_contract: float = .65
    slippage_per_contract: float = .01  # dollars per share, each side
    max_quote_age_seconds: float = 30
    max_spread: float = .10
    profit_target: float = 10  # net dollars, complete position
    stop_loss: float = 20
    close_buffer_minutes: float = 5

    def __post_init__(self):
        for value in self.__dict__.values():
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError('Policy values must be finite and nonnegative.')
        if min(self.capital, self.max_quote_age_seconds, self.profit_target,
               self.stop_loss, self.close_buffer_minutes) <= 0:
            raise ValueError('Positive capital, freshness, exits and close buffer required.')


@dataclass(frozen=True)
class Strategy:
    """Common signed-leg interface; family labels do not change payoff math.

    Legs: contract (OSI), type (Call/Put), strike, qty (signed whole contracts).
    Supports long options, verticals, butterflies, condors and ratio structures.
    Stock-backed and unbounded structures explicitly fail eligibility.
    """
    symbol: str
    family: str
    expiration: str
    legs: tuple
    shares: int = 0


def _number(value):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError('invalid_numeric_data')
    return value


def _legs(strategy):
    if strategy.symbol not in ('SPY', 'QQQ') or not strategy.family or strategy.shares:
        raise ValueError('unsupported_symbol_or_stock_backing')
    if not strategy.legs:
        raise ValueError('missing_legs')
    seen = set()
    for leg in strategy.legs:
        k, q = _number(leg['strike']), _number(leg['qty'])
        if k <= 0 or q == 0 or int(q) != q or leg['type'] not in ('Call', 'Put'):
            raise ValueError('invalid_leg')
        contract = f"{strategy.symbol}{date.fromisoformat(strategy.expiration):%y%m%d}{leg['type'][0]}{round(k * 1000):08d}"
        if leg['contract'].replace(' ', '') != contract or contract in seen:
            raise ValueError('contract_identity_mismatch')
        seen.add(contract)


def _fill(strategy, frame, policy, opening, mode):
    """Natural-side prices with adverse slippage and verified displayed size.

    source/ref and evidence_kind must be supplied by a trusted archive adapter.
    Collection time cannot substitute for either market-side timestamp.
    """
    at = timestamp(frame['at'])
    rows = frame['quotes']
    if len({r['contract'] for r in rows}) != len(rows):
        raise ValueError('duplicate_quote')
    indexed = {r['contract']: r for r in rows}
    cash = 0.
    evidence = []
    for leg in strategy.legs:
        row = indexed.get(leg['contract'])
        if row is None:
            raise ValueError('missing_leg_quote')
        if (not row.get('source') or not row.get('source_ref') or row.get('rejection_reasons')
                or row.get('quote_outcome') != 'SUCCESS'):
            raise ValueError('unverified_provenance')
        expected = 'observed_option_quote' if mode in MODES[:2] else 'synthetic_option_quote'
        if row.get('evidence_kind') != expected:
            raise ValueError('evidence_mode_mismatch')
        for field in ('bid_timestamp', 'ask_timestamp', 'observed_at'):
            stamp = timestamp(row[field])
            if (stamp.astimezone(NY).date() != at.astimezone(NY).date()
                    or not 0 <= (at-stamp).total_seconds() <= policy.max_quote_age_seconds):
                raise ValueError('stale_future_or_wrong_session_quote')
        bid, ask = _number(row['bid']), _number(row['ask'])
        if bid <= 0 or ask < bid or ask-bid > policy.max_spread:
            raise ValueError('unverified_liquidity')
        signed_qty = leg['qty'] if opening else -leg['qty']
        side = 'ask' if signed_qty > 0 else 'bid'
        size = _number(row[side + '_size'])
        if size < abs(signed_qty) or size != int(size):
            raise ValueError('insufficient_displayed_size')
        price = row[side] + (policy.slippage_per_contract if signed_qty > 0 else -policy.slippage_per_contract)
        if price < 0:
            raise ValueError('invalid_slippage_price')
        cash -= signed_qty * price * 100
        evidence.append(dict(contract=leg['contract'], qty=signed_qty, price=price,
                             quote=deepcopy(row)))
    count = sum(abs(l['qty']) for l in strategy.legs)
    return dict(at=at.isoformat(), cash=cash, fees=count*policy.fee_per_contract,
                slippage=count*policy.slippage_per_contract*100, legs=evidence)


@lru_cache(maxsize=256)
def _session(day):
    schedule = mcal.get_calendar('NYSE').schedule(start_date=day, end_date=day)
    if schedule.empty:
        raise ValueError('not_exchange_session')
    return (schedule.iloc[0]['market_open'].to_pydatetime(),
            schedule.iloc[0]['market_close'].to_pydatetime())


def simulate(strategy, frames, *, mode, policy=Policy()):
    """Replay one proposed position. First frame is the requested entry.

    Historical replay admits an entry only when a complete closing path exists.
    An unfillable mandatory exit invalidates the run: retains attempted events,
    reports no_trade and no realized P&L, never fabricates a close. For forward
    mode this is an unresolved exposure requiring action, not a cancelled fill.
    """
    result = dict(version='intraday-paper-v1', mode=mode, symbol=strategy.symbol,
                  strategy=strategy.family, policy=asdict(policy), status='no_trade', reason=None,
                  entry=None, exit=None, marks=[], net_pnl=None, maximum_loss=None,
                  fill_model='simulated natural bid/ask with adverse slippage')
    try:
        strategy = deepcopy(strategy)
        frames = deepcopy(frames)
        if mode not in MODES:
            raise ValueError('invalid_evidence_mode')
        _legs(strategy)
        times = [timestamp(f['at']) for f in frames]
        if not times or any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError('missing_or_unordered_frames')
        day = times[0].astimezone(NY).date()
        if not 0 <= (date.fromisoformat(strategy.expiration)-day).days <= 7:
            raise ValueError('outside_0_7_dte')
        opened, closed = _session(day)
        deadline = closed-timedelta(minutes=policy.close_buffer_minutes)
        result['close_deadline'] = deadline.isoformat()
        if not opened <= times[0] < deadline:
            raise ValueError('entry_outside_session')
        entry = _fill(strategy, frames[0], policy, True, mode)
        count = sum(abs(l['qty']) for l in strategy.legs)
        round_fees = 2 * count * policy.fee_per_contract
        reserve = count * policy.slippage_per_contract * 100
        risk = analyze(strategy.legs, entry['cash']/100, 1, 0, None,
                       fees=round_fees + reserve)['max_loss']
        if not isfinite(risk) or risk > policy.capital:
            raise ValueError('unbounded_or_insufficient_capital')
        if entry['cash'] > 0:
            if entry['cash']-round_fees-reserve < policy.min_credit or risk > policy.max_credit_loss:
                raise ValueError('credit_economics_failed')
        elif -entry['cash']+round_fees+reserve > policy.max_debit:
            raise ValueError('debit_economics_failed')
        result.update(entry=entry, maximum_loss=risk)
        for frame, at in zip(frames[1:], times[1:]):
            if at >= closed or at.astimezone(NY).date() != day:
                break
            try:
                exit_fill = _fill(strategy, frame, policy, False, mode)
            except (KeyError, TypeError, ValueError) as exc:
                result['marks'].append(dict(at=at.isoformat(), pnl=None, reason=str(exc)))
                continue
            pnl = entry['cash']+exit_fill['cash']-entry['fees']-exit_fill['fees']
            result['marks'].append(dict(at=at.isoformat(), pnl=pnl, liquidation=exit_fill))
            reason = ('mandatory_same_day_exit' if at >= deadline else
                      'profit_target' if pnl >= policy.profit_target else
                      'stop_loss' if pnl <= -policy.stop_loss else None)
            if reason:
                result.update(status='closed', reason=reason, exit=exit_fill, net_pnl=pnl)
                return result
        raise ValueError('unfillable_same_day_exit')
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        result['reason'] = str(exc)
        if result['entry'] is not None and mode == 'forward_paper':
            result['status'] = 'unresolved_exposure'
        return result


def summarize(results):
    """Closed-trade metrics; unresolved groups suppress aggregate performance.

    Drawdown is chronological realized equity drawdown, not portfolio MTM.
    Never pool evidence modes. Sample size counts closed trades, not quotes.
    """
    groups = {}
    for r in results:
        key = (r['mode'], r['strategy'], r['symbol'])
        groups.setdefault(key, []).append(r)
    output = []
    for (mode, strategy, symbol), rows in sorted(groups.items()):
        trades = sorted((r for r in rows if r['status'] == 'closed'), key=lambda r: timestamp(r['exit']['at']))
        values = [r['net_pnl'] for r in trades]
        wins, losses = [p for p in values if p > 0], [p for p in values if p < 0]
        equity = peak = drawdown = 0.
        for pnl in values:
            equity += pnl
            peak = max(peak, equity)
            drawdown = max(drawdown, peak-equity)
        unresolved = sum(r['entry'] is not None and r['status'] != 'closed' for r in rows)
        valid = bool(values) and not unresolved
        output.append(dict(mode=mode, strategy=strategy, symbol=symbol, sample_size=len(values),
            no_trade_count=sum(r['status'] == 'no_trade' for r in rows), unresolved_count=unresolved,
            net_pnl=sum(values) if valid else None, expectancy=sum(values)/len(values) if valid else None,
            win_rate=len(wins)/len(values) if valid else None,
            average_win=sum(wins)/len(wins) if wins and valid else None,
            average_loss=sum(losses)/len(losses) if losses and valid else None,
            drawdown=drawdown if valid else None,
            profit_factor=sum(wins)/-sum(losses) if losses and valid else None))
    return output
