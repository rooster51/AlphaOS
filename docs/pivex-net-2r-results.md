# XAUUSD net 2R target experiment

**Research only — no demonstrated positive expectancy.** This target mode is opt-in and disabled by default.

The experiment converted qualifying confirmations into modeled entries, but the completed trades lost money in development and in the evaluated portion of the independent holdout. The holdout stopped early with unresolved exposure. These results provide no evidence of historical profitability.

The [protocol](pivex-net-2r-protocol.md) and implementation were frozen at commit `7c2caa1c3991b3cce91c8a11ea9d231950187d44` before downloading or examining the 2024 holdout. This was a previously unused data sample from an earlier market regime. October–December 2025 was excluded because it had already been inspected.

## Results

All figures are for an external bid-candle proxy at one modeled ounce. Drawdown and P&L use completed trades. Average R equals empirical expectancy per completed trade.

| Period and mode | Observed / evaluated M5 | Setups evaluated | Accepted | Target / stop / unresolved | Net P&L | Avg R / expectancy | Profit factor | Max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Jan–Sep 2025 baseline | 53,096 / 53,096 | 16 | 0 | 0 / 0 / 0 | $0.00 | — | — | — |
| Jan–Sep 2025 net 2R | 53,096 / 52,601 | 15 | 12 | 1 / 11 / 0 | −$53.89 | −0.75R | 0.152 | $53.89 |
| Jan–Sep 2025 net 2R, adverse | 53,096 / 52,671 | 16 | 7 | 0 / 7 / 0 | −$54.77 | −1.00R | 0.000 | $54.77 |
| 2024 holdout baseline | 69,896 / 69,896 | 19 | 0 | 0 / 0 / 0 | $0.00 | — | — | — |
| 2024 holdout net 2R | 69,896 / 14,100 | 6 | 5 | 0 / 4 / 1 | −$13.58 | −1.00R | 0.000 | $13.58 |
| 2024 holdout net 2R, adverse | 69,896 / 14,102 | 6 | 4 | 0 / 3 / 1 | −$15.60 | −1.00R | 0.000 | $15.60 |

The replay evaluates setups while flat, which accounts for differences in evaluation counts. In development, the structural gate rejected two base-cost and eight adverse-cost setups. Each run had one missing contiguous next candle. In the holdout, the structural gate rejected one base-cost and two adverse-cost setups. Both experimental holdout replays stopped at the same unexplained five-minute gap on March 19 while a position was open. They assigned no exit or P&L to that position. The rest of 2024 contributed no experimental performance observations. The independent result covers a limited sample of trades and one feed.

Development data contained 736 unexplained five-minute slots and 24,792 modeled closure slots. The full normalized holdout archive, including warm-up, contained 1,840 unexplained slots and 32,496 modeled closure slots. The baseline had no fills in either period. Entry-audit verification confirmed each accepted experimental target stayed inside the pre-confirmation structural bound, reached at least net 2R, and had no nearer tick that also reached net 2R. The largest planned risk was $9.782 across both periods and cost scenarios. This is planned entry risk; stop gaps can still cause larger losses.

## Target and costs

For gross stop loss `L` from the actual next open and round-trip costs `C`, required gross reward is `2(L + C) + C`. The mode rounds the resulting target away from entry to the first eligible price tick and rechecks net 2R using replay arithmetic. It rejects the setup if the target would cross the structural boundary available at the confirmation candle's open. The target calculation uses the next candle's open only. Later range and close observations are used for execution, with the original stop-first and missing-data rules.

Base costs are $1.00 spread, $0.50 total slippage and a $0.25 fixed fee. The adverse scenario uses $2.00, $1.00 and $0.50, respectively, recalculating the target and entry decisions under those costs. Bid OHLC cannot resolve ask-only touches or true intrabar sequence. No Pivex contract terms or lot permissions are inferred.

## Reproduce

Use the [2025 archive and checksum](pivex-histdata-2025-study.md) and the [2024 HistData Generic ASCII M1 XAUUSD archive](https://www.histdata.com/download-free-forex-data/?/ascii/1-minute-bar-quotes/xauusd/2024). The holdout archive was acquired November 12, 2026 at 16:27:17 UTC. ZIP SHA-256 is `6d47f5cb269e0c4f35c63c7532713aae7dcf98901f605458b00dd6a69e7105de`. The extracted `DAT_ASCII_XAUUSD_M1_2024.csv` SHA-256 is `03dec44d8965c88eeba54e8ef5d13e31f28deca6f01fa727f9db55641bee5480`. Source quotes and full output remain outside Git. [Provider backtesting and format notes](https://www.histdata.com/f-a-q/)

```sh
node web/scripts/pivex-net-2r-study.mjs development /path/to/DAT_ASCII_XAUUSD_M1_2025.csv docs/pivex-histdata-2025-study.json /path/to/development.json
node web/scripts/pivex-net-2r-study.mjs holdout /path/to/DAT_ASCII_XAUUSD_M1_2024.csv docs/pivex-histdata-2024-holdout.json /path/to/holdout.json
```
