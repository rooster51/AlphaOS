import io
import json
import hashlib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.quant_engine import (validate_prices, demo_prices, metrics, weights, apply_costs,
                                  walk_forward, bootstrap, risk_contributions, benchmark_regression)
from modules.ui import configure_page


def chart(frame, title, percent=False):
    fig = go.Figure()
    for column in frame:
        fig.add_trace(go.Scatter(x=frame.index, y=frame[column], name=str(column), mode="lines"))
    fig.update_layout(title=title, template="plotly_dark", height=370, margin=dict(l=20,r=20,t=50,b=20),
                      paper_bgcolor="#0b111c", plot_bgcolor="#0b111c", legend=dict(orientation="h"))
    if percent:
        fig.update_yaxes(tickformat=".1%")
    st.plotly_chart(fig, use_container_width=True)


def render():
    configure_page("AlphaOS | Quant Research")
    st.markdown("""<style>.stApp{background:#0b111c}.block-container{max-width:1480px}
    [data-testid="stMetric"]{background:#121e2e;border:1px solid #23344b;padding:16px;border-radius:12px}
    h1{letter-spacing:-1.5px}</style>""", unsafe_allow_html=True)
    st.caption("ALPHAOS / QUANTITATIVE RESEARCH")
    st.title("Test the edge. Measure the risk.")
    st.write("A reproducible workbench for portfolio construction, chronological validation, and tail-risk analysis.")
    research, option_tab, pulse, methods, market_state = st.tabs(["Portfolio research", "Options stress lab", "Pulse research", "Methodology", "Market State Research"])
    with market_state:
        from modules.market_state_workspace import render_market_state
        render_market_state()
    with pulse:
        with st.expander("Open the original 30-minute Pulse laboratory"):
            from modules.pulse_workspace import render_pulse
            render_pulse()
    with methods:
        st.markdown("""### Research conventions
* Daily, aligned observations. Public mode uses provider closes with unverified split/dividend adjustment: price-return research, not total-return performance. CSV inputs must already account for corporate actions. No automatic filling of missing values. Public mode excludes today's potentially incomplete bar and intersects asset dates. Current asset lists may carry survivorship bias.
* Long-only portfolios, no leverage, daily rebalancing, zero cash yield. Signals use a full extra bar: information at close t−2 determines exposure from close t−1 to close t. Costs apply to absolute traded weight, including drift and the first investment, in basis points per side. No final liquidation is assumed.
* CAGR and volatility use 252 observations/year. Sharpe uses sample standard deviation and a user-supplied risk-free hurdle; cash holdings do not earn that hurdle. Sortino uses root mean squared negative excess daily returns. Drawdown includes initial capital.
* Walk-forward selects among 20/60/120-day momentum models using trailing training Sharpe, then evaluates the chosen model on the next untouched test block. Test blocks never overlap. The full-sample strategy and allocation diagnostics are descriptive, not out-of-sample evidence. Repeated experimentation can still overfit the test history.
* Historical VaR is the 95th percentile of daily losses; expected shortfall is the average loss at or beyond that threshold. Negative values indicate gains even in that tail. These are empirical measures, not regulatory capital calculations.
* Bootstrap samples contiguous blocks with replacement using a fixed seed. It preserves short-run dependence within blocks, assumes the observed history is representative, and cannot model unseen crashes.
* Allocation diagnostics use covariance shrunk 20% toward its diagonal. Inverse-volatility weighting is not full risk parity. OLS benchmark alpha/beta is descriptive, without a significance claim or causal interpretation.
* Options stress uses the selected opportunity's exact terminal payoff, not a historical options backtest. No option-chain history, volatility-surface calibration, American exercise model, or intraday execution simulator is available.

Reference: [chronological validation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) · [BIS risk terminology](https://www.bis.org/basel_framework/chapter/MAR/10.htm?inforce=20230101&published=20200327&tldate=20040605)
""")
    with option_tab:
        input_mode = st.radio('Trade input', ['Selected opportunity','Enter my own trade'],horizontal=True)
        if input_mode == 'Enter my own trade':
            from modules.manual_trade import manual_trade_form
            selected = manual_trade_form()
        else:
            selected = st.session_state.get("quant_selected_option")
        if selected:
            from modules.options_payoff import validate_trade
            try:
                selected = validate_trade(selected)
            except ValueError as exc:
                st.error(str(exc))
                selected = None
        if not selected:
            if input_mode == 'Selected opportunity':
                st.info("Click a trade in the Strategy Selector opportunity table, then return here to stress that position.")
                st.page_link("pages/5_Strategy_Selector.py", label="Open opportunities")
        else:
            st.subheader(f"{selected['symbol']} · {selected['strategy']} · {selected['expiration']}")
            st.caption(f"Source: {selected['source']} · saved input snapshot, not a refreshed quote.")
            units = st.number_input("Strategy units", 1, 10000, 1)
            st.caption('Units multiply every option leg, share position, and entered fee together. Use 1 if the entered quantities already describe your whole position.')
            from modules.options_payoff_view import render_payoff_analysis
            render_payoff_analysis(selected, units)
            with st.expander('Existing model probability estimate'):
                pop = selected.get('pop')
                st.metric('Estimated expiration POP',f"{pop:.1%}" if isinstance(pop,(int,float)) and np.isfinite(pop) else 'Unavailable')
                st.caption('Existing constant-volatility model estimate, separate from the payoff map. Not a historical win rate or expected-value estimate. Same-day POP is unavailable.')
            st.dataframe(pd.DataFrame(selected['legs']),hide_index=True,use_container_width=True)
            if selected['source'] == 'Manual entry':
                st.write(f"**Net option premium:** {'credit' if selected['credit'] >= 0 else 'debit'} ${abs(selected['credit'])*100*units:,.2f} · **Entry fees:** ${selected['fees']*units:,.2f}")
                export = {k:selected.get(k) for k in ('symbol','expiration','spot','stock_basis','shares','fees','credit','legs','iv')}
                st.download_button('Export manual trade · JSON',json.dumps(export,indent=2,allow_nan=False),'manual-trade.json','application/json')
            if selected['source'].startswith('Public'):
                st.markdown("#### Provider Greek exposure")
                exposures = {}
                for greek in ('delta','gamma','theta','vega'):
                    available = all(isinstance(l.get(greek),(int,float)) and np.isfinite(l[greek]) for l in selected['legs'])
                    exposures[greek] = units * (sum(l['qty']*100*l[greek] for l in selected['legs']) + (selected['shares'] if greek == 'delta' else 0)) if available else None
                st.dataframe(pd.Series(exposures,name='Signed position exposure').to_frame(),use_container_width=True)
                st.caption("Standard 100-share multiplier. Delta: shares equivalent; gamma: delta change per $1 underlying move; vega: dollars per 1 percentage-point IV move. Theta retains the provider time convention. Missing Greeks remain unavailable.")
                with st.expander("Inspect Public option-contract history"):
                    st.caption("Fetch daily OHLCV for these specific contracts. This is not historical chain discovery or a bid/ask execution backtest; availability varies by contract.")
                    if st.button("Fetch selected contracts' history", disabled=not all(l.get('contract') for l in selected['legs'])):
                        from modules.public_data import get_public_research_bars
                        frames = []
                        for leg in selected['legs']:
                            try:
                                history = get_public_research_bars(leg['contract'],'MONTH',option=True)
                                history['contract'] = leg['contract']
                                frames.append(history)
                            except Exception as exc:
                                st.warning(f"History unavailable for {leg['contract']} ({type(exc).__name__}).")
                        st.session_state['public_contract_history'] = {'contracts':[l.get('contract') for l in selected['legs']], 'data':pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()}
                    saved = st.session_state.get('public_contract_history')
                    if saved and saved['contracts'] == [l.get('contract') for l in selected['legs']]:
                        if saved['data'].empty:
                            st.info("No contract history returned.")
                        else:
                            st.dataframe(saved['data'],hide_index=True,use_container_width=True)
                            st.download_button("Export contract history",saved['data'].to_csv(index=False),'public-contract-history.csv','text/csv')
    with research:
        with st.form("quant_run"):
            a,b,c = st.columns(3)
            source = a.selectbox("Research dataset", ["Public market history", "Synthetic demonstration", "Adjusted-close CSV"])
            model = b.selectbox("Portfolio model", ["Momentum", "Inverse volatility", "Equal weight"])
            capital = c.number_input("Starting NAV ($)", min_value=100.0, value=100000.0, step=10000.0)
            uploaded = st.file_uploader("Daily adjusted closes · date, ASSET_A, ASSET_B, …", type="csv")
            a,b = st.columns(2)
            public_symbols = a.multiselect("Public research symbols", ["SPY","QQQ","IWM","DIA","TLT","IEF","GLD"], default=["SPY","QQQ","TLT","GLD"])
            public_period = b.selectbox("Public history period", ["FIVE_YEARS","TEN_YEARS","YEAR"])
            st.caption("Public loads market history on submission (cached for five minutes). It does not import your brokerage holdings. Provider closes are not verified total-return prices.")
            a,b,c,d = st.columns(4)
            lookback = a.selectbox("Signal lookback", [20,60,120], index=1)
            cost = b.number_input("Trading cost (bps / side)", 0.0, 100.0, 5.0)
            rf = c.number_input("Risk-free hurdle (%)", 0.0, 20.0, 4.0)
            train = d.selectbox("Walk-forward training days", [126,252,504], index=1)
            a,b,c = st.columns(3)
            test = a.selectbox("Test block days", [21,63,126], index=1)
            block = b.selectbox("Bootstrap block days", [5,10,20], index=1)
            horizon = c.selectbox("Simulation horizon days", [63,126,252], index=2)
            submitted = st.form_submit_button("Run research →", type="primary", use_container_width=True)
        st.download_button("Download CSV template", demo_prices().head(600).rename_axis("date").to_csv(), "synthetic-adjusted-close-template.csv", "text/csv")
        if submitted:
            try:
                metadata = {}
                if source == "Public market history":
                    from modules.public_research import load_public_research
                    with st.spinner("Loading Public daily history and aligning completed sessions…"):
                        prices, metadata = load_public_research(public_symbols, public_period)
                    st.session_state['public_research_audit'] = metadata
                elif source == "Adjusted-close CSV":
                    if uploaded is None:
                        raise ValueError("Upload an adjusted-close CSV first.")
                    prices = validate_prices(pd.read_csv(io.BytesIO(uploaded.getvalue())))
                else:
                    prices = demo_prices()
                held = weights(prices, model, lookback)
                # Start after sufficient common warmup; enter the evaluated sample from cash.
                start = max(122, lookback+2)
                if len(prices)-start < 30:
                    raise ValueError("At least 152 observations are needed after common warmup.")
                held.iloc[:start] = 0
                ledger = apply_costs(prices, held, cost).iloc[start:]
                benchmark_weights = weights(prices, "Equal weight")
                benchmark_weights.iloc[:start] = 0
                benchmark = apply_costs(prices, benchmark_weights, cost).Net.iloc[start:]
                wf, folds, wf_weights = walk_forward(prices, train, test, cost, rf/100)
                simulations, drawdowns = bootstrap(wf.Net, horizon, 1000, block)
                config = dict(source=source, model=model, lookback=lookback, cost_bps=cost, rf=rf/100,
                              train=train, test=test, block=block, horizon=horizon, seed=51, paths=1000, capital=capital,
                              data_metadata=metadata)
                digest = hashlib.sha256(prices.to_csv().encode()).hexdigest()
                st.session_state["quant_run_result"] = dict(prices=prices, held=held, ledger=ledger, benchmark=benchmark,
                    wf=wf, folds=folds, simulations=simulations, drawdowns=drawdowns, config=config, digest=digest)
            except (ValueError, TypeError, pd.errors.ParserError) as exc:
                st.session_state.pop("quant_run_result", None)
                st.error(str(exc))
        audit = st.session_state.get('public_research_audit')
        if audit:
            with st.expander("Last successful Public data retrieval"):
                st.caption(f"{audit['retrieved_at']} · {audit['period']} · {audit['adjustment']}")
                st.dataframe(pd.DataFrame(audit['audit']),hide_index=True,use_container_width=True)
                if audit['quotes']:
                    st.dataframe(pd.DataFrame(audit['quotes']),hide_index=True,use_container_width=True)
        result = st.session_state.get("quant_run_result")
        if not result:
            st.info("Run research to generate a performance report, risk diagnostics, and out-of-sample tests.")
            return
        p, ledger, wf, cfg = result['prices'], result['ledger'], result['wf'], result['config']
        if cfg['source'].startswith("Synthetic"):
            st.warning("SYNTHETIC RESEARCH — all prices and performance in this report are illustrative.")
        elif cfg['source'] == 'Public market history':
            st.info("PUBLIC MARKET HISTORY — actual provider closes; strategy performance is simulated. Dividend/split adjustment is unverified, so results are price-return research rather than validated total returns.")
            st.caption(f"Retrieved {cfg['data_metadata']['retrieved_at']} · {cfg['data_metadata']['period']} · no synthetic fallback")
        st.caption(f"Last submitted run · {cfg['model']} · {len(p):,} observations · {p.index[0].date()} to {p.index[-1].date()} · dataset SHA256 {result['digest'][:16]}")
        stats = metrics(wf.Net, cfg['rf'])
        a,b,c,d = st.columns(4)
        a.metric("OOS CAGR", f"{stats['CAGR']:.1%}")
        b.metric("OOS Sharpe", f"{stats['Sharpe']:.2f}")
        c.metric("OOS max drawdown", f"{stats['Max drawdown']:.1%}")
        d.metric("OOS daily ES 95%", f"{stats['Daily ES 95%']:.2%}")
        st.caption("Headline metrics refer to the walk-forward momentum selector, independent of the full-sample portfolio model.")
        perf, risk, validation, allocation, simulation = st.tabs(["Performance", "Tail risk", "Walk-forward", "Allocation & factors", "Monte Carlo"])
        with perf:
            curves = pd.DataFrame({cfg['model']: (1+ledger.Net).cumprod(), "Equal-weight reference": (1+result['benchmark']).cumprod()}) * cfg['capital']
            chart(curves, "Full-sample NAV · after trading costs")
            st.dataframe(pd.DataFrame({"Portfolio": metrics(ledger.Net,cfg['rf']), "Reference": metrics(result['benchmark'],cfg['rf'])}).round(4), use_container_width=True)
            st.caption(f"Cumulative traded weight: {ledger.Turnover.sum():.2f} × NAV · Average invested exposure: {ledger.Exposure.mean():.1%}. Metrics table uses decimals for returns.")
            monthly = ledger.Net.resample("ME").apply(lambda x: (1+x).prod()-1)
            chart(monthly.to_frame("Net monthly return"), "Monthly returns", True)
        with risk:
            wealth = (1+wf.Net).cumprod()
            dd = wealth/wealth.cummax().clip(lower=1)-1
            chart(dd.to_frame("Drawdown"), "Out-of-sample underwater curve", True)
            rolling = wf.Net.rolling(63)
            chart(pd.DataFrame({"Annual volatility": rolling.std()*np.sqrt(252)}), "Rolling 63-day volatility", True)
            st.dataframe(wf.Net.nsmallest(10).rename("Worst daily return").to_frame(), use_container_width=True)
            fig = go.Figure(go.Histogram(x=wf.Net, nbinsx=50, marker_color="#61d8c1"))
            fig.update_layout(template="plotly_dark", title="OOS daily return distribution", height=300)
            st.plotly_chart(fig,use_container_width=True)
            st.caption(f"VaR 95%: {stats['Daily VaR 95%']:.2%}; ES 95%: {stats['Daily ES 95%']:.2%}. Tail estimates use {len(wf)} observations.")
        with validation:
            chart(((1+wf.Net).cumprod()*cfg['capital']).to_frame("Walk-forward NAV"), "Untouched test blocks · stitched chronologically")
            st.dataframe(result['folds'], hide_index=True, use_container_width=True)
            st.write("Only training Sharpe chooses each fold's model. Parameter changes apply on the next test block; transaction costs include switching exposure.")
            st.caption("No random train/test shuffle. These tests do not remove survivorship bias, data revisions, or overfitting from repeated manual experimentation.")
        with allocation:
            trailing = p.pct_change(fill_method=None).dropna().tail(cfg['train'])
            last = result['held'].iloc[-1]
            st.dataframe(risk_contributions(trailing, last),use_container_width=True)
            st.caption(f"Residual cash: {1-last.sum():.1%}. Latest holdings with trailing covariance; not an optimized or out-of-sample allocation recommendation.")
            corr = trailing.corr()
            fig = go.Figure(go.Heatmap(z=corr, x=corr.columns, y=corr.index, zmin=-1,zmax=1,colorscale="RdBu"))
            fig.update_layout(template="plotly_dark",title="Trailing asset correlation",height=350)
            st.plotly_chart(fig,use_container_width=True)
            st.dataframe(pd.Series(benchmark_regression(ledger.Net,result['benchmark'],cfg['rf']),name="Estimate").to_frame(),use_container_width=True)
        with simulation:
            paths = result['simulations']
            quantiles = np.quantile(paths,[.05,.25,.5,.75,.95],axis=0).T*cfg['capital']
            chart(pd.DataFrame(quantiles,columns=["5th","25th","Median","75th","95th"]), "Block-bootstrap NAV percentiles · trading days")
            a,b,c = st.columns(3)
            a.metric("Simulated loss frequency", f"{(paths[:,-1]<1).mean():.1%}")
            b.metric("5th percentile terminal NAV", f"${np.quantile(paths[:,-1],.05)*cfg['capital']:,.0f}")
            c.metric("5th percentile max drawdown",f"{np.quantile(result['drawdowns'],.05):.1%}")
            st.caption(f"{cfg['paths']:,} paths · {cfg['horizon']} days · {cfg['block']}-day blocks · seed {cfg['seed']}. Resampled net OOS returns; no guarantee of future performance.")
        report = {"config":cfg,"dataset_sha256":result['digest'],"oos_metrics":{k:float(v) if np.isfinite(v) else None for k,v in stats.items()}}
        st.download_button("Export research manifest · JSON",json.dumps(report,indent=2),"quant-research.json","application/json")
        st.download_button("Export OOS returns · CSV",wf.to_csv(),"quant-oos-returns.csv","text/csv")
        st.download_button("Export research prices · CSV",p.rename_axis('date').to_csv(),"quant-source-prices.csv","text/csv")
