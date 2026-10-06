import pytest
from alphaos_api.config import load_secret_files, SECRET_FILES


@pytest.fixture
def clean_env(monkeypatch):
    for key in SECRET_FILES:
        monkeypatch.setenv(key, '')
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_render_files_raw_and_assignment(tmp_path, clean_env):
    import os
    (tmp_path / 'ALPHAOS_API_TOKEN').write_text('ALPHAOS_API_TOKEN="test-only-token"\n')
    (tmp_path / 'PUBLIC_API_SECRET').write_text('test-only-public\n')
    (tmp_path / 'Public_Account').write_text('Public_Account=test-account')
    load_secret_files(tmp_path)
    assert os.environ['ALPHAOS_API_TOKEN'] == 'test-only-token'
    assert os.environ['PUBLIC_API_SECRET'] == 'test-only-public'
    assert os.environ['PUBLIC_ACCOUNT_NUMBER'] == 'test-account'


def test_environment_including_empty_wins(tmp_path, clean_env):
    import os
    clean_env.setenv('ALPHAOS_API_TOKEN', '')
    (tmp_path / 'ALPHAOS_API_TOKEN').write_text('unused-file-value')
    load_secret_files(tmp_path)
    assert os.environ['ALPHAOS_API_TOKEN'] == ''
    assert 'PUBLIC_API_SECRET' not in os.environ


def test_bad_file_never_echoes_contents(tmp_path, clean_env):
    (tmp_path / 'ALPHAOS_API_TOKEN').write_text('sensitive-value\nextra-line')
    with pytest.raises(RuntimeError, match='Invalid server secret configuration') as error:
        load_secret_files(tmp_path)
    assert 'sensitive-value' not in str(error.value)
