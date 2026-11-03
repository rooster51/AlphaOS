import { readFile, access } from "node:fs/promises";
import { resolve } from "node:path";

// Read-only validation for BOTH production and Preview artifacts. In particular,
// never use `cf deploy`, even with --dry-run, for Preview output.
const root = resolve(".cloudflare/output/v0");
const context = JSON.parse(await readFile(resolve(root, "config.json"), "utf8"));
if (typeof context.buildContext?.isPreview !== "boolean") throw new Error("Missing build context");
const worker = JSON.parse(await readFile(resolve(root, "workers/default/worker.config.json"), "utf8"));
if (worker.name !== "alphaos-web" || !worker.manifest?.mainModule) throw new Error("Invalid website Worker output");
const bundle = resolve(root, "workers/default/bundle");
const entry = resolve(bundle, worker.manifest.mainModule);
if (!entry.startsWith(bundle + "/") && !entry.startsWith(bundle + "\\")) throw new Error("Invalid Worker entry path");
await access(entry);
console.log(`Validated ${context.buildContext.isPreview ? "Preview" : "production"} Worker output without a deployment command.`);
