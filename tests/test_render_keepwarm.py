"""Contract tests for the Render keep-warm heartbeat and its manual check.

The heartbeat itself is an external scheduler request, so the repository can only
pin the configuration it documents and the credential-free verification workflow.
"""
from pathlib import Path

WORKFLOW = Path('.github/workflows/backend-health-check.yml')
DOC = Path('docs/render_keepwarm.md')
WEB_DEPLOYMENT = Path('web/DEPLOYMENT.md')
HEALTH_URL = 'https://alphaos.onrender.com/health'


def test_health_check_is_manual_and_credential_free():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in text
    # Manual only: no native schedule, matching the repository's scheduler policy.
    assert '  schedule:' not in text and 'cron:' not in text
    # No credential of any kind reaches the workflow.
    assert 'secrets.' not in text
    assert 'Authorization' not in text
    assert 'ALPHAOS_API_TOKEN' not in text
    assert ' -H ' not in text
    assert HEALTH_URL in text
    assert '--max-time 60' in text
    assert 'if [ "$code" != "200" ]' in text
    assert 'timeout-minutes: 5' in text


def test_keepwarm_doc_records_job_spec_and_budget():
    doc = DOC.read_text(encoding='utf-8')
    assert 'cron-job.org' in doc
    assert HEALTH_URL in doc
    assert '*/10 12-21 * * 1-5' in doc
    # Cadence must beat the documented 15-minute sleep threshold.
    assert '15 minutes' in doc
    # Free instance hour math that bounds the schedule.
    assert '750' in doc and '744' in doc and '217 h/month' in doc
    # The paid alternative and its price stay visible.
    assert '$7/month' in doc
    assert 'Rollback' in doc
    assert 'no credential' in doc


def test_doc_brackets_both_dst_regimes_without_rescheduling():
    doc = DOC.read_text(encoding='utf-8')
    # Regular session in UTC under each regime; the fixed UTC window covers both.
    assert '13:30' in doc and '14:30' in doc
    assert '22:05' in doc
    # The two DST changes are named, and no reconfiguration is required.
    assert '2026-11-01' in doc and '2027-03-14' in doc
    assert 'no reconfiguration' in doc
    # Extended hours are explicitly out of scope for this window.
    assert 'Extended hours are **not** covered' in doc


def test_doc_records_awake_hour_accounting():
    doc = DOC.read_text(encoding='utf-8')
    assert '222 h/month' in doc          # window plus spin-down tail
    assert '520 h' in doc                # unused allowance in a 31-day month
    assert 'spun-down service consumes no instance hours' in doc


def test_web_deployment_points_at_keepwarm_doc():
    assert 'docs/render_keepwarm.md' in WEB_DEPLOYMENT.read_text(encoding='utf-8')
