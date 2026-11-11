import { readFile, writeFile } from "node:fs/promises";
import { prepareHistDataGold } from "../src/lib/pivex/histdata-history.ts";
import {
  runProxyBacktest,
  runProxyDevelopment,
} from "../src/lib/pivex/proxy-history.ts";

const args = process.argv.slice(2);
const developmentOnly = args[0] === "--development-only";
if (developmentOnly) args.shift();
const [csv, config, report, normalized] = args;
if (!csv || !config || !report || args.length > 4) {
  console.error(
    "Usage: node scripts/pivex-histdata.mjs [--development-only] source.csv study.json report.json [normalized.json]",
  );
  process.exitCode = 1;
} else {
  const [bytes, manifest] = await Promise.all([
    readFile(csv),
    readFile(config, "utf8").then(JSON.parse),
  ]);
  const bounds = developmentOnly
    ? { ...manifest.source, to: manifest.replay.splitAt }
    : manifest.source;
  const dataset = prepareHistDataGold(bytes, bounds);
  const result = developmentOnly
    ? runProxyDevelopment(dataset, manifest.replay)
    : runProxyBacktest(dataset, manifest.replay);
  const save = (path, value) =>
    writeFile(path, JSON.stringify(value, null, 2) + "\n", { flag: "wx" });
  await save(report, result);
  if (normalized) await save(normalized, dataset);
}
