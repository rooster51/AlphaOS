# Intraday archive on Render Cron

## Architecture and choice

GitHub remains source/CI. One standalone Render Python Cron Job runs the existing
`python -m scripts.run_intraday_snapshot` collector against Public and Supabase.
No research API, HTTP endpoint, worker daemon, local disk, or second provider is
needed. The repository contains no Render API service configuration to depend on.
Render Cron is simpler here than a VPS (patching/process management) or a separate
cloud scheduler/container stack. It bills active compute with a $1/month minimum;
actual cost depends on runtime and selected plan, not a guaranteed $1 total.
See https://render.com/docs/cronjobs and https://render.com/pricing.

## Setup / cutover (manual, not performed by this change)

1. Review and merge this branch into the intended production source branch through
   normal GitHub review/CI. Both archive Actions workflows are manual-only.
2. Apply `supabase/intraday_slot.sql` in the existing project's SQL editor.
   This additive migration adds a nullable slot column and unique index. Existing
   archives and observed timestamps are not rewritten or backfilled. The existing
   private `market-archive` bucket, tables and service-role permissions must remain.
3. In Render select New > Blueprint, connect `rooster51/AlphaOS`, select the reviewed
   branch, and use root `render.yaml`. Review the single Cron service and its billing.
   Alternatively create one Python Cron Job with build `pip install -r requirements-daily.txt`,
   schedule `*/5 13-21 * * 1-5`, and command
   `timeout --signal=TERM --kill-after=10s 240s python -u -m scripts.run_intraday_snapshot`.
4. Set secret environment variables in Render (not Git): `PUBLIC_API_SECRET`,
   `PUBLIC_ACCOUNT_NUMBER`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.
   These are runtime names, not the older GitHub secret aliases. Never paste values
   into logs, source, PRs or support messages. Python 3.12.10 is set by the blueprint.
5. Start at a new five-minute slot after disabling the old GitHub schedule. Do not
   run old collector code concurrently. Do not trigger Render manually while it is
   active: Render cancels the active run when a manual run starts.
6. Trigger once during a regular session. Verify exit success and one `archived` or
   `duplicate` line per symbol, database slot/observed timestamps, metadata count,
   and the gzip JSON in the private bucket. Trigger again within the same slot:
   expect duplicate skips, not new metadata or objects. Outside session expect a skip.
7. Enable Render failed-run notifications and review Runs regularly. Confirm 78
   complete metadata rows per symbol on a normal full trading day. Missing slots
   require investigation; this system does not manufacture historical snapshots.

## Schedule, timing and counts

The UTC heartbeat runs every five minutes on weekdays from 13:00 through 21:55,
covering US daylight and standard time. The existing NYSE calendar rejects
weekends, holidays, premarket, after-hours and times after early close. It runs
before authentication, again before options collection, and before snapshot write.
A 09:30–16:00 session has 78 eligible slots (09:30 through 15:55): 78 SPY + 78 QQQ
option snapshots = 156 total. A 13:00 early close has 42 per symbol. This is a
healthy-run target, not a delivery guarantee. Candle upserts are keyed by actual
one-minute bar time; candle row count is not the option-snapshot count.

`slot_time` is the floor of actual invocation time to the five-minute UTC slot.
A late invocation uses the then-current slot; missed slots are not backfilled.
`observed_at` is actual collection-start time, never replaced with slot time.
`collection_finished_at`, per-chain response timestamps and Public timestamps
remain in the raw payload. Sequential SPY/QQQ and expiration requests are not
simultaneous; provider quotes may themselves be delayed. Crossing market close
during collection prevents the options snapshot write.

## Duplicates, failures and recovery

Completed provider/symbol/slot metadata skips another collection. Candle upserts
retain the existing uniqueness key. Option objects use the deterministic slot
path and immutable upload. If upload fails because the object already exists
(or the first response was lost), download that exact object, validate its
identity, and finish metadata from its original payload/hash/timestamp. Concurrent
writers therefore converge on the first object. Database metadata is idempotent
by original observation identity, with additional unique provider/symbol/slot.
Metadata is read back before success. Database and Storage are not one transaction:
a crash can leave an object without metadata, recovered by another attempt in the
same active slot. After the slot expires, inspect/reconcile that object manually;
never overwrite it with later observations or relabel it as a historical quote.

Each symbol gets at most two attempts with a ten-second delay, only while its
original slot remains active. SPY failure does not prevent QQQ's attempt, but any
unresolved symbol returns exit 1. Partial/empty options are preserved for diagnosis
and cause failure; they are not silently marked complete or overwritten on retry.
The next scheduled tick samples its own current slot, not the prior failed slot.
Render's single-run guarantee prevents overlap within this service; immutable
Storage plus database uniqueness covers duplicates from other invocations too.
A four-minute process timeout plus ten-second kill grace prevents indefinitely
blocking later ticks. Timeout/nonzero exit must be treated as failure; Render
platform automatic retries are not assumed. Auth/database initialization errors
fail immediately; subsequent heartbeat tries again.

Logs include stage, symbol, error class and source location only; arbitrary
exception text (potentially containing credentials) is excluded. Keep the four
secrets in the trusted runtime and do not enable SDK HTTP debug logging.

## Rollback

Suspend/delete the Render Cron service to stop automatic collection. Keep the
legacy daily schedule disabled. Manual GitHub dispatch uses the updated collector
and requires the additive migration. Leaving the nullable slot column/index in
place is safe. Do not restore old slot-as-observed-time collector behavior.

## Validation limits

Automated fixture tests cover session gating, timestamps, duplicate storage
recovery, retries, partial failure and log redaction. Production Render deployment,
SQL migration, actual secret configuration and live post-cutover verification are
manual steps; no live Public/Supabase write is performed by the test suite.
