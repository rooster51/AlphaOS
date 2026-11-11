// Public TEST credentials, never real runtime configuration. No test bypass in app.
import { createHmac, randomBytes } from 'node:crypto';
export const password = 'test-only-alphaos-password-42';
export const authBindings = {
  ALPHAOS_PASSWORD_HASH: '$2b$12$E06IN5AWIp.Dnep75.KsDOhhciZNBaKKidKkydiYqnMo2lGBvBdYG',
  ALPHAOS_SESSION_KEY: 'test-only-session-key-' + '0'.repeat(21),
};
export function cookie(origin='https://website.test', now=Date.now()) {
  const iat = Math.floor(now/1000);
  const payload=Buffer.from(JSON.stringify({v:1,iat,exp:iat+2592000,aud:origin,nonce:randomBytes(32).toString('base64url')})).toString('base64url');
  const sig=createHmac('sha256',`${authBindings.ALPHAOS_SESSION_KEY}:${authBindings.ALPHAOS_PASSWORD_HASH}`).update(payload).digest('base64url');
  return `${payload}.${sig}`;
}
