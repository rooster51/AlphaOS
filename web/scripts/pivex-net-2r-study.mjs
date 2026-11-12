import { readFile, writeFile } from "node:fs/promises";
import { prepareHistDataGold } from "../src/lib/pivex/histdata-history.ts";
import {
  runProxyDevelopment,
  runProxyHoldout,
} from "../src/lib/pivex/proxy-history.ts";

const [period, csv, manifestPath, output] = process.argv.slice(2);
if (
  !["development", "holdout"].includes(period) ||
  !csv ||
  !manifestPath ||
  !output ||
  process.argv.length !== 6
)
  throw Error(
    "Usage: node web/scripts/pivex-net-2r-study.mjs development|holdout source.csv manifest.json report.json",
  );

const frozen = JSON.parse(
  await readFile(
    new URL("../../docs/pivex-histdata-2025-study.json", import.meta.url),
    "utf8",
  ),
);
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
const config = {
  ...frozen.replay,
  from: manifest.replay.from,
  splitAt: manifest.replay.splitAt,
  to: manifest.replay.to,
};
const development = period === "development";
const bounds = development
  ? { ...manifest.source, to: config.splitAt }
  : manifest.source;
const dataset = prepareHistDataGold(await readFile(csv), bounds);
const run = development ? runProxyDevelopment : runProxyHoldout;
const baseline = run(dataset, { ...config, targetMode: "baseline" });
const experiment = run(dataset, { ...config, targetMode: "net_2r_structure" });
const adverse = run(dataset, {
  ...config,
  targetMode: "net_2r_structure",
  spreadFloor: 2 * config.spreadFloor,
  roundTripSlippage: 2 * config.roundTripSlippage,
  roundTripFees: 2 * config.roundTripFees,
  costsReference:
    "Predeclared adverse scenario: twice the base spread, slippage and fixed fees.",
});
await writeFile(
  output,
  JSON.stringify({ period, baseline, experiment, adverse }, null, 2) + "\n",
  { flag: "wx" },
);
