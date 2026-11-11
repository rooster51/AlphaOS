// Offline only: deterministic generated fixtures, not vendor or broker records.
import { writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { backtestFixture } from "../src/lib/pivex/backtest-fixture.ts";
import { runBacktest } from "../src/lib/pivex/backtest.ts";
const directory = fileURLToPath(
  new URL("../../docs/pivex-upgrade-evidence/", import.meta.url),
);
mkdirSync(directory, { recursive: true });
const { dataset, config } = backtestFixture();
writeFileSync(
  directory + "synthetic-input.json",
  JSON.stringify({ dataset, config }, null, 2) + "\n",
);
writeFileSync(
  directory + "synthetic-result.json",
  JSON.stringify(runBacktest(dataset, config), null, 2) + "\n",
);
console.log(
  "Generated synthetic replay input and result in docs/pivex-upgrade-evidence; no market/account access.",
);
