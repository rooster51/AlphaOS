import { readFile, writeFile } from "node:fs/promises";
import { prepareHistDataGold } from "../src/lib/pivex/histdata-history.ts";
import { runProxyBacktest } from "../src/lib/pivex/proxy-history.ts";

const [csv, config, report, normalized] = process.argv.slice(2);
if (!csv || !config || !report || process.argv.length > 6) {
  console.error(
    "Usage: node scripts/pivex-histdata.mjs source.csv study.json report.json [normalized.json]",
  );
  process.exitCode = 1;
} else {
  const [bytes, manifest] = await Promise.all([
    readFile(csv),
    readFile(config, "utf8").then(JSON.parse),
  ]);
  const dataset = prepareHistDataGold(bytes, manifest.source);
  const result = runProxyBacktest(dataset, manifest.replay);
  const save = (path, value) =>
    writeFile(path, JSON.stringify(value, null, 2) + "\n", { flag: "wx" });
  await save(report, result);
  if (normalized) await save(normalized, dataset);
}
