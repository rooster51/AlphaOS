"""Fixed synthetic storage -> actual REST/OAuth MCP -> website fixture contract."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from tests.test_research2_api import boundary, post, repack
from test_mcp_api import login, call

CASES = json.loads((Path(__file__).parents[1] / 'web/tests/fixtures/market-parity.json').read_text())


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
def test_website_fixture_matches_actual_rest_and_mcp(boundary, case):
    client, storage, _, _ = boundary
    prepare_storage(storage, case['request']['symbol'])
    response = post(client, 'market', case['request'])
    assert response.status_code == 200
    assert response.json() == case['response']
    _, tokens = login(client)
    result = call(client, tokens['access_token'], 'run_market', case['request'])
    assert not result.get('isError')
    assert result['structuredContent'] == case['response']
