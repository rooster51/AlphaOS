import bcrypt from "bcryptjs";

export const SESSION_COOKIE = "__Host-alphaos_session";
export const SESSION_SECONDS = 30 * 24 * 60 * 60;
export type AuthBindings = {
  ALPHAOS_PASSWORD_HASH?: string;
  ALPHAOS_SESSION_KEY?: string;
  ALPHAOS_LOGIN_LIMITER?: { limit(input: { key: string }): Promise<{ success: boolean }> };
};
const utf8 = new TextEncoder();
const encode = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
function decode(value: string) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error("Invalid encoding");
  return Uint8Array.from(atob(value.replaceAll("-", "+").replaceAll("_", "/")), c => c.charCodeAt(0));
}
export function authConfigured(env: AuthBindings) {
  return /^\$2[aby]\$12\$[./A-Za-z0-9]{53}$/.test(env.ALPHAOS_PASSWORD_HASH ?? "")
    && /^[A-Za-z0-9_-]{43}$/.test(env.ALPHAOS_SESSION_KEY ?? "")
    && typeof env.ALPHAOS_LOGIN_LIMITER?.limit === "function";
}
async function key(env: AuthBindings) {
  // Changing either secret invalidates existing sessions.
  return crypto.subtle.importKey("raw", utf8.encode(`${env.ALPHAOS_SESSION_KEY}:${env.ALPHAOS_PASSWORD_HASH}`),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}
export async function issueSession(env: AuthBindings, origin: string, now = Date.now()) {
  const iat = Math.floor(now / 1000);
  const payload = encode(utf8.encode(JSON.stringify({ v: 1, iat, exp: iat + SESSION_SECONDS,
    aud: origin, nonce: encode(crypto.getRandomValues(new Uint8Array(32))) })));
  return `${payload}.${encode(new Uint8Array(await crypto.subtle.sign("HMAC", await key(env), utf8.encode(payload))))}`;
}
export async function validSession(request: Request, env: AuthBindings, now = Date.now()) {
  if (!authConfigured(env)) return false;
  try {
    const matches = (request.headers.get("cookie") ?? "").split(";").map(c => c.trim()).filter(c => c.startsWith(`${SESSION_COOKIE}=`));
    if (matches.length !== 1) return false;
    const token = matches[0].slice(SESSION_COOKIE.length + 1);
    if (token.length > 1024) return false;
    const [payload, signature, extra] = token.split(".");
    if (!payload || !signature || extra !== undefined) return false;
    if (!await crypto.subtle.verify("HMAC", await key(env), decode(signature), utf8.encode(payload))) return false;
    const data = JSON.parse(new TextDecoder().decode(decode(payload))), seconds = Math.floor(now / 1000);
    return data.v === 1 && data.aud === new URL(request.url).origin
      && Number.isSafeInteger(data.iat) && Number.isSafeInteger(data.exp)
      && data.iat <= seconds && data.exp > seconds && data.exp - data.iat === SESSION_SECONDS
      && typeof data.nonce === "string" && /^[A-Za-z0-9_-]{43}$/.test(data.nonce);
  } catch { return false; }
}
export function sessionCookie(token: string, now = Date.now()) {
  return `${SESSION_COOKIE}=${token}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=${SESSION_SECONDS}; Expires=${new Date(now + SESSION_SECONDS * 1000).toUTCString()}`;
}
function finish(response: Response) {
  const result = new Response(response.body, response);
  for (const [k, v] of Object.entries({ "Cache-Control": "private, no-store, max-age=0", "X-Robots-Tag": "noindex, nofollow", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin" })) result.headers.set(k, v);
  result.headers.append("Vary", "Cookie"); return result;
}
const failure = (code: string, status: number) => Response.json({ error: { code } }, { status });
function redirect(path: string, cookie?: string) {
  const response = new Response(null, { status: 303, headers: { Location: path } });
  if (cookie) response.headers.set("Set-Cookie", cookie); return response;
}
function loginPage(error = "", status = 200) {
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Sign In | AlphaOS</title><style>body{margin:0;min-height:100dvh;background:#090f1a;color:#e2e8f0;font:16px system-ui;display:grid;place-items:center}main{box-sizing:border-box;width:min(100%,26rem);padding:2rem}h1{font-size:1.6rem}label,input,button{display:block;box-sizing:border-box;width:100%}input,button{font:inherit;padding:.8rem;margin-top:.6rem;border-radius:.3rem}input{background:#111827;color:#fff;border:1px solid #64748b}button{background:#86efac;color:#052e16;border:0;cursor:pointer}p{min-height:1.5rem;color:#fca5a5}</style></head><body><main><h1>AlphaOS</h1><form method="post" action="/auth/login"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="72"><button type="submit">Sign In</button><p role="alert">${error}</p></form></main></body></html>`, { status, headers: { "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'" } });
}
async function readPassword(request: Request) {
  if (request.headers.get("content-type")?.split(";")[0].trim() !== "application/x-www-form-urlencoded") return null;
  const reader = request.body?.getReader(); if (!reader) return null;
  let text = "", size = 0; const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.byteLength; if (size > 2048) { await reader.cancel(); return null; }
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode(); const values = new URLSearchParams(text).getAll("password");
    return values.length === 1 && values[0] && utf8.encode(values[0]).length <= 72 ? values[0] : null;
  } finally { reader.releaseLock(); }
}
/** Gate runs before vinext, independent of Next.js rewrites, routing and process.env. */
export async function protectWebsite(request: Request, env: AuthBindings, next: () => Promise<Response>) {
  const run = async () => {
    const url = new URL(request.url), path = url.pathname;
    if (url.protocol !== "https:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
      if (!["GET", "HEAD"].includes(request.method)) return failure("https_required", 403);
      url.protocol = "https:"; return Response.redirect(url.toString(), 308);
    }
    if (path === "/robots.txt" && ["GET", "HEAD"].includes(request.method)) return new Response("User-agent: *\nDisallow: /\n", { headers: { "Content-Type": "text/plain" } });
    const unsafe = !["GET", "HEAD", "OPTIONS"].includes(request.method);
    if (path === "/login" && ["GET", "HEAD"].includes(request.method)) return await validSession(request, env) ? redirect("/market") : loginPage();
    const login = path === "/auth/login" && request.method === "POST";
    // APIs return 401 before CSRF validation when no valid session exists.
    const session = await validSession(request, env);
    if (!login && !session) return path.startsWith("/api/") ? failure("authentication_required", 401) : redirect("/login");
    // Required on login too: prevents login CSRF. No forwarded-host trust.
    if (unsafe && (request.headers.get("origin") !== url.origin || request.headers.get("sec-fetch-site") === "cross-site")) return failure("csrf_rejected", 403);
    if (login) {
      if (!authConfigured(env)) return loginPage("Sign in is not configured.", 503);
      try {
        // Single-user bucket also limits IP-rotating attempts per Cloudflare location.
        if (!(await env.ALPHAOS_LOGIN_LIMITER!.limit({ key: `alphaos-single-user-login-v1:${url.origin}` })).success) {
          const response = loginPage("Too many attempts. Try again later.", 429); response.headers.set("Retry-After", "60"); return response;
        }
      } catch { return loginPage("Sign in is temporarily unavailable.", 503); }
      const password = await readPassword(request);
      if (!password || !await bcrypt.compare(password, env.ALPHAOS_PASSWORD_HASH!)) return loginPage("Incorrect password.", 401);
      return redirect("/market", sessionCookie(await issueSession(env, url.origin)));
    }
    if (path === "/auth/logout" && request.method === "POST") return redirect("/login", `${SESSION_COOKIE}=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT`);
    return next();
  };
  try { return finish(await run()); } catch { return finish(failure("website_unavailable", 503)); }
}
