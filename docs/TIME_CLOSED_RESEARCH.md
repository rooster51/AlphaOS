# SPY and QQQ time-closed research

Set `ALPHAOS_TIME_CLOSED_RESEARCH=true` only on an approved authenticated test backend. The default is off.

The trade-intelligence route uses two independent Public SDK DAY / FIVE_MINUTES reads with the process-local candle cache bypassed. The first read also feeds the existing strict signal calculation. The second request must start at least five seconds after the end of every included interval. Matching OHLCV, a contiguous NYSE regular-session prefix, acceptable freshness, and private-research entitlement are required. Two matched observations establish consistency at retrieval time. Provider finality remains unknown.

`provisional_research` contains the two observation times, last eligible bar start, count, provider, opening range from the first three bars, OHLC-typical-price VWAP, and SMA-seeded EMA 9. The workspace renders these values for owner sessions when the provider allows owner-private display. Setups, position exits, and option execution decisions do not consume provisional evidence. The MCP tool shares the REST path when AI analysis is entitled. Under the current Public policy it returns `data_use_denied`.

The API has a 3-second processing deadline and the website trade-intelligence request has a 3.5-second deadline. The website reuses the market snapshot ID and loads structure and trade intelligence concurrently. Provider calls that outlive the API deadline retain a bounded worker slot until they return. Admission and timeouts return controlled 503 and 504 responses. The optional trade-intelligence call can fail while market and structure evidence remain available.

## Live acceptance

During an NYSE regular session after 10:15:05 a.m. Eastern, inject the authorized Public API secret into the local test environment using the existing secret store. Set the preferred account only if account selection requires it. Keep tokens and raw payloads out of the evidence record.

1. Run `python -m scripts.market_data_probe --symbols SPY QQQ --intervals 5m --samples 2 --interval-seconds 0`.
2. Start an isolated local API with a locally generated REST token and the feature flag on. Record HTTP timings and statuses for cold and warm bearer-authenticated requests to `/v1/research/trade-intelligence/SPY` and `/v1/research/trade-intelligence/QQQ`, including parallel requests. Record both provider observation timestamps, bar counts, freshness and result reasons. Compare derived values against the observed five-minute prefix.
3. Use a local production website build pointed at that API. Sign in as owner and verify both symbols, provisional indicators, and WAIT behavior. Confirm a non-owner cannot receive the provisional payload. Leave the raw candle display flag off.
4. Keep the full dependency audit blocking. Issue #119 tracks the unpublished picomatch fix.

## Approval gates

Request approval before merging the reviewed PR, deploying its exact merged commit to the Render AlphaOS API, or enabling the production feature flag. Deploy with the flag off first, verify health and authentication, then request approval for opt-in and repeat the authenticated smoke tests. Keep Netlify Git builds stopped. A separately approved frontend release can publish a single verified local build through Netlify's manual deployment path. Roll back by disabling the feature flag and restoring the preceding approved deployment if the smoke checks fail.
