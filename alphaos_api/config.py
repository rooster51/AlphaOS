"""Load explicitly named Render secret mounts without logging their contents."""
import os
from pathlib import Path

SECRET_FILES = {
    'ALPHAOS_API_TOKEN': ('ALPHAOS_API_TOKEN',),
    'PUBLIC_API_SECRET': ('PUBLIC_API_SECRET',),
    'PUBLIC_ACCOUNT_NUMBER': ('PUBLIC_ACCOUNT_NUMBER', 'Public_Account'),
}


def load_secret_files(directory=Path('/etc/secrets')):
    """Environment wins; files may contain a raw value or NAME=value line."""
    for name, filenames in SECRET_FILES.items():
        if name in os.environ:
            continue
        for filename in filenames:
            path = Path(directory) / filename
            try:
                with path.open(encoding='utf-8-sig') as stream:
                    value = stream.read(16385).strip()
            except FileNotFoundError:
                continue
            except (OSError, UnicodeError):
                raise RuntimeError('Unable to read server secret configuration.') from None
            if len(value) > 16384 or '\n' in value or '\r' in value:
                raise RuntimeError('Invalid server secret configuration.')
            for key in (name, filename):
                if value.startswith(key + '='):
                    value = value[len(key) + 1:].strip()
                    break
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if value:
                os.environ[name] = value
            break
