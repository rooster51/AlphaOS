# External heartbeat, GitHub collector execution

External scheduler -> GitHub workflow_dispatch -> existing AlphaOS collector ->
Public -> existing Supabase Postgres and private Storage. GitHub remains source,
CI, execution environment, collector secret store and run history. No API server,
collector endpoint or second market-data implementation is needed.

## Selected scheduler: cron-job.org

Use one hosted HTTP cron job. It supports free minute-level schedules, POST bodies
and custom headers, so no scheduler code or cloud runtime is required.
References: https://cron-job.org/en/faq/ and https://cron-job.org/en/ .
Only a GitHub dispatch credential resides there. Public and Supabase secrets stay
in GitHub. GitHub Actions usage limits/billing still apply; a free heartbeat does
not make private-repository runner minutes free. Neither dispatch nor Actions
runner startup guarantees execution at an exact wall-clock instant.

## Manual setup (not executed by this PR)

1. Review PR #14 and CI. Apply `supabase/intraday_slot.sql` in the existing
   project's SQL editor before enabling the updated workflow. It adds a nullable
   slot_time column and a unique provider/symbol/slot_time index for non-NULL slots.
   Legacy observations remain unchanged with NULL slot_time; no backfill.
2. Merge the reviewed PR when ready. The scheduler targets main, not this draft
   branch. Verify `.github/workflows/intraday-archive.yml` exists on main and
   supports workflow_dispatch. Keep both archive workflows without schedule.
3. Keep these existing GitHub repository secret aliases and runtime mappings:

   | GitHub secret | Collector environment |
   | --- | --- |
   | PUBLIC_API | PUBLIC_API_SECRET |
   | PUBLIC_ACCOUNT | PUBLIC_ACCOUNT_NUMBER |
   | SUPABASE_URL | SUPABASE_URL |
   | SUPABASE_API | SUPABASE_SERVICE_ROLE_KEY |

4. Create an expiring fine-grained GitHub PAT owned by an account with access to
   rooster51/AlphaOS. Select only this repository, Repository permissions Actions:
   Read and write (Metadata read is automatic), no Contents write or other extra
   permissions. Obtain organization approval if required. Actions write is GitHub's
   minimum dispatch permission; GitHub does not offer a token restricted to just
   this one workflow/dispatch operation. It can perform other Actions write
   operations in the selected repo, so treat the scheduler account as trusted.
   Do not use a broad classic repo token. Do not put any token in source, URLs,
   issue comments, screenshots or logs. Set an expiry reminder and rotate it.
5. Create an initially disabled cron-job.org job with timezone UTC. Custom schedule:
   minutes 0,5,10,...,55; hours 13 through 21 inclusive; Monday through Friday;
   all days of month and months. Equivalent cron: `*/5 13-21 * * 1-5`.
6. Configure the following HTTP request in the scheduler's protected settings:

   Method: POST
   URL: https://api.github.com/repos/rooster51/AlphaOS/actions/workflows/intraday-archive.yml/dispatches
   Headers:
   - Accept: application/vnd.github+json
   - Authorization: Bearer <fine-grained token, entered only in scheduler settings>
   - X-GitHub-Api-Version: 2022-11-28
   - Content-Type: application/json
   - User-Agent: AlphaOS-intraday-heartbeat

   Body exactly: `{"ref":"main"}`

   Reference: https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
   HTTP 204 means accepted, not successful collection. Do not log request headers
   or publish request/response history. Use failure/recovery notifications. Check
   scheduler auto-disable behavior after repeated failures; monitor credential
   expiry and 401/403/404/422 responses. Never add Public/Supabase secrets here.
7. Test once after migration/merge, verify a workflow_dispatch run on main in
   GitHub Actions, then enable the scheduler. Enable GitHub failed-workflow
   notifications separately; scheduler success cannot see collector failure.
   Do not deploy/enable anything as part of this draft PR review.

## Cadence, actual time and authoritative gate

The UTC window covers NYSE regular hours in EST and EDT. Python's existing NYSE
calendar is authoritative: weekends, holidays, premarket, after-hours and
post-early-close calls skip without authentication. The collector gates again
before options collection and before writing a snapshot after market close.

Slot time is the deterministic five-minute floor of actual collector invocation,
not the scheduler's nominal fire time. Actual observed_at, collection_finished_at,
per-chain responses and Public quote timestamps remain separate. A late job
collects the current slot only; it never pretends to observe a missed past slot.
Sequential symbols/expirations are not simultaneous; Public may return delayed
quotes. Collection crossing session close will not write an options snapshot.

09:30 through 15:55 ET gives 78 slots per symbol: 78 SPY + 78 QQQ = 156 option
snapshots on a healthy full day. A 13:00 early close gives 42 per symbol. Targets
are not guarantees. One-minute candle rows are separate, upserted by bar time.

## Concurrency, duplicates and interruption

A fixed GitHub concurrency group with cancel-in-progress: true makes newer
heartbeats supersede old runs rather than accumulate old jobs. It can interrupt
an active collection, including when a duplicate dispatch arrives. This favors
fresh work over waiting. GitHub cancellation is not an instantaneous distributed
lock: Supabase/Storage idempotency remains authoritative. The collector command
has a 240-second timeout plus 10-second kill grace; the job has a 12-minute limit
including dependency setup. Pip caching reduces startup cost. A canceled or
runner-delayed run can leave a gap; the scheduler is not a real-time guarantee.

Complete provider/symbol/slot metadata skips duplicate collection. Immutable
Storage paths are slot-based. Collision recovery downloads the first stored
payload, validates identity and writes metadata using that original observation
time and hash. Database read-after-write verification is retained. Simultaneous
or repeated invocations converge on the first stored snapshot; none overwrites
raw data. Candles retain their existing unique upsert key.

Database and Storage are not one transaction. A cancellation after upload can
leave an object without metadata. Another attempt in the same active slot can
recover it; after that slot, reconcile the immutable object manually with its
original timestamps/hash. Never recollect later and label it as historical data.

## Failure, verification and missing slots

Each symbol gets two attempts with a 10-second delay while the original slot is
active. SPY failure still permits a QQQ attempt; unresolved failure returns exit 1.
Partial/empty option snapshots remain archived for diagnosis and produce failure,
including on duplicate checks. They are not overwritten by retries. Authentication
or database initialization failure exits immediately. Timeout/cancellation is not
success. Exception logs expose stage/type/location, never arbitrary error text.

Verify both layers: scheduler HTTP acceptance, then GitHub run status and logs.
Expect per-symbol archived/duplicate lines or an explicit closed-session skip.
Verify option_snapshots fields slot_time, observed_at, quality_status,
contract_count, archive_path and archive_sha256 against the private gzip object.
The existing full-chain payload/provenance is unchanged.

To identify gaps, use the existing NYSE calendar/session gate to enumerate the
actual day's eligible UTC five-minute slots (respect DST and early close). Compare
those slots for each SPY/QQQ against option_snapshots filtered to provider Public,
session_date and non-NULL slot_time. Missing rows and non-complete quality are
separate failures. Do not infer completeness from total count alone or include
legacy NULL slots in the new-slot count. Inspect matching Actions run failures,
cancellations, queue/start times and scheduler logs. Record missing slots in the
validation report; never manufacture backfill. This PR does not add an automated
gap-monitoring service.

For a transient failure in the current active slot, manually dispatch the same
workflow on main (beware it cancels an active run). For old gaps, retain the gap,
inspect orphan objects, and reconcile only existing observations. Repair expired
GitHub credentials in scheduler settings; repair collector credentials only in
GitHub repository secrets. Re-enable a scheduler disabled by repeated HTTP errors.

## Rollback and scope

Disable the external job and revoke its GitHub credential to stop automatic
collection. Keep manual workflow dispatch available and both native schedules
absent. Leave the additive nullable Supabase column/index in place. Do not roll
back to slot-as-observation timestamps. No migration, credential creation,
scheduler deployment or production write is performed by this implementation.
