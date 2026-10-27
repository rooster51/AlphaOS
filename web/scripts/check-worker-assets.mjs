import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

// Inspect only public assets, never server bundles or runtime secret files.
const root = ".cloudflare/output/v0/workers/default/assets";
let checked = 0;
async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await inspect(path);
    else {
      const content = await readFile(path, "utf8");
      if (["ALPHAOS_API_TOKEN", "alphaos-build-only-credential-canary"].some(value => content.includes(value))) {
        throw new Error(`Server credential reference found in public asset: ${path}`);
      }
      checked++;
    }
  }
}
await inspect(root);
if (!checked) throw new Error("No public Worker assets found; build first.");
console.log(`Checked ${checked} public Worker assets for credential leakage.`);
