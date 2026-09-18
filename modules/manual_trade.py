"""Validated manual, single-expiration trade input; never places orders."""
from datetime import date
from math import isfinite
import re

from modules.premium_engine import analyze


def build_manual_trade(symbol, expiration, spot, rows, shares=0, stock_basis=0, fees=0, iv=.25, as_of=None):
    as_of = as_of or date.today()
    symbol = str(symbol).strip().upper()
    if not re.fullmatch(r'[A-Z0-9.^/-]{1,20}',symbol):
        raise ValueError('Enter a valid underlying symbol.')
    if expiration < as_of:
        raise ValueError('Expiration must be today or later.')
    if not all(isfinite(float(x)) for x in (spot,shares,stock_basis,fees,iv)) or spot <= 0 or fees < 0 or stock_basis < 0 or iv <= 0:
        raise ValueError('Use finite, valid prices, fees, shares, and volatility.')
    if shares != int(shares) or (shares and stock_basis <= 0):
        raise ValueError('Shares must be whole numbers; stock positions need a positive entry price.')
    if not 1 <= len(rows) <= 12:
        raise ValueError('Enter between 1 and 12 option legs with the same expiration.')
    legs, credit = [], 0.
    for i,row in enumerate(rows,1):
        try:
            action, kind = row['Action'], row['Type']
            qty, strike, entry = (float(row[k]) for k in ('Contracts','Strike','Entry premium'))
        except (KeyError,ValueError,TypeError):
            raise ValueError(f'Complete all fields for leg {i}.') from None
        if action not in ('Buy','Sell') or kind not in ('Call','Put') or not all(isfinite(x) for x in (qty,strike,entry)) or qty <= 0 or qty != int(qty) or strike <= 0 or entry < 0:
            raise ValueError(f'Leg {i}: choose Buy/Sell, Call/Put, positive whole contracts, positive strike, and nonnegative premium.')
        signed = int(qty) * (1 if action == 'Buy' else -1)
        legs.append(dict(type=kind,strike=strike,qty=signed,entry_premium=entry))
        credit -= signed*entry
    dte = (expiration-as_of).days
    # Incorporate stock P&L already accrued between entry basis and current spot.
    adjusted_credit = credit + shares*(spot-stock_basis)/100
    stats = analyze(legs,adjusted_credit,spot,max(dte,.25)/365,iv,shares,fees)
    if dte == 0:
        stats['pop'] = None
    return dict(symbol=symbol,strategy='Manual trade',expiration=expiration.isoformat(),spot=spot,
                stock_basis=stock_basis,shares=int(shares),fees=fees,credit=credit,legs=legs,
                source='Manual entry',iv=iv,dte=dte,**stats)


def manual_trade_form():
    import pandas as pd
    import streamlit as st
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo('America/New_York')).date()
    st.caption('Enter one underlying and one shared expiration. Premiums are per share ($1.50 = $150 per standard contract). Positions persist for this browser session; export to keep a copy. Multi-expiration trades require a different valuation model.')
    with st.form('manual_option_trade'):
        a,b,c = st.columns(3)
        symbol = a.text_input('Trade underlying',value='SPY')
        spot = b.number_input('Current underlying price ($)',min_value=.01,value=500.)
        expiry = c.date_input('Shared option expiration',value=today+timedelta(days=30),min_value=today)
        legs = st.data_editor(pd.DataFrame([
            {'Action':'Sell','Type':'Put','Contracts':1,'Strike':490.,'Entry premium':3.},
            {'Action':'Buy','Type':'Put','Contracts':1,'Strike':485.,'Entry premium':2.}]),
            num_rows='dynamic',hide_index=True,use_container_width=True,key='manual_trade_legs',
            column_config={'Action':st.column_config.SelectboxColumn(options=['Buy','Sell'],required=True),
                           'Type':st.column_config.SelectboxColumn(options=['Call','Put'],required=True),
                           'Contracts':st.column_config.NumberColumn(min_value=1,step=1,required=True),
                           'Strike':st.column_config.NumberColumn(min_value=.01,required=True),
                           'Entry premium':st.column_config.NumberColumn(min_value=0.,required=True)})
        a,b,c,d = st.columns(4)
        shares = a.number_input('Signed shares (optional)',value=0,step=1,help='Positive for long shares, negative for short shares.')
        basis = b.number_input('Stock entry price ($)',min_value=0.,value=0.)
        fees = c.number_input('Total entry fees ($)',min_value=0.,value=0.)
        iv = d.number_input('Model volatility (%)',min_value=1.,max_value=500.,value=25.)
        submitted = st.form_submit_button('Analyze my trade',type='primary')
    if submitted:
        try:
            st.session_state['quant_manual_option'] = build_manual_trade(symbol,expiry,spot,legs.to_dict('records'),shares,basis,fees,iv/100,today)
        except ValueError as exc:
            st.session_state.pop('quant_manual_option',None)
            st.error(str(exc))
    selected = st.session_state.get('quant_manual_option')
    if selected:
        st.caption('Results reflect the last submitted manual trade. Click Analyze my trade after editing.')
    return selected
