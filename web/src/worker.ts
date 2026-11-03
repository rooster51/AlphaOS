import application from "vinext/server/fetch-handler";
import { protectWebsite } from "./lib/website-auth";

export default {
  fetch(request: Request, env: Cloudflare.Env, ctx: ExecutionContext) {
    return protectWebsite(request, env, () => application.fetch(request, env, ctx));
  },
};
