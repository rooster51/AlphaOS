# Owner-private candle display and private probe

Status: **owner-private display implemented and fail-closed; deployment switch off
by default.** Public display, commercial use, redistribution, AI processing and
access by anyone other than the authenticated repository owner remain disabled.

This document is an engineering record, not legal advice. It records the exact
provider language reviewed on 2026-11-12 and the narrow interpretation implemented
in Phase C.

## Personal-use-first distinction

Public's June 2026 **Individual Trader API Program Terms and Conditions** and its
public API page describe a personal, non-commercial program. Those documents do
not use the words "website", "browser display", or "server-to-browser" in the
sections reviewed. The owner therefore cannot treat a general personal-use
statement as permission for public display or for every possible implementation.

| Use | What the documented terms support | AlphaOS decision |
| --- | --- | --- |
| Personal API use | §1(a) permits Applications "solely for their own personal use"; §1(c) says API access is "solely for Developer's own personal use"; §5(a) says API Keys are solely for the owner's use. | Allowed for the single-owner backend and research paths already in place. |
| Owner's own Application | §2(a) licenses use of the API to develop and use the Developer's Applications; §5(b) permits Data "solely through the operation of your Applications" for authorized purposes. | A single-owner AlphaOS web application is treated as the owner's Application, not a third-party product. |
| Authenticated browser display | The terms do not separately name a browser UI or a server-to-browser transfer. It can be read as operation of the owner's Application, but the wording is not explicit. | Implemented only as `owner_private_display`, restricted to one owner role. The deployment switch stays off by default. This is the unresolved interpretation. |
| Third-party software/systems | §1(c) prohibits making the Public Platform available "through any third-party or any third-party's software or systems"; §4(a)(x) and (xiii) prohibit offering services to third parties and distributing Public Property; §5(a) prohibits third-party API-key access. | No other accounts, no guest mode, no signed links, no embeddable/public endpoint, and no third-party data product. A viewer role is denied at the server boundary. |
| Public display | The public API page says the Individual API is for the owner's "own personal, non-commercial use"; §14 requires prior written approval to disseminate Market Data to third parties. | **Not authorized.** `public_display=false`; the chart bridge rejects a `public_display` response. |
| Redistribution | §14's final paragraph prohibits using the API to disseminate Market Data or other licensed information to third parties without Public's prior written approval; §4(a)(xiii) separately restricts distribution. | **Not authorized.** `redistribution=false`; no export or public endpoint. |
| Commercial use | The public API page describes the Individual API as personal and non-commercial. The agreement permits personal Applications, not a commercial data service. | **Not authorized.** `commercial_use=false`. |
| AI processing | The agreement does not grant an AI-processing or model-training right, and §5(b) limits Data to authorized purposes. | **Not authorized.** `ai_analysis=false`; no Gemini market-data processing. |

## Evidence reviewed

1. [Public Individual Trader API Program Terms and Conditions, June 2026](https://public.com/disclosures/individual-api-program)
   - **§1(a):** Public permits customers to develop software Applications
     "solely for their own personal use."
   - **§1(c) Own Use:** API access is "solely for Developer's own personal use."
     The Developer may not make the Public Platform available through "any
     third-party or any third-party's software or systems."
   - **§2(a):** the licence is to use the API "solely for the purposes of
     developing and using the Applications."
   - **§5(a):** API Keys are "solely for your own use"; no third party may be
     given access.
   - **§5(b):** Data may be accessed and used "solely through the operation of
     your Applications and for the purposes authorized under this Agreement."
   - **§14, final paragraph:** disseminating Market Data or other licensed
     information to third parties is prohibited without Public's prior written
     approval.
2. [Public API page](https://public.com/api): "The Public Individual API is for
   your own personal, non-commercial use. Unauthorized access is prohibited."

The owner reports that Public communicated that personal use is permitted. No
message identifier, written approval, or authorization reference naming an
authenticated AlphaOS website is stored in this repository. The code therefore
does **not** invent an authorization reference and does **not** claim that the
communication covers public or commercial display.

## Implemented entitlement

`owner_private_display` is a separate use context in
`modules/data_entitlements.py`. For Public:

- `private_research=true`
- `owner_private_display=true`
- `public_display=false`
- `commercial_use=false`
- `redistribution=false`
- `ai_analysis=false`
- `authorization_reference=null`

The owner-private decision does not require an authorization reference because it
is based on the documented own-use Application terms, not on a fabricated Public
approval. The provider capability reports the same narrow permission.

The server-side path is:

```text
owner website session (signed __Host- cookie, role=owner)
  -> /api/candles/{symbol} checks role before any backend call
  -> AlphaOS API receives X-AlphaOS-Data-Use: owner_private_display
  -> CandleService checks owner_private_display and returns that decision
  -> bridge requires use_context=owner_private_display and the capability
  -> private, no-store response
```

A valid session with any other role receives `403 owner_only`. Anonymous and
shared-link requests receive `401 authentication_required`. The browser never
receives `ALPHAOS_API_TOKEN`, and the owner-private header cannot be set by the
browser. The signed session format moves to version 2 with an explicit `owner`
role, so older v1 cookies are invalid and the owner must sign in again after
deployment.

The deployment switch remains:

```text
ALPHAOS_CANDLE_CHART_ENABLED=false
```

It must be set to `true` only in the single-owner deployment after the owner
records acceptance of the unresolved browser/website interpretation. The switch
is not an authorization by itself: the signed owner role and the provider
`owner_private_display` decision are still checked.

## Unresolved authorization questions

These are the reasons the deployment switch remains off by default:

1. The terms permit the owner's "Applications" but do not explicitly define
   whether a hosted multi-page website and its server-to-browser transfer are an
   Application rather than a "third-party software or system" under §1(c).
2. The owner's general personal-use communication does not name AlphaOS, the
   authenticated website, the server-to-browser flow, or the hosting providers.
3. Public has not confirmed whether the owner-only authentication boundary is
   sufficient, or whether it requires a separate written display approval.
4. Public has not confirmed attribution, retention, or recordkeeping requirements
   for browser display.
5. Any future non-owner account, shared session, public route, embed, export,
   commercial offering, or AI processing requires separate review.

If Public's answer is narrower than this implementation, the switch stays off or
the website scope must be reduced to match it.

## Private authenticated probe

`scripts/candle_display_probe.py` measures the exact browser-facing path:
website session -> authenticated Next.js bridge -> AlphaOS API -> Public provider.
It is read-only and bounded to SPY/QQQ at `1m`, `5m`, and `15m`, plus one quote
per symbol/interval.

It requires the returned entitlement context to be `owner_private_display`. A
`private_research` or `public_display` snapshot is reported as invalid rather than
silently accepted.

It uses only the signed owner website session. It never accepts, prints, or
stores `ALPHAOS_API_TOKEN` or any backend bearer token.

### Configuration

Set these only in the private shell running the probe:

```sh
export ALPHAOS_SITE_URL="https://<owner-private-alphaos-site>"
export ALPHAOS_WEBSITE_SESSION="<__Host-alphaos_session value>"
```

Do not put the session in source, a committed `.env`, command history, logs, or
the probe output. The probe refuses HTTP except for loopback development.

### Run

```sh
python -m scripts.candle_display_probe \
  --symbols SPY QQQ --intervals 1m 5m 15m
```

An optional `--output` path must be relative and inside the working tree.

### Measurements

For each symbol/interval the JSON report records:

- candle HTTP availability and safe error code;
- `data_age_seconds` from the newest candle timestamp;
- `snapshot_age_seconds` from `retrieved_at`;
- provider, snapshot ID, completeness, warnings, and last-bar state;
- returned/received/expected counts and missing-bar count;
- strictly increasing timestamps, interval alignment, latest-bar match, and
  retrieval-after-latest consistency;
- independent quote status, `ageSeconds`, and quote timestamps;
- `Cache-Control: private, no-store` on the website response.

Exit codes:

- `0`: all six symbol/interval requests are valid and all six quotes are fresh.
- `1`: partial availability, stale quotes, or invalid snapshots.
- `2`: configuration missing, authentication denied, owner-only denial, or
  `feature_disabled`.

The probe cannot bypass the feature flag. While the owner-private deployment is
not enabled it will report `feature_disabled`; that is the correct gate result,
not a reason to enable the route. It must not be run against production until the
owner has approved a read-only staging check and recorded acceptance of the
unresolved interpretation.

## Deployment boundary

- The AlphaOS API defaults to `private_research`. The website bridge explicitly
  requests `owner_private_display`; the API rejects public, commercial,
  redistribution, AI and unknown use contexts with `400 invalid_data_use`.
- The bridge requires an owner-role session and rejects viewer sessions,
  anonymous requests, and shared links before contacting the provider.
- The chart's independent current-quote route applies the same owner-role check.
- The browser never receives the backend token or an unrestricted provider URL.
- Candle and quote responses are `private, no-store` with `Vary: Cookie`; no
  public CDN or shared cache is permitted.
- No public, commercial, redistribution, other-user, or AI-analysis use is
  enabled.
