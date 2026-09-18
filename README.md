# AlphaOS

AlphaOS is a Streamlit premium-selling research app with timeframe selection, 15 income strategy generators, expiration risk/reward, estimated probability of profit, and interactive payoff charts. It retains the Scanner, Pulse Bar lab, TradingView tools, and existing Public/Supabase integrations.

The MVP intentionally does not support automated trade execution.

## Active Pages

- Dashboard
- Scanner
- Strategy Selector
- Quant Lab
- TradingView Indicator
- Settings

## Current MVP Features

- Supabase-ready authentication
- Defined-risk spread suggestions
- Public.com option-chain pricing
- Alpaca or CSV-uploaded 30-minute Pulse Bar candles
- SPX, XSP, SPY, QQQ, IWM, and DIA scanner universe
- Pulse Bar Original vs Enhanced backtest lab
- Compounding growth calculator

## Local Preview

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

If Supabase secrets are not configured, use the demo session in the sidebar. Demo data is stored in the Streamlit session only.

## Supabase Setup

1. Create a Supabase project.
2. Open SQL Editor.
3. Run `supabase/schema.sql`.
4. In Authentication settings, enable email/password auth.
5. Copy the project URL and anon public key.

The app uses row-level security policies so each authenticated user can access only their own settings, watchlist, trades, and P&L snapshots.

## GitHub Setup

1. Create a new GitHub repository.
2. Commit and push this project.
3. Do not commit `.streamlit/secrets.toml`.
4. Keep `.streamlit/secrets.toml.example` as the template for required secrets.

## Streamlit Community Cloud Deployment

1. Go to Streamlit Community Cloud.
2. Create a new app from the GitHub repository.
3. Set the main file path to `streamlit_app.py`.
4. Add secrets in App settings:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your-supabase-anon-key"
PUBLIC_API_SECRET = "your-public-secret-key"
PUBLIC_OWNER_EMAIL = "your-login-email@example.com"
ALPACA_API_KEY_ID = "your-alpaca-key-id"
ALPACA_API_SECRET_KEY = "your-alpaca-secret-key"
```

5. Deploy the app.

The deployed app is browser-based and usable from desktop and phone browsers.

## Architecture Notes

- `streamlit_app.py` is the main dashboard entrypoint.
- `pages/` contains Streamlit multipage routes.
- `disabled_pages/` contains retired MVP pages that are not loaded by Streamlit.
- `modules/public_data.py` contains server-side Public.com calls for brokerage, quotes, and option chains.
- `modules/alpaca_data.py` contains server-side Alpaca calls for 30-minute ETF bars.
- `modules/pulse_backtest.py` contains the Pulse Bar setup detection and backtest logic.
- `tradingview/alphaos_pulse_confirm.pine` contains the TradingView confirmation indicator for 30-minute Pulse Bar setups.
- `supabase/schema.sql` contains database tables, row-level security, and update triggers.
- API keys belong in Streamlit secrets, never in source control.

## TradingView Confirmation Indicator

Open TradingView, create a new Pine Script indicator, paste `tradingview/alphaos_pulse_confirm.pine`, save it, and add it to a 30-minute chart. Use the alert conditions for Pulse Bar detection, breakout confirmation, and chop warnings.

## Alpaca Data

Quant Lab can pull 30-minute bars from Alpaca for ETF symbols such as `SPY`, `QQQ`, `DIA`, and `IWM`. Since Alpaca stock bars do not reliably cover `SPX` and `XSP` on free plans, the app includes an option to use `SPY` as a proxy for those index symbols during research.

## Premium Studio rebuild

The home page and Strategy Selector now open a shared premium-selling workspace.
Choose a preset horizon or a custom 0–180 calendar-day expiration range, select
strategies and risk families, and click **Find premium trades**. The maximum-loss
budget is per strategy unit; zero disables that filter. Stock-backed positions
include share-purchase risk. Unlimited-risk trades require the Uncovered family
and no maximum-loss budget.

Supported generators: bull put and bear call spreads, iron condors, iron
butterflies, cash-secured puts, covered calls, covered strangles, short puts,
short calls, short strangles, short straddles, call/put ratio spreads, and
call/put broken-wing butterflies. Only net-credit constructions are returned.
Calendars, diagonals and other multi-expiration strategies are documented but
not generated. This is not an exhaustive set of all possible option combinations.

The demo uses synthetic quotes for a fictional $500 underlying. Connected mode
uses the existing Public adapter, never silently substitutes demo prices, and
reports the underlying timestamp plus retrieval time. The adapter does not expose
option quote timestamps; verify freshness before acting. Index share-covered
positions are excluded. Standard 100-share contract assumptions must be verified
against broker specifications.

Probability of profit is a lognormal expiration-payoff estimate after entry
commissions, using constant volatility and zero price drift. It is not a backtest
or a prediction guarantee. Same-day POP is unavailable. IV may be manually set or
estimated from near-ATM chain IV. Risk:reward means maximum loss / maximum profit.
Natural and midpoint pricing, per-contract entry commissions, payoff charts,
breakevens, stock/cash requirements and CSV exports are included.

Engine tests (no third-party dependencies):

```bash
python -m unittest discover -s tests -v
```

Implementation: `modules/premium_engine.py` contains pricing/payoff calculations;
`modules/premium_workspace.py` contains the shared Streamlit workspace. Existing
Scanner, Quant Lab, TradingView and Settings routes remain available.

## Quantitative research workbench

Opportunity rows are selectable and show strike summaries. Selecting a row opens
its contract legs and payoff without a dropdown, and sends the snapshot to the
Quant Lab options stress tab for deterministic terminal-price scenarios.

Quant Lab now includes daily portfolio research from adjusted-close CSVs or an
explicitly synthetic demonstration dataset. Models include long-only momentum,
inverse volatility and equal weight. Signals have a full-bar execution delay;
trading costs account for portfolio drift and turnover. Reports include NAV,
CAGR, Sharpe, Sortino, Calmar, drawdown, historical VaR/expected shortfall,
rolling volatility, correlations, shrunk-covariance risk contributions and
benchmark OLS diagnostics.

Chronological walk-forward validation selects momentum lookbacks using training
Sharpe and evaluates nonoverlapping test blocks. A seeded moving-block bootstrap
simulates net out-of-sample returns. JSON manifests include configuration and a
dataset hash; OOS returns can be exported. The original Pulse lab is retained in
its own tab. This is a research workbench, not a validated institutional risk
system or a historical options backtester. See the in-app Methodology for timing,
cost, data-quality and model assumptions.

Run all numerical tests with pandas/numpy installed:
`python -m unittest discover -s tests -v`.

## Public-powered research

Portfolio Research now defaults to Public market history: choose ETF symbols and
one, five or ten years, then run research. Daily provider bars are requested via
the existing server-side credential, aligned on common dates without filling,
and current-day bars are excluded. Sparse or invalid data fails explicitly;
there is no synthetic fallback. Adjustment semantics are unverified, so Public
mode reports price-return research, not validated total returns. The retrieval
audit, latest available quotes, actual coverage, source CSV and metadata are
available in the app. Research is refreshed on submission with a five-minute
history cache, not a continuously streaming or scheduled feed.

Selected Public options now retain quote timestamps and Greeks. Quant Lab can
show signed Greek exposure and request a month of individual contract OHLCV.
That endpoint does not establish historical chain discovery or historical bid/ask
coverage for expired contracts. No brokerage positions, orders or executions are
requested by the research workflow.

## Manual option trades

Quant Lab → Options stress lab now offers Selected opportunity or Enter my own
trade. The manual builder supports 1–12 same-expiration option legs with buy/sell,
call/put, whole contract quantities, strikes and per-share entry premiums, plus
optional signed shares with a separate stock entry price, total fees and model
volatility. Debit and credit positions share the expiration stress workflow.
Input validation rejects incomplete legs and expired dates. Manual and scanner
positions are stored separately in browser-session state. Export manual inputs
as JSON to retain a copy; this workflow does not place orders.
