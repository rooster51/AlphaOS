import { protectWebsite, type AuthBindings } from "../../src/lib/website-auth.ts";

type EdgeContext = {
  next(): Promise<Response>;
};

declare const Netlify: {
  env: {
    get(name: string): string | undefined;
  };
};

export default function authGate(request: Request, context: EdgeContext) {
  const bindings: AuthBindings = {
    ALPHAOS_API_URL: Netlify.env.get("ALPHAOS_API_URL"),
    ALPHAOS_API_TOKEN: Netlify.env.get("ALPHAOS_API_TOKEN"),
    ALPHAOS_PASSWORD_HASH: Netlify.env.get("ALPHAOS_PASSWORD_HASH"),
    ALPHAOS_SESSION_KEY: Netlify.env.get("ALPHAOS_SESSION_KEY"),
  };
  return protectWebsite(request, bindings, () => context.next(), { loginRateLimitHandledExternally: true });
}

export const config = {
  path: "/*",
};
