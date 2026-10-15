"""Fixed synthetic storage -> actual REST/OAuth MCP -> website fixture contract."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
from tests.test_research2_api import boundary, post, repack
from test_mcp_api import login, call

CASES = json.loads((Path(__file__).parents[1] / 'web/tests/fixtures/market-parity.json').read_text())


def expected_fixture(value):
    """Allow only floating-point reduction noise in realized volatility."""
    if isinstance(value, dict):
        return {
            key: pytest.approx(item, rel=1e-12, abs=0)
            if key in ('realized_vol_20d', 'realized_vol_60d') and isinstance(item, float)
            else expected_fixture(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [expected_fixture(item) for item in value]
    return value


def test_fixture_tolerance_is_limited_to_volatility_roundoff():
    expected = expected_fixture({'nested': [{'realized_vol_20d': 0.003039032495217601,
                                           'realized_vol_60d': 0.011710562922675643}],
                                 'available_capital': 150.0})
    actual = {'nested': [{'realized_vol_20d': 0.00303903249521761,
                          'realized_vol_60d': 0.011710562922675659}],
              'available_capital': 150.0}
    assert actual == expected
    actual['available_capital'] = 150.000000000001
    assert actual != expected
    actual['available_capital'] = 150.0
    actual['nested'][0]['realized_vol_20d'] += 1e-10
    assert actual != expected


def prepare_storage(storage, symbol):
    if symbol == 'SPY':
        storage.payload = json.loads(json.dumps(storage.payload).replace('QQQ', 'SPY'))
        storage.row['symbol'] = symbol
        storage.row['archive_path'] = storage.row['archive_path'].replace('QQQ', 'SPY')
    options = storage.payload['options']
    rows = deepcopy(options['valid_contracts'])
    for expiration in ('2030-01-03', '2030-01-04'):
        options['requested_expirations'].append(expiration)
        for original in rows:
            row = deepcopy(original)
            row['expiration'] = expiration
            row['contract'] = row['contract'].replace('300102', expiration[2:].replace('-', ''))
            options['valid_contracts'].append(row)
    repack(storage)

@pytest.mark.parametrize('case', CASES, ids=['spy150','spy500','qqq1dte','qqqweekly','spyweekly'])
@pytest.mark.parametrize('gzip_os', [3, 10], ids=['linux-gzip', 'windows-gzip'])
def test_website_fixture_matches_actual_rest_and_mcp(boundary, case, gzip_os):
    client, storage, _, _ = boundary
    prepare_storage(storage, case['request']['symbol'])
    # Python 3.12 gzip.compress(mtime=0) delegates the OS header byte to zlib.
    # Exercise both platforms; the archive reader must verify the actual bytes.
    raw = bytearray(storage.raw)
    raw[9] = gzip_os
    storage.raw = bytes(raw)
    checksum = hashlib.sha256(storage.raw).hexdigest()
    storage.row['archive_sha256'] = checksum
    expected = deepcopy(case['response'])
    expected['research']['archive']['storage']['archive_sha256'] = checksum
    response = post(client, 'market', case['request'])
    assert response.status_code == 200
    assert response.json() == expected_fixture(expected)
    _, tokens = login(client)
    result = call(client, tokens['access_token'], 'run_market', case['request'])
    assert not result.get('isError')
    assert result['structuredContent'] == response.json()
