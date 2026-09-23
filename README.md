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

## Phase 1: adaptive options payoff analysis

Options stress lab now separates a fine Payoff map from the existing Extreme
stress scenarios. The map includes exact spot, strikes, calculated breakevens,
and interval midpoints, with padding on both sides. Regular sampling targets
$0.50 or finer at ETF scale and tightens to a quarter of the narrowest strike
gap. Broad ranges are limited to 401 regular points plus exact landmarks and
midpoints. The chart marks spot, strikes, breakevens and finite global bounds;
the table labels landmarks and reports terminal price, move, P&L and return on
finite positive maximum risk. Scenarios are deterministic, not probabilities.

Economics are recalculated through the unchanged generalized payoff engine,
including stock entry basis, fees and strategy units. Net credit/debit includes
entry fees but excludes stock purchase cash flows. Width and pre-fee credit as
a percentage of width are shown only for equal-quantity, two-leg verticals
without shares; they are intentionally unavailable for ambiguous structures.
Contracts must share an expiration and use the standard 100-share multiplier.
The existing model POP is retained separately; no historical probability,
expectancy model, recommendation system, ML or new dependency was added.

Validation: 47 unit/integration tests, including narrow credit/debit spreads,
condors, butterflies, broken wings, multiple roots, stock basis, scaling,
unlimited exposure, malformed trades, both input paths and Portfolio Research.
Before Phase 2, establish reliable historical chains/quotes and corporate-action
handling, settlement and assignment conventions, execution/fee assumptions, and
a chronological validation protocol. Daily individual-contract bars alone do
not establish a historical options execution backtest.

## Phase 2: historical market state

Quant Lab → Market State Research provides SPY/QQQ trailing daily features and
separate future-outcome labels using Public FIVE_YEARS/TEN_YEARS history.
Warm-up and unavailable forward outcomes stay missing. Export separate CSVs
with metadata or download the JSON manifest. Existing options, Portfolio
Research and Pulse workflows are retained.

See [formulas, availability, tests and data limitations](docs/market_state.md).
The complete suite passes 71 tests. Provider session completeness and
corporate-action adjustment remain unverified and are disclosed in the UI.
No recommendations or options expectancy model are added.

## Phase 3: historical analog research

After generating a Phase 2 dataset, open Quant Lab → Historical Analogs. Compare
the latest completed or a historical target using configurable tolerance filters
or standardized nearest neighbors. Candidate dates are strictly earlier, and
outcomes must have matured by the target close. Separate per-horizon masks prevent
later information from entering historical-date summaries or exports.

Inspect feature funnels, independent pass counts, historical return/excursion
summaries, distributions, percentile curves, analog timelines and fixed tolerance
sensitivity presets. These are descriptive historical frequencies, not forecast
probabilities or trade recommendations. All 100 tests pass, including retained
Phase 1/2, Portfolio and Pulse integration tests.

See [historical analog methods, chronology and limitations](docs/historical_analogs.md).

## Phase 4: threshold / strike survival research

Quant Lab → Threshold Research evaluates normalized underlying thresholds on
the saved Phase 3 sample. Put/call styles separately report terminal survival,
touch/breach, equality and recovery, with explicit valid counts and nominal
Wilson intervals. Price/percentage inputs, selected short-leg shortcuts, custom
distance grids, horizon matrices, distribution context, non-overlapping
robustness and observation export are available. Historical targets recheck
outcome maturity and use target-date spot; saved-trade shortcuts are disabled
in that mode. Existing provider/model POP is unchanged and remains separate.

All 133 tests pass. See [threshold definitions, denominators and limitations](docs/threshold_survival.md).
This is descriptive underlying research, not historical option execution or
profitability. No recommendations or Phase 5 functionality are added.

Public daily-history retrieval now maps ten years to an explicit supported
start-date request, with strict coverage checks and safe diagnostics. See the
[reproduction, period mapping and data-quality notes](docs/public_history_debugging.md).

## Daily research and options archive

`python scripts/run_daily_quant.py` runs the existing Phase 2–4 engines without
Streamlit, with frozen SPY/QQQ defaults and separate point-in-time option-chain
observations. The GitHub Actions workflow runs at 22:23 UTC on weekdays and
checks the NYSE calendar. Existing artifacts are immutable; partial failures
and quote-quality issues remain explicit. Quant Lab's **Daily Archive** tab
opens archived sessions without changing interactive research.

Configure the GitHub Actions secret `PUBLIC_API_SECRET` and optionally
`PUBLIC_ACCOUNT_NUMBER`; Streamlit secrets are not automatically shared with
Actions. See [setup, every schema field, units, timing and limitations](docs/daily_quant_schema.md).
This is collection infrastructure, not Phase 5 or trade recommendations.


### Phase 6: integrated trade research

Quant Lab **Trade Research** combines current-spot-anchored distributions, historical support/resistance, short-strike behavior, Phase 5.2 economics and fixed robustness comparisons. Enter a vertical or load a saved trade; normalized option-chain CSVs support unranked candidate evidence comparisons. See [research definitions, boundary audit and limitations](docs/phase6_research.md).


### Strategy Selector research handoff

Public SPY/QQQ scans now show completed price structure above live candidates. Select a row and use **Research selected trade in Quant Lab** to carry its quote, actual credit and explicit research horizon into the integrated workspace. [Workflow, caching, provenance and limitations](docs/selector_quant_workflow.md).
