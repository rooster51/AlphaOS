"""Single-process deployment entry point: python -m alphaos_api."""
import os
from .config import load_secret_files


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
    import uvicorn
    # In-memory snapshot IDs require one worker/instance. Never log query strings.
    uvicorn.run('alphaos_api.app:app', host='0.0.0.0', port=port,
                workers=1, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
