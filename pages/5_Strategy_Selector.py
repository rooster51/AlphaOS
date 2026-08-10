import streamlit as st

from modules.auth import get_current_user
from modules.data import get_account_snapshot, get_user_settings
from modules.income_risk import session_texture, spread_management_plan
from modules.market_data import price_history, symbol_analysis
from modules.options_income import build_income_spread, select_expiration_buckets
from modules.public_data import (
    get_public_option_chain,
    get_public_option_expirations,
)
from modules.risk_guardrails import discipline_status
from modules.signal_quality import backtest_signal, reversal_diagnostics
from modules.strategies import primary_strategy_idea
from modules.trade_analyzer import (
    analyze_trade,
    growth_engine_plan,
)
from modules.ui import configure_page, empty_state, page_header


HORIZONS = [
    "Day trade (same day)",
    "Swing (2-8 weeks)",
    "Intermediate (2-6 months)",
    "Long term (6+ months)",
]


def load_spread_into_journal(symbol: str, spread: dict) -> None:
    for key in list(st.session_state):
        if key.startswith("journal_"):
            del st.session_state[key]
    management_notes = spread.get("management_notes")
    notes = (
        f"{spread['bucket']} income candidate; "
        f"target width ${spread['target_width']:,.2f}; "
        f"actual width ${spread['actual_width']:,.2f}; "
        f"estimated max profit ${spread['max_profit']:,.2f}; "
        f"estimated max loss ${spread['max_loss']:,.2f}; "
        f"breakeven {spread['breakeven']}."
    )
    if management_notes:
        notes = f"{notes} Management plan: {management_notes}"
    st.session_state["journal_spread_draft"] = {
        "symbol": symbol,
        "strategy": spread["strategy"],
        "expiration": spread["expiration"],
        "side": "Short / Credit",
        "entry_price": spread["net_credit"],
        "legs": spread["legs"],
        "notes": notes,
    }
    st.switch_page("pages/6_Trade_Journal.py")


configure_page("Trade Analyzer")
page_header(
    "Trade Analyzer & Growth Engine",
    "Pre-trade decisions, options strategy fit, income setups, and portfolio growth math.",
)

user = get_current_user()
user_id = user.get("id") if user else None
settings = get_user_settings(user_id=user_id)
snapshot = get_account_snapshot(user_id=user_id)

trade_tab, analyze_tab, income_tab, growth_engine_tab = st.tabs(
    ["Find a Trade", "Analyze My Trade", "Income Options", "Growth Engine"]
)

with trade_tab:
    with st.form("symbol_strategy_form"):
        c1, c2 = st.columns(2)
        symbol = c1.text_input("Symbol", value="SPY").strip().upper()
        horizon = c2.selectbox("Time horizon", HORIZONS)
        c3, c4 = st.columns(2)
        risk_tolerance = c3.selectbox(
            "Risk tolerance",
            ["Conservative", "Moderate", "Aggressive"],
        )
        objective = c4.selectbox(
            "Objective",
            ["Directional", "Income", "Hedging"],
        )
        submitted = st.form_submit_button(
            "Analyze Symbol",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        st.session_state["strategy_analysis_request"] = {
            "symbol": symbol,
            "horizon": horizon,
            "risk_tolerance": risk_tolerance,
            "objective": objective,
        }

    request = st.session_state.get("strategy_analysis_request")
    if request:
        analysis, source = symbol_analysis(request["symbol"], request["horizon"])
        st.caption(f"Data source: {source}")

        if analysis is None:
            empty_state(
                "Symbol analysis is unavailable.",
                "Verify the ticker and Public API connection in Settings.",
            )
        else:
            metrics = st.columns(6)
            metrics[0].metric("Last", f"${analysis['last']:,.2f}")
            metrics[1].metric(
                "Today",
                (
                    f"{analysis['change_pct']:+.2f}%"
                    if analysis["change_pct"] is not None
                    else "N/A"
                ),
            )
            metrics[2].metric("5-Day", f"{analysis['return_5d']:+.2f}%")
            metrics[3].metric("20-Day", f"{analysis['return_20d']:+.2f}%")
            metrics[4].metric("ATR", f"{analysis['atr_pct']:.2f}%")
            metrics[5].metric("Trend Score", analysis["trend_score"])
            context = st.columns(3)
            context[0].metric("Active Outlook", analysis["outlook"])
            context[1].metric("Day Bias", analysis.get("day_bias", "N/A"))
            context[2].metric(
                "Market Today",
                (
                    f"{analysis['market_change_pct']:+.2f}%"
                    if analysis.get("market_change_pct") is not None
                    else "N/A"
                ),
            )
            if request["horizon"] == "Day trade (same day)":
                st.caption(
                    "Day-trade outlook uses live quote change, SPY/QQQ alignment, 5-day context, volume, and price location. Swing trend remains available as the slower backdrop."
                )

            primary, alternatives = primary_strategy_idea(
                analysis["outlook"],
                analysis["volatility"],
                request["risk_tolerance"],
                request["objective"],
                request["horizon"],
            )

            st.subheader(f"{analysis['symbol']} Research Suggestion")
            st.markdown(f"### {primary['strategy']}")
            st.dataframe(
                [
                    {
                        "Market view": analysis["outlook"],
                        "Volatility regime": analysis["volatility"],
                        "Vehicle": primary["vehicle"],
                        "Structure": primary["structure"],
                        "Why it fits": primary["fit"],
                        "Defined risk": primary["risk"],
                    }
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Alternatives")
            st.dataframe(alternatives, use_container_width=True, hide_index=True)

            with st.expander("Reversal Risk & Signal Backtest", expanded=True):
                history, history_source = price_history(request["symbol"])
                st.caption(f"Backtest source: {history_source}")
                if history.empty:
                    empty_state(
                        "Signal diagnostics are unavailable.",
                        "Historical bars are required for reversal checks and backtesting.",
                    )
                else:
                    checks = reversal_diagnostics(history, analysis["outlook"])
                    st.dataframe(checks, use_container_width=True, hide_index=True)

                    hold_map = {
                        "Day trade (same day)": 1,
                        "Swing (2-8 weeks)": 5,
                        "Intermediate (2-6 months)": 20,
                        "Long term (6+ months)": 60,
                    }
                    backtest = backtest_signal(
                        history,
                        analysis["outlook"],
                        hold_days=hold_map.get(request["horizon"], 5),
                    )
                    discipline = discipline_status(
                        snapshot.get("trades", []),
                        settings,
                        reversal_checks=checks,
                        backtest=backtest,
                    )
                    if discipline["status"] == "Blocked":
                        st.error("Trade blocked by your discipline guardrails.")
                    elif discipline["status"] == "Caution":
                        st.warning("Trade requires caution under your discipline guardrails.")
                    else:
                        st.success("Discipline guardrails are clear.")

                    d_cols = st.columns(4)
                    d_cols[0].metric("Trades Today", discipline["trades_today"])
                    d_cols[1].metric(
                        "Realized Today",
                        f"${discipline['realized_today']:,.2f}",
                    )
                    d_cols[2].metric(
                        "Daily Loss Limit",
                        f"${discipline['daily_loss_limit']:,.2f}",
                    )
                    d_cols[3].metric(
                        "Consecutive Losses",
                        discipline["consecutive_losses"],
                    )
                    for blocker in discipline["blockers"]:
                        st.error(blocker)
                    for warning in discipline["warnings"]:
                        st.warning(warning)

                    if discipline["guardrails"]["require_pretrade_checklist"]:
                        st.markdown("#### Pre-Trade Checklist")
                        c1, c2, c3 = st.columns(3)
                        planned_exit = c1.checkbox("Invalidation is defined")
                        sized_correctly = c2.checkbox("Size fits risk limit")
                        not_revenge = c3.checkbox("Not revenge trading")
                        if not all([planned_exit, sized_correctly, not_revenge]):
                            st.info(
                                "Checklist incomplete. Treat this as a stand-down until every box is true."
                            )

                    bt_cols = st.columns(5)
                    bt_cols[0].metric("Signals Tested", backtest["trades"])
                    bt_cols[1].metric("Win Rate", f"{backtest['win_rate']:.1f}%")
                    bt_cols[2].metric(
                        "Avg Return",
                        f"{backtest['average_return']:+.2f}%",
                    )
                    bt_cols[3].metric("Profit Factor", backtest["profit_factor"])
                    bt_cols[4].metric("Worst Trade", f"{backtest['max_loss']:+.2f}%")
                    if backtest["results"].empty:
                        empty_state(
                            "No matching historical signals were found.",
                            "Treat the current signal as unproven until more context is available.",
                        )
                    else:
                        st.dataframe(
                            backtest["results"].head(20),
                            use_container_width=True,
                            hide_index=True,
                        )
                st.caption(
                    "Backtests are simple historical signal studies, not fill-aware execution simulations. Use them as context, not a guarantee."
                )

            st.subheader("Risk Budget")
            b1, b2, b3 = st.columns(3)
            capital = b1.number_input(
                "Account capital",
                min_value=0.0,
                value=10000.0,
                step=500.0,
            )
            risk_pct = b2.slider(
                "Risk per trade (%)",
                0.1,
                5.0,
                1.0,
                0.1,
            )
            max_option_loss = b3.number_input(
                "Maximum loss per option position",
                min_value=1.0,
                value=200.0,
                step=25.0,
            )
            risk_dollars = capital * (risk_pct / 100)
            stop_distance = analysis["last"] * (analysis["atr_pct"] / 100) * 2
            share_count = int(risk_dollars / stop_distance) if stop_distance else 0
            option_count = (
                int(risk_dollars / max_option_loss) if max_option_loss else 0
            )

            sizes = st.columns(3)
            sizes[0].metric("Risk Budget", f"${risk_dollars:,.2f}")
            sizes[1].metric("Stock Size at 2 ATR", f"{share_count:,} shares")
            sizes[2].metric(
                "Defined-Risk Option Size",
                f"{option_count:,} positions",
            )

with analyze_tab:
    st.subheader("Manual Pre-Trade Analyzer")
    with st.form("manual_trade_analyzer_form"):
        a1, a2, a3 = st.columns(3)
        analyzer_symbol = a1.text_input("Ticker", value="SPY").strip().upper()
        horizon_selection = a2.selectbox(
            "Holding period",
            ["AUTO-DETECT", "DAY TRADE", "WEEKLY", "MONTHLY", "POSITION", "LEAPS"],
        )
        strategy = a3.selectbox(
            "Strategy",
            [
                "Long Call",
                "Long Put",
                "Call Debit Spread",
                "Put Debit Spread",
                "Put Credit Spread",
                "Call Credit Spread",
                "Iron Condor",
                "Butterfly",
                "Calendar Spread",
                "Diagonal Spread",
                "LEAPS Call",
                "LEAPS Put",
                "LEAPS Debit Spread",
            ],
        )
        b1, b2, b3, b4 = st.columns(4)
        expiration = b1.date_input("Expiration")
        premium = b2.number_input(
            "Debit or credit per spread/contract",
            min_value=0.0,
            value=0.25,
            step=0.01,
        )
        contracts = b3.number_input("Contracts / spreads", min_value=1, value=1, step=1)
        account_balance = b4.number_input(
            "Account balance",
            min_value=0.0,
            value=float(settings.get("default_account_size") or 100.0),
            step=50.0,
        )
        c1, c2 = st.columns(2)
        risk_pct = c1.number_input(
            "Planned risk (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(settings.get("default_risk_pct") or 5.0),
            step=0.25,
        )
        risk_dollar_limit = c2.number_input(
            "Max planned dollar risk",
            min_value=0.0,
            value=7.0,
            step=1.0,
        )
        legs_text = st.text_area(
            "Legs",
            value="Buy 550C\nSell 555C",
            help="Examples: Buy 550C, Sell 555C, Sell 540P.",
        )
        analyze_submitted = st.form_submit_button(
            "Analyze Trade",
            type="primary",
            use_container_width=True,
        )

    if analyze_submitted:
        with st.spinner("Analyzing trade fit, risk, and exit structure..."):
            analysis, analysis_source = symbol_analysis(analyzer_symbol, horizon_selection)
            history, history_source = price_history(analyzer_symbol)
            texture = session_texture(history, analysis or {})
            result = analyze_trade(
                analyzer_symbol,
                strategy,
                horizon_selection,
                expiration,
                legs_text,
                premium,
                contracts,
                account_balance,
                risk_pct,
                risk_dollar_limit,
                analysis,
                texture,
            )
            st.session_state["manual_trade_analysis"] = {
                "result": result,
                "analysis": analysis,
                "analysis_source": analysis_source,
                "texture": texture,
                "history_source": history_source,
            }

    manual = st.session_state.get("manual_trade_analysis")
    if manual:
        result = manual["result"]
        analysis = manual["analysis"]
        texture = manual["texture"]
        st.caption(
            f"Data sources: {manual['analysis_source']}; {manual['history_source']}"
        )
        verdict_cols = st.columns(5)
        verdict_cols[0].metric("Verdict", result["verdict"])
        verdict_cols[1].metric("Score", f"{result['score']}/100")
        verdict_cols[2].metric("Horizon", result["horizon"])
        verdict_cols[3].metric("DTE", result["dte"] if result["dte"] is not None else "N/A")
        verdict_cols[4].metric("Session", texture["label"])

        if result["verdict"] == "DO NOT TAKE":
            st.error("NO TRADE / DO NOT TAKE")
        elif result["warnings"]:
            st.warning("Trade is not clean. Review warnings before deciding.")
        else:
            st.success("Analyzer found a complete pre-trade structure.")

        if result["blockers"]:
            st.subheader("Blockers")
            for blocker in result["blockers"]:
                st.error(blocker)
        if result["warnings"]:
            st.subheader("Warnings")
            for warning in result["warnings"]:
                st.warning(warning)

        st.subheader("Trade Card")
        risk = result["risk"]
        st.dataframe(
            [
                {
                    "Ticker": result["symbol"],
                    "Strategy": result["strategy"],
                    "Direction": result["direction"],
                    "Horizon": result["horizon"],
                    "Capital Required": risk["capital_required"],
                    "Planned Loss": risk["planned_loss"],
                    "Max Loss": risk["max_loss"],
                    "Max Profit": risk["max_profit"],
                    "Reward/Risk": risk["reward_risk"],
                    "Account Committed %": risk["account_committed_pct"],
                    "Risk Class": risk["risk_class"],
                }
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.dataframe(result["legs"], use_container_width=True, hide_index=True)

        st.subheader("Relevant Timeframes")
        st.dataframe(
            [{"Timeframe": item} for item in result["timeframes"]],
            use_container_width=True,
            hide_index=True,
        )

        if analysis:
            context_cols = st.columns(4)
            context_cols[0].metric("Underlying", f"${analysis['last']:,.2f}")
            context_cols[1].metric("Day Bias", analysis.get("day_bias", "N/A"))
            context_cols[2].metric("Swing", analysis.get("swing_outlook", analysis.get("outlook", "N/A")))
            context_cols[3].metric("ATR", f"{analysis['atr_pct']:.2f}%")
        st.info(f"{texture['detail']} {texture['action']}")

        st.subheader("Trade Management")
        plan = result["exit_plan"]
        if not plan.get("available"):
            st.error(plan["reason"])
        else:
            st.dataframe(
                [
                    {"Item": "Entry", "Plan": plan["entry"]},
                    {"Item": "Initial invalidation", "Plan": plan["underlying_invalidation"]},
                    {"Item": "Estimated option/spread stop", "Plan": plan["estimated_option_stop"]},
                    {"Item": "Planned loss", "Plan": plan["planned_loss"]},
                    {"Item": "Target 1", "Plan": plan["target_1"]},
                    {"Item": "Target 2", "Plan": plan["target_2"]},
                    {"Item": "Profit plan", "Plan": plan["profit_plan"]},
                    {"Item": "Breakeven rule", "Plan": plan["breakeven_rule"]},
                    {"Item": "Time stop", "Plan": plan["time_stop"]},
                    {"Item": "Early exit", "Plan": plan["early_exit"]},
                    {"Item": "End of day", "Plan": plan["eod"]},
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "Option/spread stop values are estimates. Greeks, volatility, time decay, and bid/ask changes can alter actual fillable prices."
            )

with income_tab:
    with st.form("income_options_form"):
        i1, i2, i3 = st.columns(3)
        income_symbol = i1.text_input(
            "Income ticker",
            value="SPY",
            help="Works with optionable ETFs/stocks such as SPY, QQQ, DIA, IWM, and index symbols such as SPX when supported by Public.",
        ).strip().upper()
        spread_bias = i2.selectbox(
            "Spread bias",
            ["Auto from trend", "Bullish", "Neutral", "Bearish"],
        )
        width_choice = i3.selectbox(
            "Spread width",
            ["Auto", "$1 wide", "$2 wide", "$3 wide", "$5 wide", "$10 wide"],
            index=2,
        )
        income_submitted = st.form_submit_button(
            "Build Income Spreads",
            type="primary",
            use_container_width=True,
        )

    if income_submitted:
        st.session_state["income_options_request"] = {
            "symbol": income_symbol,
            "bias": spread_bias,
            "width": None
            if width_choice == "Auto"
            else float(width_choice.replace("$", "").replace(" wide", "")),
            "width_label": width_choice,
        }

    income_request = st.session_state.get("income_options_request")
    if income_request:
        analysis, source = symbol_analysis(
            income_request["symbol"],
            "Day trade (same day)",
        )
        st.caption(f"Data source: {source} + Public option chain")

        if analysis is None:
            empty_state(
                "Income analysis is unavailable.",
                "Verify the ticker is optionable and the Public connection is active.",
            )
        else:
            outlook = (
                analysis["outlook"]
                if income_request["bias"] == "Auto from trend"
                else income_request["bias"]
            )
            try:
                expirations = get_public_option_expirations(
                    income_request["symbol"]
                )
                buckets = select_expiration_buckets(expirations)
                candidates = {}
                for bucket, expiration in buckets.items():
                    chain = get_public_option_chain(
                        income_request["symbol"],
                        expiration,
                    )
                    candidates[bucket] = build_income_spread(
                        chain,
                        float(analysis["last"]),
                        outlook,
                        bucket,
                        spread_width=income_request["width"],
                    )
            except Exception:
                candidates = {}

            header_metrics = st.columns(4)
            header_metrics[0].metric(
                "Underlying",
                f"${analysis['last']:,.2f}",
            )
            header_metrics[1].metric("Trend", outlook)
            header_metrics[2].metric(
                "20-Day Return",
                f"{analysis['return_20d']:+.2f}%",
            )
            header_metrics[3].metric(
                "Realized Volatility",
                analysis["volatility"],
            )
            history, history_source = price_history(income_request["symbol"])
            texture = session_texture(history, analysis)
            texture_cols = st.columns(4)
            texture_cols[0].metric("Session Setup", texture["label"])
            texture_cols[1].metric("Status", texture["status"])
            texture_cols[2].metric("Day Bias", analysis.get("day_bias", "N/A"))
            texture_cols[3].metric(
                "Market Today",
                (
                    f"{analysis['market_change_pct']:+.2f}%"
                    if analysis.get("market_change_pct") is not None
                    else "N/A"
                ),
            )
            if texture["status"] in {"Caution", "Directional"}:
                st.warning(f"{texture['detail']} {texture['action']}")
            else:
                st.info(f"{texture['detail']} {texture['action']}")
            st.caption(f"Chart context source: {history_source}")
            st.caption(
                f"Requested width: {income_request.get('width_label', 'Auto')}. "
                "If the exact strike width is not listed, AlphaOS uses the nearest available protection leg."
            )

            if not candidates or not any(candidates.values()):
                empty_state(
                    "No viable income spread was found.",
                    "The selected chain may lack liquid contracts with valid bid and ask prices.",
                )
            else:
                bucket_tabs = st.tabs(["Day Trade", "Weekly", "Monthly"])
                for tab, bucket in zip(
                    bucket_tabs,
                    ["Day Trade", "Weekly", "Monthly"],
                ):
                    with tab:
                        spread = candidates.get(bucket)
                        if spread is None:
                            empty_state(
                                f"No {bucket.lower()} spread is available.",
                                "Try another ticker or directional bias.",
                            )
                            continue

                        st.subheader(spread["strategy"])
                        st.caption(
                            f"Expiration: {spread['expiration']} - "
                            f"{spread['expiration_note']}"
                        )
                        spread_metrics = st.columns(4)
                        spread_metrics[0].metric(
                            "Estimated Credit",
                            f"${spread['net_credit']:,.2f}",
                        )
                        spread_metrics[1].metric(
                            "Actual Width",
                            f"${spread['actual_width']:,.2f}",
                        )
                        spread_metrics[2].metric(
                            "Max Profit",
                            f"${spread['max_profit']:,.2f}",
                        )
                        spread_metrics[3].metric(
                            "Max Loss",
                            f"${spread['max_loss']:,.2f}",
                        )
                        st.metric(
                            "Breakeven",
                            spread["breakeven"],
                        )
                        st.dataframe(
                            spread["legs"],
                            use_container_width=True,
                            hide_index=True,
                        )
                        management_plan = spread_management_plan(spread, analysis)
                        spread["management_notes"] = " ".join(
                            f"{row['Rule']}: {row['Trigger']}."
                            for row in management_plan
                        )
                        st.subheader("Stop & Management Plan")
                        st.dataframe(
                            management_plan,
                            use_container_width=True,
                            hide_index=True,
                        )
                        st.caption(
                            "Management levels are planning references, not automated orders. Decide before entry, then follow the plan instead of flipping direction after a stop."
                        )
                        if st.button(
                            "Load into Trade Journal",
                            key=f"load_{bucket}",
                            use_container_width=True,
                        ):
                            load_spread_into_journal(
                                income_request["symbol"],
                                spread,
                            )

with growth_engine_tab:
    st.subheader("Growth Engine Strategy")
    g1, g2, g3 = st.columns(3)
    current_value = g1.number_input(
        "Current portfolio value",
        min_value=0.0,
        value=float(settings.get("default_account_size") or 100.0),
        step=50.0,
        key="growth_engine_current",
    )
    target_value = g2.number_input(
        "Target portfolio value",
        min_value=0.0,
        value=max(float(settings.get("default_account_size") or 100.0) * 2, 250.0),
        step=50.0,
        key="growth_engine_target",
    )
    target_days = g3.number_input(
        "Target days",
        min_value=1,
        value=90,
        step=1,
        key="growth_engine_days",
    )
    g4, g5, g6 = st.columns(3)
    risk_per_trade = g4.number_input(
        "Risk per trade (%)",
        min_value=0.0,
        max_value=25.0,
        value=float(settings.get("default_risk_pct") or 5.0),
        step=0.25,
        key="growth_engine_risk",
    )
    trades_per_week = g5.number_input(
        "Planned trades per week",
        min_value=0,
        value=3,
        step=1,
        key="growth_engine_trades",
    )
    average_r = g6.number_input(
        "Average R per winning plan",
        min_value=-5.0,
        value=1.0,
        step=0.25,
        key="growth_engine_avg_r",
    )
    plan = growth_engine_plan(
        current_value,
        target_value,
        target_days,
        risk_per_trade,
        trades_per_week,
        average_r,
    )
    plan_cols = st.columns(5)
    plan_cols[0].metric("Growth Needed", f"${plan['gap']:,.2f}")
    plan_cols[1].metric("Daily Need", f"${plan['daily_needed']:,.2f}")
    plan_cols[2].metric("Daily %", f"{plan['daily_pct']:.2f}%")
    plan_cols[3].metric("Weekly Need", f"${plan['weekly_needed']:,.2f}")
    plan_cols[4].metric("Expected Weekly", f"${plan['expected_weekly_profit']:,.2f}")
    if "PLAUSIBLE" in plan["posture"] or "MET" in plan["posture"]:
        st.success(plan["posture"])
    else:
        st.warning(plan["posture"])
    st.dataframe(
        [
            {
                "Rule": "Only take complete trade cards",
                "Why": "A trade without entry, invalidation, planned loss, and targets does not qualify for the growth plan.",
            },
            {
                "Rule": "Respect weekly risk budget",
                "Why": f"Planned weekly risk budget is about ${plan['weekly_risk_budget']:,.2f}.",
            },
            {
                "Rule": "No trade is a valid outcome",
                "Why": "The growth engine depends on avoiding low-quality trades, not forcing activity.",
            },
            {
                "Rule": "Stop after guardrail breach",
                "Why": "Overtrading and revenge trading damage account survival more than missed trades.",
            },
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Growth projections are planning math only. They are not expected returns or profit guarantees."
    )

st.caption(
    "Research only. Option estimates use current midpoint data and may not be fillable. Day-trade candidates use same-day expiration when listed; otherwise the nearest available expiration is shown. AlphaOS does not place orders."
)
