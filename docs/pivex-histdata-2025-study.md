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
