import assert from 'node:assert/strict';
import {test, afterEach} from 'node:test';
import {readFileSync} from 'node:fs';
import {POST} from '../src/app/api/research/market/route.ts';
import {validResearchSummary} from '../src/lib/research-summary.ts';
import {assessStrategyCandidates} from '../src/lib/strategy-opportunities.ts';

const full = JSON.parse(readFileSync(new URL('./fixtures/market-parity.json', import.meta.url)));
const summaries = JSON.parse(readFileSync(new URL('./fixtures/market-summary.json', import.meta.url)));
const originalFetch = globalThis.fetch;
const originalEnv = {...process.env};
afterEach(() => {globalThis.fetch = originalFetch; process.env = {...originalEnv};});
function setup() {
  process.env.ALPHAOS_API_URL = 'https://alphaos-api-staging.onrender.com';
  process.env.ALPHAOS_API_TOKEN = 'summary-fixture-secret';
}
function request(payload, signal) {
  return new Request('https://preview.test/api/research/market', {method:'POST', signal,
    headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
}
function input(item) {
  return Object.fromEntries(Object.entries(item.request).filter(([,value]) => value !== null));
}

test('golden backend summaries preserve every accepted candidate, eligibility and deterministic order', () => {
  for (const fixture of summaries) {
    const original = full[fixture.fixture_index].response;
    const summary = fixture.response;
    assert.equal(validResearchSummary(summary), true);
    const before = original.research, after = summary.research;
    assert.deepEqual(after.archive, before.archive);
    assert.deepEqual(after.research_session.candidates.map(row=>row.input_index), before.research_session.candidates.map(row=>row.input_index));
    assert.equal(after.research_session.excluded.length, before.research_session.excluded.length);
    const assess = envelope => assessStrategyCandidates(envelope.research.research_session,
      envelope.research.archive, envelope.request.symbol, envelope.request.available_capital,
      envelope.request.research_mode, envelope.research.as_of)
      .filter(row=>row.candidate.source_bucket === 'accepted')
      .map(row=>({index:row.candidate.input_index,status:row.status,reasons:row.reasons}));
    assert.deepEqual(assess(summary), assess(original));
    for (const field of ['ask_timestamp','bid','contract','archive_quality']) {
      const invalid = structuredClone(summary);
      const entries = invalid.research.research_session.candidates;
      if (!entries.length) continue;
      for (const entry of entries) for (const leg of entry.research.legs) delete leg[field];
      assert.ok(assess(invalid).every(row=>row.status !== 'eligible'));
    }
  }
});

test('summary bridge validates completeness and counts before returning any evidence', async () => {
  setup();
  for (const fixture of summaries) {
    const payload = {...input(full[fixture.fixture_index]), response_format:'summary-v1'};
    for (const defect of [null,'count','checksum','detail','format']) {
      const data = structuredClone(fixture.response), session = data.research.research_session;
      if (defect === 'count') session.transport.candidate_count++;
      if (defect === 'checksum') data.research.archive.storage.archive_sha256 = 'bad';
      if (defect === 'detail') session.transport.complete = false;
      if (defect === 'format') delete data.response_format;
      globalThis.fetch = async (url,options) => {
        assert.equal(new URL(url).pathname, '/v1/research/market');
        assert.equal(JSON.parse(options.body).response_format, 'summary-v1');
        return Response.json(data);
      };
      const response = await POST(request(payload));
      assert.equal(response.status, defect ? 502 : 200);
      if (defect) assert.equal((await response.json()).code, 'response_schema_mismatch');
    }
  }
});

test('compact summary bridge requires the requested version and preserves quote qualification', async () => {
  setup();
  const fixture = summaries[0];
  const original = fixture.response;
  const compact = structuredClone(original);
  compact.response_format = compact.research.research_session.transport.format = 'summary-v2';
  for (const row of compact.research.research_session.candidates) {
    for (const leg of row.research.legs) {
      delete leg.mid;
      delete leg.quote_timestamp;
      delete leg.observation_timestamp;
    }
    delete row.research.historical_economics.capital_requirement;
    delete row.research.historical_economics.capital_eligibility.basis;
  }
  const assess = envelope => assessStrategyCandidates(envelope.research.research_session,
    envelope.research.archive, envelope.request.symbol, envelope.request.available_capital,
    envelope.request.research_mode, envelope.research.as_of).map(({status, reasons}) => ({status, reasons}));
  assert.deepEqual(assess(compact), assess(original));

  const payload = {...input(full[fixture.fixture_index]), response_format:'summary-v2'};
  globalThis.fetch = async (_url, options) => {
    assert.equal(JSON.parse(options.body).response_format, 'summary-v2');
    return Response.json(compact);
  };
  assert.equal((await POST(request(payload))).status, 200);
  globalThis.fetch = async () => Response.json(original);
  assert.equal((await POST(request(payload))).status, 502);
});

test('detail bridge binds authenticated request, archive and whole-candidate reference', async () => {
  setup();
  const fixture = summaries.find(row=>row.response.research.research_session.candidates.length);
  const original = full[fixture.fixture_index], row = fixture.response.research.research_session.candidates[0];
  const payload = {...input(original), view:'candidate', detail:row.detail};
  const data = {schema_version:'alphaos-candidate-detail-v1', read_only:true,verified_for_trading:false,
    request:original.response.request,archive:original.response.research.archive,
    reference:row.detail,candidate:original.response.research.research_session.candidates[0],caveats:[]};
  for (const defect of [null,'candidate','archive','symbol']) {
    const value = structuredClone(data);
    if (defect === 'candidate') value.reference.candidate_sha256 = '0'.repeat(64);
    if (defect === 'archive') value.archive.storage.archive_sha256 = '0'.repeat(64);
    if (defect === 'symbol') value.request.symbol = value.request.symbol === 'QQQ' ? 'SPY' : 'QQQ';
    globalThis.fetch = async (url, options) => {
      assert.equal(new URL(url).pathname, '/v1/research/market/candidate');
      assert.equal(options.headers.Authorization, 'Bearer summary-fixture-secret');
      return Response.json(value);
    };
    assert.equal((await POST(request(payload))).status, defect ? 502 : 200);
  }
});

test('non-JSON upstream 429 is handled without promotion or leaking origin diagnostics', async () => {
  setup();
  const messages=[], warn=console.warn, log=console.log;
  console.warn=console.log=value=>messages.push(String(value));
  try {
    globalThis.fetch=async()=>new Response('PRIVATE_RATE_LIMIT_BODY', {status:429,
      headers:{'Content-Type':'text/html','server':'PRIVATE_SERVER'}});
    const response=await POST(request({symbol:'QQQ',available_capital:150,response_format:'summary-v1'}));
    assert.equal(response.status,502);
    assert.equal((await response.json()).code,'backend_rate_limited');
    const diagnostics=messages.join('\n');
    assert.match(diagnostics, /"backend_target":"staging"/);
    assert.match(diagnostics, /"backend_correlated":false/);
    assert.ok(!/PRIVATE_|summary-fixture-secret/.test(diagnostics));
  } finally {console.warn=warn;console.log=log;}
});
