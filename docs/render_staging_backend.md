# AlphaOS staging research API on Render

`render.staging.yaml` defines a separate, read-only API service on the `web/research-api-integration` branch. It uses the existing Python API deployment entry point (`python -m alphaos_api`), the API-only dependency manifest, and `/health` as its process health check. It does not define, change, or deploy the production API or MCP service.

The blueprint allows a verified archive observation up to 24 hours old. Research remains dated to the archived observation and is not a live quote or actionable trading signal. Expired contracts and archive data outside this window continue to fail closed. Checksum, symbol/session identity, timestamps, and archive quality verification remain enforced by the existing archive reader.

## Render-managed secrets

Render prompts for these values when the staging blueprint is first created because each is declared with `sync: false`:

- `ALPHAOS_API_TOKEN` — staging API bearer token. Set the same staging-only value on the staging website as a server-side secret.
- `PUBLIC_API_SECRET` - Public provider credential for completed daily history; archive credentials do not authorize this provider.
- `PUBLIC_ACCOUNT_NUMBER` - explicit Public account selection (ID or number). The provider can select an account when omitted, but staging should use an explicit selection.
- `SUPABASE_URL` — private Supabase project URL for the existing archive.
- `SUPABASE_SERVICE_ROLE_KEY` — backend-only key used by the API's read-only archive path; never add it to the website service or client-visible variables.

Do not place secret values in this repository, blueprint, browser variables, or chat. The website staging service must have server-side `ALPHAOS_API_URL` set to the new API service URL and `ALPHAOS_API_TOKEN` set to the matching staging token. Do not use a `NEXT_PUBLIC_` name for either setting.

The custom blueprint path is `render.staging.yaml`; select that path when initializing the staging Blueprint. Service creation and secret configuration require an authorized Render operator. The free plan can sleep while idle, so allow for a cold start when checking the staging service.


## Daily-history recovery audit (2026-10-13)

The exact path is ArchiveResearchService._history -> get_public_research_bars
(FIVE_YEARS) -> _public_context -> configuration -> authenticated_context.
Absent PUBLIC_API_SECRET raises PublicProviderError(public_not_configured) before
constructing PublicApiClient, fetching accounts, refreshing auth or requesting
bars. The deployed service catches the exception and passes history=None to the
classifier. Commit 81ce3f1 already retains this fixed error code safely.

Once authenticated, fetch_research_bars uses the existing SDK transport:
`/userapigateway/historicdata/EQUITY/{symbol}/FIVE_YEARS/ONE_DAY`, no query params.
BarsResponse validates symbol, period and regularMarket.bars. Timestamp and OHLCV
become date/open/high/low/close/volume columns; _history adds symbol. Existing
coverage checks reject truncated/stale/coarse history, invalid OHLC and synthetic
leading fills. Classifier processing excludes unfinished sessions. No alternate
provider, shorter-history fallback or schema bypass is introduced.

The fix adds the two omitted sync:false declarations to this staging blueprint.
It supplies no values and has not been applied. Existing Render services will
still need an authorized operator to add their supported Public configuration;
editing this file does not populate secrets on an existing service. Do not copy
credentials to the website, repository or chat. Do not trigger an environment
restart/deploy without separate approval.

After approved configuration/deployment, verify history_loading is loaded and
classifier evidence has completed daily rows, then retry the original requests.
A loaded history need not produce a route or an affordable candidate. Unarchived
October 30 expiration remains a separate blocker; collector settings are unchanged.

Work is isolated on fix/release1-history-validation, stacked on PR #37; existing diagnostics are reused unchanged.
Do not push web/research-api-integration: the staging API auto-deploys that branch.
No production/Render settings, credentials or deployments were changed.

## Verified configuration blocker (2026-10-13)

Read-only Render inspection found PUBLIC_ACCOUNT_NUMBER present,
but the secret environment key is `Public_API_Secret`, not `PUBLIC_API_SECRET`.
A secret file named `Public_API_Secret` also exists. Values were never revealed.
On Render Linux the environment lookup is case-sensitive; the API does not read
that file. The required key remains unavailable, causing public_not_configured
before any historical-data HTTP request.

An authorized operator must configure the existing secret under exactly
`PUBLIC_API_SECRET` on the staging API, with separate approval for the resulting
restart/deployment. No account change is justified. Do not add aliases or read
arbitrary secret files. This PR declares canonical keys without values and tests
the Linux configuration contract even when tests run on Windows.

### Parity and remaining launch validation

Observed versions: staging API c2d4645afdf2da361a2b8df6e7fc78f1d1864563,
website 047428f12463f1bdb96c71002c9b3b9a34a9c368, production API/MCP
7f7ef53c85151711ef5fdc3c5d092a7a3e6d84cb. PR #36/#37 are not deployed.
The staging blueprint declares a 86400-second archive window; API default is
600 seconds. Effective masked values were not retrieved. Website and MCP route
equivalent inputs to ArchiveResearchService; local REST/OAuth MCP tests assert
identical results. Live parity remains unverified: staging returned no_candidate
with missing completed history; authenticated QQQ MCP returned archive_unavailable,
and SPY MCP requested authentication retry. These are separate evidence failures.

After approved configuration and staging release, test SPY capital 150/width 1,
and QQQ capital 300/widths 1 and 2 using actual archived expirations. Confirm
loaded completed history, provenance, classification, routing, candidate economics
and exclusion reasons. Compare MCP with matching code, inputs and valid evidence;
do not relax freshness. October 30 was outside the observed archive expirations.
No real candidate success or launch readiness is claimed before validation.

Latest repeated website requests (SPY 150/1, QQQ 300/1 and 300/2) returned HTTP
502 backend_timeout from the existing 12-second bridge deadline. This does not
establish which backend operation was slow and does not disprove the observed
configuration blocker. Do not extend the deadline speculatively. Recheck service
latency and archive access after authorized configuration/restart; earlier counts
of zero candidates are not current results for these timeout responses.

## Local validation

Python 3.12.14 focused history, API/MCP, router, session and run_market suite:
98 passed, 11 subtests passed. Website contract tests: 37 passed, zero failed.
Fixtures are synthetic regression evidence, not real SPY/QQQ market validation.

Full backend suite: 659 passed, 40 subtests passed (261.30s), zero failures.
Render Blueprint schema validation and git diff --check passed.
