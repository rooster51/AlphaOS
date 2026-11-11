# Pivex XAU/USD candle study

This external-proxy study uses HistData.com bid OHLC for gold in USD. The original symbol is `XAUUSD`. HistData documents the quote side, format and time zone but does not identify an underlying broker contract for this file. Its FAQ offers the files for backtesting. The study keeps the source quotes, status file and normalized candles outside Git. Redistribution rights were not verified. [Provider FAQ](https://www.histdata.com/f-a-q/) · [File specification](https://www.histdata.com/f-a-q/data-files-detailed-specification/)

## Reproduce

1. Use the provider's [free 2025 Generic ASCII XAUUSD M1 download](https://www.histdata.com/download-free-forex-data/?/ascii/1-minute-bar-quotes/xauusd/2025). The public download form supplied `HISTDATA_COM_ASCII_XAUUSD_M1_2025.zip`, acquired November 11, 2026 at 16:58:06 UTC. Save the ZIP and its contents outside the checkout.
2. Check the SHA-256 of the original artifacts.

| File | SHA-256 |
| --- | --- |
| ZIP | `dd0b4dc6983c07fafd89ba83b0c7f514aa16977654eaeb4c9fc8884ed359d98e` |
| `DAT_ASCII_XAUUSD_M1_2025.csv` | `1b302280d4f95f9c8ecdbb293e5659ca8a86eed314a7a061635f9f73fe96c2bc` |
| `DAT_ASCII_XAUUSD_M1_2025.txt` | `37e989d8594ca9a06c64fae57d7b48aaa1c3844e96f6f9b51423d427b974a52e` |

3. From the repository root, use the committed [study configuration](pivex-histdata-2025-study.json). Give the outputs new paths outside the repository.

```sh
node web/scripts/pivex-histdata.mjs /path/to/DAT_ASCII_XAUUSD_M1_2025.csv docs/pivex-histdata-2025-study.json /path/to/report.json /path/to/normalized.json
```

The last argument is optional. The report records the input hash, source basis and time zone, complete bar counts, all gap intervals and replay diagnostics. Git contains the study configuration and aggregate findings.

## Data quality and calendar

- The source uses fixed UTC−05:00 year-round. The adapter shifts timestamps to UTC, validates positive bid OHLC and the observed $0.001 quote grid, and groups the sorted observations into UTC-aligned half-open intervals. It rejects conflicting duplicates and invalid rows. The supplied file had one backward transition and 60 repeated minute records with identical OHLC.
- Observed coverage runs from 2025-01-01 23:00 UTC through 2025-12-31 21:57 UTC. There are 354,011 raw rows and 353,951 unique minutes across 312 UTC dates. That date count includes partial trading sessions.
- Five-minute candles require all five M1 children. M15 and H1 require three and twelve consecutive M5 candles. OHLC uses first open, max high, min low and last close. The import produced 70,759 M5, 23,560 M15 and 5,866 H1 candles. It excluded 156 observed minutes in incomplete M5 windows. No prices were filled in.
- The calendar is a research assumption. It applies the published 17:00–18:00 gold break and Friday-to-Sunday weekend pattern, testing fixed EST first and New York local hours second. It accepts a modeled closure only when no source minute overlaps it. At least one candidate conflicted with observations on 20 windows. No holiday overrides were assumed. The report classifies 32,484 five-minute slots as modeled closures and 1,877 slots in 52 intervals as missing or unexplained. Missing bars reset trend warm-up and can leave exposure unresolved. [Gold session reference](https://www.dukascopy.com/wiki/en/page/preview/?url=%2Fdevelopment%2Fdata-export%2Ftrading-sessions)

## Replay

The fixed split and costs were set before the first replay. Development starts January 1 at 05:00 UTC. Validation starts October 1 at 05:00 UTC and ends January 1, 2026 at 05:00 UTC. Partitions start flat with independent $10,000 equity. Earlier observations may warm the existing EMA and define pre-existing levels.

The study uses the existing 1H trend, 15M pullback and 5M confirmation rules. It models one ounce at the next contiguous bid open, with a $1.00 spread allowance, $0.50 round-trip slippage and $0.25 round-trip fees. The engine rechecks net 2:1 and a maximum $25 planned risk at entry. These allowances are research assumptions. Bid OHLC contains neither observed ask prices nor a tick sequence. All price-level tests use the bid range, so the model cannot detect ask-only stop or target touches or actual spread spikes. The fixed cost allowances do not establish real fill prices. A stop takes priority when both levels are touched in the same bar. An adverse stop gap uses the observed reopening bid. A missing open-market interval during exposure makes the position unresolved.

| Metric | Development | Validation |
| --- | ---: | ---: |
| Evaluated M5 candles | 53,096 | 17,663 |
| Qualified setups | 16 | 5 |
| Rejected at next-open geometry, cost or risk check | 15 | 5 |
| Missing contiguous next bar | 1 | 0 |
| Completed trades | 0 | 0 |
| Unresolved trades | 0 | 0 |
| Net modeled P&L from completed trades | $0 | $0 |
| Win rate, expectancy, profit factor, drawdown and loss streak | Unavailable | Unavailable |

Neither partition terminated early. Both have incomplete market coverage. Session-level trade statistics are empty. The combined entry-rejection diagnostic does not identify which individual constraint rejected each setup. Zero completed trades leave performance and statistical edge unmeasured. The validation period was used once with the same strategy and assumptions as development.

## Other sources

The HistData archive supplied a full calendar year at no charge. GetData offered a public evaluation sample and listed its full archive as purchaser-only. The reviewed Hugging Face mirror listed a Creative Commons license but lacked enough upstream feed and time-zone detail to prefer it over the provider download. [GetData archive](https://getdata.finance/datasets/xauusd) · [Hugging Face dataset card](https://huggingface.co/datasets/Pcitycrypto/xauusd)

## Development entry audit

The diagnostic rerun used the same source CSV and SHA-256, frozen study configuration, entry rules and costs. It evaluated only January–September. The original development metrics matched the previous run. The five October–December setups and zero fills remain the frozen validation result. The diagnostic command excludes that partition from normalization and replay.

```sh
node web/scripts/pivex-histdata.mjs --development-only /path/to/DAT_ASCII_XAUUSD_M1_2025.csv docs/pivex-histdata-2025-study.json /path/to/development-entry-audit.json
```

The JSON includes an `entryAudit` row for each of the 16 development setups and the `entryRejections` aggregate. Each row records the confirmation and next-open prices, stop, execution and structural targets, gross and net reward/risk, dollar risk, cost components and rejection reasons. The per-setup output stays outside Git with the source-price data.

| Rejection reason | Applicable | Primary |
| --- | ---: | ---: |
| Insufficient net reward/risk | 15 | 15 |
| Missing contiguous next candle | 1 | 1 |
| Invalid stop geometry | 0 | 0 |
| Invalid target geometry | 0 | 0 |
| Planned risk above $25 | 0 | 0 |
| Invalid or nonfinite economics | 0 | 0 |
| Planned risk above configured budget or available equity | 0 | 0 |

Primary priority is missing next candle, invalid economics, invalid stop geometry, invalid target geometry, insufficient net reward/risk, the $25 cap, then a lower budget or equity limit. Applicable counts can overlap. Reward/risk requires valid stop and target geometry. Planned risk requires a valid stop. The June 16 confirmation at 22:00 UTC coincided with the start of a modeled one-hour closure. It had no contiguous next open.

### Ranked explanation

1. **The gross 2R target leaves too little room for costs.** The strategy sets a target at exactly 2R from the confirmation close. At the contiguous next opens, gross reward/risk ranged from 1.903R to 2.173R. Seven of 15 were already below 2R before costs. After the fixed $1.75 round-trip charge at one modeled ounce, every result fell below 2R, ranging from 0.757R to 1.325R.
2. **Sizing cannot fix the shortfall under the existing assumptions.** One-ounce planned risk ranged from $4.00 to $8.03. For quantity `q`, gross dollar reward and risk per ounce `R` and `L`, proportional cost `c=$1.50` per ounce and fixed fee `F=$0.25`, net 2R requires `q(R−2L−3c) ≥ 3F`. The largest observed `R−2L` was $0.39 per ounce, below the $4.50 needed to cover proportional costs alone. The feasible positive size range is empty for all 15 priced setups, even before imposing `q ≤ (25−F)/(L+c)`. Quantities here are modeled ounces. Pivex lot sizes, increments and permissions were not assumed.
3. **One setup was unavailable for execution.** The missing next candle accounts for the remaining development rejection. The replay did not substitute the reopening price.

### Separate proposal

Test a target that covers net 2R from the actual hypothetical entry, only when that target fits inside the pre-existing structural level. Preserve confirmation rules, stop placement, costs, fixed size and the $25 limit in that experiment. At one modeled ounce, the required target distance was $4.86–$5.85 per ounce farther than the existing target in the trade direction. The already-observed structural level left that much room for 12 of the 15 priced setups. This is a distance check. It does not establish fills or performance. If the proposal is pursued, treat all 2025 observations as development and use a genuinely new, unseen holdout for independent validation.
