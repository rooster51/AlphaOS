# Distribution-conditioned option economics

## Purpose

Phase 5 applies a **current/saved option structure's exact expiration payoff** to forward underlying returns observed in the Phase 3 historical-analog sample. It answers a scenario question: if today's structure had faced those underlying terminal moves, what expiration P&L distribution would today's payoff produce?

It is **not a historical options backtest**. AlphaOS does not pretend today's credit, volatility surface, bid/ask, Greeks, or contract existed on the analog dates.

## Scenario construction

For target spot `S0` and an analog H-session forward return `r_i`:

`scenario_terminal_spot_i = S0 * (1 + r_i)`

The scenario terminal spot is passed to the existing Phase 1 generalized expiration payoff function. This preserves partial P&L between strikes rather than reducing a spread to a binary short-strike survival event.

Only finite Phase 3 outcomes that were marked observable by the target date are used. Analog dates must be unique and strictly before the target. Supported horizons remain 1, 2, 3, 5, and 10 observed sessions. Calendar DTE is not silently treated as trading-session horizon.

## Reported economics

AlphaOS reports the arithmetic mean scenario payoff as **distribution-conditioned expected payoff**, plus median, payoff percentiles, positive/negative/zero payoff frequencies, worst/best scenario, average winner, average loser, profit factor, and expected payoff divided by finite maximum risk.

These statistics describe the selected analog sample and today's payoff function. They are not guarantees or calibrated future probabilities.

## Friction

The saved trade's existing entry fees remain inside the Phase 1 payoff. Phase 5 can additionally model nonnegative dollar friction for commission per option contract, entry slippage per strategy unit, and terminal/exit friction per strategy unit. Gross and net scenario economics remain separate so modeled friction is visible rather than hidden.

## Robustness

The engine accepts either Phase 3 analog method. A non-overlapping diagnostic uses the same deterministic earliest-first observed-session-window convention as Phase 4 when the required chronology metadata is available. This reduces overlapping outcome windows but does not make the observations statistically independent.

## Limitations

- Historical analog selection depends on the chosen state variables and tolerances/distance model.
- Today's option quote and payoff are applied to historical **underlying** returns; historical option premiums are not reconstructed.
- No historical volatility surface, bid/ask path, intraday mark-to-market, stop execution, early assignment, pin risk, or exercise behavior is reconstructed.
- Daily underlying outcomes cannot reproduce intraday option management.
- Overlapping analog observations can be dependent.
- Public underlying adjustment conventions and exchange-session completeness retain the upstream limitations documented by Market State Research.
- A positive distribution-conditioned expected payoff does not establish that a trade is profitable in the future.

## Merge gates

Do not merge Phase 5 to `main` until the full regression suite executes successfully in a real runtime, the Streamlit Option Economics page loads without import/runtime errors, and the saved opportunity and completed-session target are intentionally synchronized rather than silently mixed.

A later phase may consume this engine for systematic candidate comparison, but Phase 5 itself does not select strikes, expirations, rank trades, or submit orders.
