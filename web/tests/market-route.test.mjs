import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { POST } from "../src/app/api/research/market/route.ts";

test("validated ordinary research avoids stringify even with exponent-like archive hashes", async () => {
  setBackendConfig();
  const data={...envelope("SPY"),archive_hash:"e319e312e221e713e99",normal:1.25};
  globalThis.fetch=async()=>new Response(JSON.stringify(data));
  const original=Response.json;let calls=0;
  try {
    Response.json=(...args)=>{calls++;return original(...args);};
    const result=await POST(request({symbol:"SPY"}));
    assert.equal(result.status,200);assert.deepEqual((await result.json()).research,data);
    assert.equal(calls,0);
  }finally{Response.json=original;}
});

test("validated JSON wrapper preserves number normalization and all research fields", async () => {
  setBackendConfig();
  const literals = ["0", "-0", "-0.0", "-0e-5", "9007199254740993", "-9007199254740993",
    "1208925819614629174706176", "1.234567891234567e19", "1e400", "-1e-400",
    "-0." + "0".repeat(350) + "1", "0.1", "1e-12"];
  for (const literal of literals) {
    const raw = JSON.stringify({...envelope("SPY"),extra:{literal:0,unicode:"café λ <script>",text:"escaped \\\" braces }"}})
      .replace('"literal":0', '"literal":' + literal);
    globalThis.fetch = async () => new Response(raw, {headers:{"Content-Type":"application/json"}});
    const result = await POST(request({symbol:"SPY"}));
    assert.equal(result.status,200);
    assert.equal(result.headers.get("Cache-Control"),"no-store");
    assert.deepEqual(await result.json(), JSON.parse(JSON.stringify({research:JSON.parse(raw),verified_for_trading:false,source:"alphaos_research_api"})), literal);
  }
});

test("browser cancellation reaches only its upstream request with the existing deadline", async () => {
  setBackendConfig();
  const cancelled = new AbortController();
  const input = new Request("https://alphaos.example/api/research/market", {
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({symbol:"QQQ",research_mode:"historical"}),signal:cancelled.signal,
  });
  let observed;
  globalThis.fetch=async (_, options) => {
    const symbol=JSON.parse(options.body).symbol;
    if(symbol === "SPY") return Response.json(envelope("SPY"));
    observed=options.signal;
    return new Promise((_,reject)=>{
      options.signal.addEventListener("abort",()=>reject(options.signal.reason),{once:true});
      cancelled.abort(new DOMException("DO_NOT_LOG","AbortError"));
    });
  };
  const [abandoned,peer]=await Promise.all([POST(input),POST(request({symbol:"SPY"}))]);
  assert.equal(observed.aborted,true);
  assert.equal(abandoned.status,499);
  assert.deepEqual(await abandoned.json(),{status:"unavailable",code:"request_cancelled"});
  assert.equal(peer.status,200);
  assert.notEqual(abandoned.headers.get("X-AlphaOS-Request-ID"),peer.headers.get("X-AlphaOS-Request-ID"));
});

test("auto and exact manual width semantics survive the bridge; substituted widths fail closed", async () => {
  setBackendConfig();
  for (const symbol of ["SPY", "QQQ"]) for (const width of [undefined, null, 1, 2.5, 5]) {
    const payload = {symbol, ...(width !== undefined ? {width} : {})};
    globalThis.fetch = async (_, options) => {
      assert.deepEqual(JSON.parse(options.body), payload);
      const data = envelope(symbol);
      data.request.width = width ?? null;
      return Response.json(data);
    };
    assert.equal((await POST(request(payload))).status, 200);
    if (width !== undefined) {
      globalThis.fetch = async () => {
        const data = envelope(symbol); data.request.width = 7;
        return Response.json(data);
      };
      assert.equal((await POST(request(payload))).status, 502);
    }
  }
});

test("explicit near, monthly and long dates never accept a substituted expiration", async () => {
  setBackendConfig();
  for (const symbol of ["SPY","QQQ"]) for (const expiration of ["2030-01-02","2030-01-03","2030-01-04","2030-01-18","2031-01-17"]) {
    const data = envelope(symbol);
    data.request.expiration = data.research.expiration = data.research.research_session.expiration = expiration;
    globalThis.fetch = async (_,options) => {
      assert.equal(JSON.parse(options.body).expiration,expiration);
      return Response.json(data);
    };
    assert.equal((await POST(request({symbol,expiration}))).status,200);
    for (const place of ["request","research","session"]) {
      const bad = structuredClone(data);
      (place==="request" ? bad.request : place==="research" ? bad.research : bad.research.research_session).expiration = "2030-01-07";
      globalThis.fetch = async () => Response.json(bad);
      const response = await POST(request({symbol,expiration}));
      assert.equal(response.status,502);
      assert.equal((await response.json()).code,"response_schema_mismatch");
    }
  }
});

test("historical mode is explicit and preserves the full backend envelope for SPY and QQQ", async () => {
  setBackendConfig();
  for (const symbol of ["SPY", "QQQ"]) {
    for (const capital of [150, 300, 500, 1000]) {
      const data = envelope(symbol);
      data.request.research_mode = "historical";
      data.research.research_mode = "historical";
      data.research.archive.provider = "Public";
      data.research.archive.freshness = {age_seconds: 172800, max_age_seconds: null};
      globalThis.fetch = async (_, options) => {
        assert.deepEqual(JSON.parse(options.body), {symbol, research_mode:"historical", available_capital:capital});
        return Response.json(data);
      };
      const result = await POST(request({symbol, research_mode:"historical", available_capital:capital}));
      assert.equal(result.status, 200);
      const body = await result.json();
      assert.deepEqual(body.research, data);
      assert.equal(body.verified_for_trading, false);
    }
  }
});

test("historical requests cannot accept a current response or missing archive provenance", async () => {
  setBackendConfig();
  const data = envelope();
  for (const defect of ["mode", "age", "source"]) {
    const response = structuredClone(data);
    response.request.research_mode = "historical";
    response.research.research_mode = "historical";
    response.research.archive.provider = "Public";
    response.research.archive.freshness = {age_seconds:10000,max_age_seconds:null};
    if (defect === "mode") response.research.research_mode = "current";
    if (defect === "age") response.research.archive.freshness.age_seconds = -1;
    if (defect === "source") delete response.research.archive.provider;
    globalThis.fetch = async () => Response.json(response);
    const result = await POST(request({symbol:"QQQ",research_mode:"historical"}));
    assert.equal(result.status, 502);
    assert.equal((await result.json()).code, "response_schema_mismatch");
  }
  data.request.research_mode = "historical";
  data.research.research_mode = "historical";
  globalThis.fetch = async () => Response.json(data);
  assert.equal((await POST(request({symbol:"QQQ"}))).status, 502);
});

test("invalid research modes fail before any backend access", async () => {
  globalThis.fetch = async () => { throw new Error("Must not fetch"); };
  for (const research_mode of ["auto", "live", "", null, 42]) {
    assert.equal((await POST(request({symbol:"SPY",research_mode}))).status, 400);
  }
});

for (const [status, upstreamCode, expectedCode] of [
  [503, "archive_stale", "archive_stale"],
  [503, "archive_missing", "archive_missing"],
  [503, "archive_unavailable", "archive_unavailable"],
  [503, "api_not_configured", "backend_api_not_configured"],
  [500, "internal_error", "backend_internal_error"],
  [404, "not_found", "backend_endpoint_unavailable"],
  [429, "http_error", "backend_rate_limited"],
  [503, null, "backend_service_unavailable"],
]) {
  test(`upstream ${status}/${upstreamCode} has a safe specific website error`, async () => {
    setBackendConfig();
    globalThis.fetch = async () => upstreamCode
      ? Response.json({error:{code:upstreamCode,message:"sensitive diagnostic"}}, {status})
      : new Response("sensitive gateway page", {status});
    const response = await POST(request({symbol:"SPY"}));
    assert.deepEqual(await response.json(), {status:"unavailable",code:expectedCode});
  });
}

const originalToken = process.env.ALPHAOS_API_TOKEN;
const originalUrl = process.env.ALPHAOS_API_URL;
const originalFetch = globalThis.fetch;

function setBackendConfig(config = {}) {
  const token = Object.hasOwn(config, "token") ? config.token : "test-token";
  const url = Object.hasOwn(config, "url") ? config.url : "https://api.example.test";
  if (token === null) delete process.env.ALPHAOS_API_TOKEN;
  else process.env.ALPHAOS_API_TOKEN = token;
  if (url === null) delete process.env.ALPHAOS_API_URL;
  else process.env.ALPHAOS_API_URL = url;
}

function request(body) {
  return new Request("http://localhost/api/research/market", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

function envelope(symbol = "QQQ", status = "complete") {
  return {
    schema_version: "alphaos-interface-v2",
    request: { symbol },
    read_only: true,
    research: {
      version: "alphaos-run-market-v1",
      symbol,
      as_of: "2030-01-02T15:00:00+00:00",
      expiration: "2030-01-02",
      archive: {
        session_date: "2030-01-02",
        observation: { observed_at: "2030-01-02T15:00:00+00:00" },
        freshness: { age_seconds: 120, max_age_seconds: 600 },
      },
      research_session: {
        version: "opportunity-session-v1",
        symbol,
        status,
        candidates: status === "complete" ? [{ strategy_family: "call_debit_spread" }] : [],
        unavailable_routes: [],
      },
    },
    provenance: { source: "test" },
    caveats: [],
  };
}

afterEach(() => {
  if (originalToken === undefined) delete process.env.ALPHAOS_API_TOKEN;
  else process.env.ALPHAOS_API_TOKEN = originalToken;
  if (originalUrl === undefined) delete process.env.ALPHAOS_API_URL;
  else process.env.ALPHAOS_API_URL = originalUrl;
  globalThis.fetch = originalFetch;
});

test("forwards a valid authenticated JSON POST and preserves read-only response envelope", async () => {
  setBackendConfig();
  let upstreamRequest;
  globalThis.fetch = async (url, options) => {
    upstreamRequest = { url: new URL(url), options };
    const data = envelope();
    data.request.expiration = "2026-10-16";
    data.request.width = 7.5;
    data.research.expiration = "2026-10-16";
    data.research.research_session.expiration = "2026-10-16";
    return Response.json(data);
  };

  const response = await POST(request({
    symbol: "qqq", expiration: "2026-10-16", available_capital: 250,
    objective: "research context", width: 7.5,
  }));
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(upstreamRequest.url.toString(), "https://api.example.test/v1/research/market");
  assert.equal(upstreamRequest.options.method, "POST");
  assert.equal(upstreamRequest.options.headers.Authorization, "Bearer test-token");
  assert.equal(upstreamRequest.options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(upstreamRequest.options.body), {
    symbol: "QQQ", expiration: "2026-10-16", available_capital: 250,
    objective: "research context", width: 7.5,
  });
  assert.equal(body.research.schema_version, "alphaos-interface-v2");
  assert.equal(body.research.research.symbol, "QQQ");
  assert.equal(body.research.research.research_session.status, "complete");
  assert.equal(body.verified_for_trading, false);
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("upstream authentication failures do not leak response details", async () => {
  setBackendConfig();
  for (const status of [401, 403]) {
    globalThis.fetch = async () => new Response("Bearer secret backend detail", { status });
    const response = await POST(request({ symbol: "SPY" }));
    const body = await response.json();
    assert.equal(response.status, 502);
    assert.equal(body.status, "unavailable");
    assert.equal(body.code, status === 401
      ? "backend_authentication_required"
      : "backend_authentication_rejected");
    assert.equal(JSON.stringify(body).includes("secret"), false);
  }
});

test("invalid or malformed request bodies fail before contacting the backend", async () => {
  setBackendConfig();
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(envelope()); };

  for (const body of [
    "not-json",
    {},
    { symbol: "DIA" },
    { symbol: "QQQ", unexpected: true },
    { symbol: "SPY", expiration: "2026-02-30" },
    { symbol: "SPY", expiration: "0000-01-01" },
    { symbol: "SPY", available_capital: Number.NaN },
    ...[0, -1, "", "150", null, Infinity].map(available_capital => ({symbol:"SPY", available_capital})),
    { symbol: "SPY", width: 101 },
  ]) {
    const response = await POST(request(body));
    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), { error: "Invalid research request" });
  }
  assert.equal(calls, 0);
});

test("malformed upstream research envelopes fail closed", async () => {
  setBackendConfig();
  globalThis.fetch = async () => Response.json({ schema_version: "wrong", research: [] });

  const response = await POST(request({ symbol: "QQQ" }));
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), {
    status: "unavailable", code: "response_schema_mismatch",
  });
});

test("upstream symbol mismatch fails closed", async () => {
  setBackendConfig();
  globalThis.fetch = async () => Response.json(envelope("SPY"));

  const response = await POST(request({ symbol: "QQQ" }));
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), {
    status: "unavailable", code: "response_schema_mismatch",
  });
});

test("unavailable and no-candidate research states remain explicit and non-tradable", async () => {
  setBackendConfig();
  for (const status of [
    "no_candidate",
  ]) {
    const payload = envelope("QQQ", status);
    globalThis.fetch = async () => Response.json(payload);
    const response = await POST(request({ symbol: "QQQ" }));
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.research.research.research_session.status, status);
    assert.deepEqual(body.research.research.research_session.candidates, []);
    assert.equal(body.verified_for_trading, false);
  }
});

test("upstream errors and invalid JSON fail closed", async () => {
  setBackendConfig();
  globalThis.fetch = async () => Response.json(
    { error: { code: "archive_unavailable" } },
    { status: 503 },
  );
  const unavailable = await POST(request({ symbol: "QQQ" }));
  assert.equal(unavailable.status, 502);
  assert.deepEqual(await unavailable.json(), {
    status: "unavailable", code: "archive_unavailable",
  });

  globalThis.fetch = async () => new Response("{", {
    status: 200, headers: { "Content-Type": "application/json" },
  });
  const malformed = await POST(request({ symbol: "QQQ" }));
  assert.equal(malformed.status, 502);
  assert.deepEqual(await malformed.json(), {
    status: "unavailable", code: "response_schema_mismatch",
  });
});

test("missing or invalid backend configuration is unavailable without fetching", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return Response.json(envelope()); };

  setBackendConfig({ token: null });
  const missing = await POST(request({ symbol: "SPY" }));
  assert.equal(missing.status, 503);
  assert.deepEqual(await missing.json(), {
    status: "unavailable", code: "backend_not_configured",
  });

  setBackendConfig({ url: "http://api.example.test" });
  const invalid = await POST(request({ symbol: "SPY" }));
  assert.equal(invalid.status, 503);
  assert.deepEqual(await invalid.json(), {
    status: "unavailable", code: "invalid_backend_configuration",
  });
  assert.equal(calls, 0);
});

test("SPY archive research uses the same authenticated v2 response contract", async () => {
  setBackendConfig();
  globalThis.fetch = async () => Response.json(envelope("SPY"));
  const response = await POST(request({ symbol: "SPY" }));
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.research.request.symbol, "SPY");
  assert.equal(body.research.research.research_session.symbol, "SPY");
  assert.equal(body.research.research.research_session.candidates[0].strategy_family, "call_debit_spread");
  assert.equal(body.verified_for_trading, false);
});

test("archive freshness, backend rejection, timeout, and network errors stay distinguishable", async () => {
  setBackendConfig();
  for (const [upstreamCode, upstreamStatus, expected] of [
    ["archive_stale", 503, "archive_stale"],
    ["archive_missing", 503, "archive_missing"],
    ["archive_not_configured", 503, "archive_not_configured"],
    ["archive_research_unavailable", 422, "archive_research_unavailable"],
    ["archive_expiration_unavailable", 422, "archive_expiration_unavailable"],
  ]) {
    globalThis.fetch = async () => Response.json(
      { error: { code: upstreamCode } },
      { status: upstreamStatus },
    );
    const response = await POST(request({ symbol: "QQQ" }));
    assert.deepEqual(await response.json(), { status: "unavailable", code: expected });
  }

  globalThis.fetch = async () => { throw new DOMException("timeout", "TimeoutError"); };
  const timedOut = await POST(request({ symbol: "QQQ" }));
  assert.deepEqual(await timedOut.json(), {
    status: "unavailable", code: "backend_timeout",
  });

  globalThis.fetch = async () => { throw new TypeError("network unreachable"); };
  const unreachable = await POST(request({ symbol: "QQQ" }));
  assert.deepEqual(await unreachable.json(), {
    status: "unavailable", code: "backend_unreachable",
  });
});


test("consolidated historical economics and history diagnostics survive the website bridge", async () => {
  setBackendConfig();
  const data = envelope();
  const session = data.research.research_session;
  session.diagnostics = { history_loading: { status: "loaded", reason: null } };
  session.historical_comparison = { winner: null, groups: [] };
  session.holding_policy = { preference: "avoid_overnight_exposure" };
  session.candidates[0].research = {
    historical_economics: {
      eligible_for_consideration: false,
      intraday_economics: { expected_value_dollars: null },
      missing_reasons: ["intraday_entry_not_completed_session"],
    },
  };
  globalThis.fetch = async () => Response.json(data);
  const response = await POST(request({ symbol: "QQQ" }));
  const body = await response.json();
  assert.deepEqual(body.research, data);
  assert.equal(body.verified_for_trading, false);
});

for (const capital of [100,150,300,500,1000,2000,150.75]) {
  test(`forwards buying power ${capital} without altering backend research`, async () => {
    setBackendConfig();
    const expected = envelope("SPY");
    expected.request.available_capital = capital;
    expected.research.research_session.available_capital = capital;
    expected.research.research_session.excluded = [{reason:"exceeds_available_capital",required_capital:2500}];
    globalThis.fetch = async (_, options) => {
      assert.equal(JSON.parse(options.body).available_capital, capital);
      return Response.json(expected);
    };
    const result=await POST(request({symbol:"SPY",available_capital:capital}));
    assert.deepEqual((await result.json()).research,expected);
  });
}

test("website preserves exact fixed REST/MCP results across symbols and capital amounts", async () => {
  const { readFileSync } = await import("node:fs");
  const cases=JSON.parse(readFileSync(new URL("./fixtures/market-parity.json",import.meta.url),"utf8"));
  setBackendConfig();
  for (const fixture of cases) {
    globalThis.fetch=async (_,options) => {
      assert.deepEqual(JSON.parse(options.body),fixture.request);
      return Response.json(fixture.response);
    };
    const result=await POST(request(fixture.request));
    assert.equal(result.status,200);
    assert.deepEqual((await result.json()).research,fixture.response);
  }
});

test("candidate stage diagnostics and unclassified flags survive the REST bridge exactly for SPY and QQQ", async () => {
  const {readFileSync} = await import("node:fs");
  const cases = JSON.parse(readFileSync(new URL("./fixtures/candidate-diagnostics-parity.json", import.meta.url),"utf8"));
  setBackendConfig();
  for (const fixture of cases) {
    globalThis.fetch = async (_, options) => {
      assert.deepEqual(JSON.parse(options.body),fixture.request);
      return Response.json(fixture.response);
    };
    const response = await POST(request(fixture.request));
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.deepEqual(body.research, fixture.response);
    assert.equal(body.verified_for_trading, false);
    const session = body.research.research.research_session;
    assert.equal(session.opportunity_state.direction,"unknown");
    assert.deepEqual(session.strategy_routes.routes,[]);
    assert.equal(session.diagnostics.generated_count,2);
    assert.ok(session.diagnostics.pipeline.some(stage => stage.stage === "historical_evidence" && stage.output_count === 0));
    assert.ok(session.candidates.every(item => item.classification_supported === false));
  }
});
test("upstream failures record correlation/status without secrets and recover without retry",async()=>{
 setBackendConfig();const logs=[];const warn=console.warn;console.warn=v=>logs.push(JSON.parse(v));
 try {
  for(const status of [500,502,503,504]) {
   let sent;
   globalThis.fetch=async(_,options)=>{sent=options;return new Response("DO_NOT_LOG",{status,headers:{"Content-Type":"text/html"}});};
   const r=await POST(request({symbol:"QQQ",objective:"DO_NOT_LOG"}));
   assert.deepEqual(await r.json(),{status:"unavailable",code:"backend_service_unavailable"});
   const id=r.headers.get("X-AlphaOS-Request-ID");assert.match(id,/^[0-9a-f]{32}$/);
   assert.equal(sent.headers["X-AlphaOS-Request-ID"],id);
   const log=logs.at(-1);assert.equal(log.request_id,id);assert.equal(log.upstream_status,status);
   assert.equal(log.upstream_json,false);assert.equal(log.backend_correlated,false);
   assert.equal(log.upstream_code,"unrecognized_or_missing");assert.ok(log.elapsed_ms>=0);
  }
  globalThis.fetch=async(_,options)=>Response.json({error:{code:"secret_token",message:"DO_NOT_LOG"}},{status:503,headers:{"X-AlphaOS-Request-ID":options.headers["X-AlphaOS-Request-ID"]}});
  await POST(request({symbol:"SPY"}));assert.equal(logs.at(-1).backend_correlated,true);
  assert.equal(logs.at(-1).upstream_code,"unrecognized_or_missing");
  assert.ok(!JSON.stringify(logs).includes("DO_NOT_LOG"));assert.ok(!JSON.stringify(logs).includes("test-token"));assert.ok(!JSON.stringify(logs).includes("secret_token"));
  globalThis.fetch=async()=>Response.json(envelope());
  const recovered=await POST(request({symbol:"QQQ"}));assert.equal(recovered.status,200);
  assert.deepEqual(logs.map(log=>log.status),[502,502,502,502,502,200]);
  assert.equal(logs.at(-1).symbol,"QQQ");assert.equal(logs.at(-1).research_mode,"current");
  assert.equal(logs.at(-1).timeout_ms,12000);
  for(const field of ["fetch_headers_ms","response_body_ms","schema_validation_ms"]) assert.ok(logs.at(-1)[field]>=0);
 }finally{console.warn=warn;}
});
for(const status of [200,503]) {
 test(`response-body timeout after HTTP ${status} stays bounded and classified`,async()=>{
  setBackendConfig();const logs=[];const warn=console.warn;console.warn=v=>logs.push(JSON.parse(v));
  try {
   globalThis.fetch=async()=>({ok:status===200,status,headers:new Headers(),text:async()=>{throw new DOMException("DO_NOT_LOG","TimeoutError");},json:async()=>{throw new DOMException("DO_NOT_LOG","TimeoutError");}});
   const r=await POST(request({symbol:"SPY"}));assert.equal(r.status,502);assert.equal((await r.json()).code,"backend_timeout");
   assert.equal(logs[0].stage,"response_body");assert.equal(logs[0].upstream_status,status);
  }finally{console.warn=warn;}
 });
}
test("unresolved directional routes preserve exact backend stage truth",async()=>{
 const {readFileSync}=await import("node:fs");
 const fixture=JSON.parse(readFileSync(new URL("./fixtures/unsupported-routes-parity.json",import.meta.url),"utf8"));
 setBackendConfig();globalThis.fetch=async(_,options)=>{assert.deepEqual(JSON.parse(options.body),fixture.request);return Response.json(fixture.response);};
 const r=await POST(request(fixture.request));assert.equal(r.status,200);assert.deepEqual((await r.json()).research,fixture.response);
});


test("body AbortError is classified using the original 12000ms timeout signal",async()=>{
 setBackendConfig();const original=AbortSignal.timeout;const warn=console.warn;console.warn=()=>{};
 try {
  AbortSignal.timeout=ms=>{assert.equal(ms,12000);return AbortSignal.abort(new DOMException("private","TimeoutError"));};
  globalThis.fetch=async()=>({ok:true,status:200,headers:new Headers(),text:async()=>{throw new DOMException("private","AbortError");},json:async()=>{throw new DOMException("private","AbortError");}});
  const result=await POST(request({symbol:"SPY"}));assert.equal((await result.json()).code,"backend_timeout");
 }finally{AbortSignal.timeout=original;console.warn=warn;}
});


test("current bridge rejects unknown backend research modes without breaking legacy omission",async()=>{
 setBackendConfig();
 for(const mode of ["auto","live",null]) {
  for(const section of ["request","research"]) {
   const data=envelope();data[section].research_mode=mode;
   globalThis.fetch=async()=>Response.json(data);
   const r=await POST(request({symbol:"QQQ"}));assert.equal(r.status,502);assert.equal((await r.json()).code,"response_schema_mismatch");
  }
 }
 globalThis.fetch=async()=>Response.json(envelope());
 assert.equal((await POST(request({symbol:"QQQ"}))).status,200);
});

test("concurrent historical timeouts keep the 12000ms deadline, isolated correlation and sanitized diagnostics",async()=>{
 setBackendConfig();const originalTimeout=AbortSignal.timeout;const warn=console.warn;
 const logs=[];const sent=[];console.warn=value=>logs.push(JSON.parse(value));
 try {
  AbortSignal.timeout=ms=>{
   assert.equal(ms,12000);
   const controller=new AbortController();
   queueMicrotask(()=>controller.abort(new DOMException("DO_NOT_LOG","TimeoutError")));
   return controller.signal;
  };
  globalThis.fetch=async(_,options)=>{
   sent.push({id:options.headers["X-AlphaOS-Request-ID"],payload:JSON.parse(options.body)});
   return new Promise((resolve,reject)=>{
    if(options.signal.aborted) reject(options.signal.reason);
    else options.signal.addEventListener("abort",()=>reject(options.signal.reason),{once:true});
   });
  };
  const responses=await Promise.all(["SPY","QQQ"].map(symbol=>POST(request({symbol,research_mode:"historical"}))));
  assert.equal(new Set(sent.map(item=>item.id)).size,2);
  for(let index=0;index<responses.length;index++) {
   const response=responses[index];assert.equal(response.status,502);
   assert.deepEqual(await response.json(),{status:"unavailable",code:"backend_timeout"});
   const id=response.headers.get("X-AlphaOS-Request-ID");
   const log=logs.find(row=>row.request_id===id);
   assert.equal(log.symbol,index===0?"SPY":"QQQ");assert.equal(log.research_mode,"historical");
   assert.equal(log.stage,"fetch");assert.equal(log.timeout_ms,12000);
   assert.equal(sent.find(item=>item.id===id).payload.research_mode,"historical");
  }
  assert.equal(logs.length,2);assert.ok(!JSON.stringify(logs).includes("DO_NOT_LOG"));
  assert.ok(!JSON.stringify(logs).includes("test-token"));
 }finally{AbortSignal.timeout=originalTimeout;console.warn=warn;}
});
