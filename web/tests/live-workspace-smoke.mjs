import assert from "node:assert/strict";
import { chromium } from "@playwright/test";
import { issueSession, SESSION_COOKIE } from "../src/lib/website-auth.ts";

// Next normalizes the loopback request origin to localhost.
const origin = "http://localhost:3000";
const cookie = await issueSession(process.env, origin);
const browser = await chromium.launch();

try {
  const owner = await browser.newContext();
  // Chromium accepts Secure cookies on loopback. Use the HTTPS URL for
  // cookie registration to satisfy the __Host- prefix requirement.
  await owner.addCookies([{
    name: SESSION_COOKIE, value: cookie, url: origin.replace("http:", "https:"),
    httpOnly: true, secure: true,
  }]);
  const page = await owner.newPage();
  await page.route("https://s.tradingview.com/**", (route) => route.abort());

  for (const symbol of ["SPY", "QQQ"]) {
    const path = `/api/market?symbol=${symbol}`;
    const [response] = await Promise.all([
      page.waitForResponse((result) => result.url() === origin + path && result.request().method() === "GET"),
      page.goto(`${origin}/workspace?symbol=${symbol}`),
    ]);
    assert.equal(response.status(), 200, `${symbol} website bridge status`);
    const result = await response.json();
    const evidence = result.trade_intelligence?.provisional_research;
    assert.equal(result.data.symbol, symbol);
    assert.equal(result.trade_intelligence?.state, "WAIT");
    if (!evidence) {
      const path = `/v1/research/trade-intelligence/${symbol}`;
      const direct = await fetch(new URL(path, process.env.ALPHAOS_API_URL), {
        headers: { Authorization: `Bearer ${process.env.ALPHAOS_API_TOKEN}` },
      });
      const directResult = await direct.json();
      const directEvidence = directResult.evidence?.provisional_research;
      const cookieSent = Boolean(await response.request().headerValue("cookie"));
      const quote = await owner.request.get(origin + `/api/current-quote?symbol=${symbol}`);
      const quoteResult = await quote.json();
      console.log(JSON.stringify({ symbol, cookieSent, ownerQuoteStatus: quote.status(),
        ownerQuoteCode: quoteResult.code, directStatus: direct.status, directCode: directResult.error?.code,
        directProvisional: directEvidence?.evidence, directReason: directEvidence?.reason,
        directDisplayAllowed: directEvidence?.owner_private_display_allowed }));
    }
    assert.equal(evidence?.evidence, "closed_by_time", evidence?.reason);
    assert.equal(evidence.actionable, false);
    assert.equal(evidence.owner_private_display_allowed, true);
    assert.ok(evidence.bar_count >= 9);
    assert.ok(evidence.opening_range && evidence.vwap > 0 && evidence.ema9 > 0);

    const heading = page.getByRole("heading", { name: "Provisional intraday research" });
    await heading.waitFor({ state: "visible" });
    const card = heading.locator("..");
    await card.getByText(/Long breakout .* WAIT/).waitFor();
    await card.getByText(/Short breakout .* WAIT/).waitFor();

    const anonymous = await fetch(origin + path);
    const anonymousResult = await anonymous.json();
    assert.ok(!anonymousResult.trade_intelligence?.provisional_research);
    console.log(JSON.stringify({ symbol, website_status: response.status(), state: "WAIT",
      provisional_bars: evidence.bar_count, indicators_visible: true, anonymous_payload_stripped: true }));
  }
} finally {
  await browser.close();
}
