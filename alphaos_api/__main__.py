"""Single-process deployment entry point: python -m alphaos_api."""
import os
import logging
from datetime import datetime
from importlib import import_module
from time import perf_counter
from zoneinfo import ZoneInfo
from .config import load_secret_files


def prepare_research_runtime():
    """Prepare static dependencies before readiness; perform no provider reads."""
    started = perf_counter()
    from modules.research_calendar import nyse_schedule
    today = datetime.now(ZoneInfo('America/New_York')).date()
    # Archive date validation and the regular-session gate use these same
    # package-defined schedules. No market observations enter this cache.
    for year in (today.year, today.year + 1):
        nyse_schedule(f'{year}-01-01', f'{year}-12-31')
    nyse_schedule(today, today)
    if os.environ.get('PUBLIC_API_SECRET'):
        try:
            import_module('public_api_sdk')
            import_module('modules.public_history')
        except ImportError:
            logging.getLogger('alphaos_api.runtime').warning('research_history_prepare_unavailable')
    if os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_SERVICE_ROLE_KEY'):
        from modules.supabase_archive import research_archive_client
        try:
            # HTTPX/TLS construction only. Archive reads remain request-local,
            # including all integrity and freshness checks.
            research_archive_client()
        except Exception:
            logging.getLogger('alphaos_api.runtime').warning('research_transport_prepare_unavailable')
    logging.getLogger('alphaos_api.runtime').warning(
        'research_runtime_prepared elapsed_ms=%s', round((perf_counter() - started) * 1000))


def main():
    load_secret_files()
    if not os.environ.get('ALPHAOS_API_TOKEN'):
        raise SystemExit('ALPHAOS_API_TOKEN must be configured before starting the server.')
    try:
        port = int(os.environ.get('PORT', '8000'))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit('PORT must be an integer from 1 to 65535.') from None
    prepare_research_runtime()
    import uvicorn
    # In-memory snapshot IDs require one worker/instance. Never log query strings.
    uvicorn.run('alphaos_api.app:app', host='0.0.0.0', port=port,
                workers=1, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
