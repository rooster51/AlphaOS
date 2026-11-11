import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { createInterface } from "node:readline";
import {
  prepareDukascopyHistory,
  runProxyBacktest,
} from "../src/lib/pivex/dukascopy-history.ts";

async function* readTicks(input) {
  let lineNumber = 0;
  const lines = createInterface({ input, crlfDelay: Infinity });
  for await (const line of lines) {
    lineNumber++;
    if (lineNumber === 1) {
      if (line.replace(/^\uFEFF/, "") !== "timestamp,bid,ask")
        throw Error("Expected a paired tick CSV with timestamp,bid,ask header");
      continue;
    }
    const fields = line.split(",");
    if (
      fields.length !== 3 ||
      !fields.slice(1).every((price) => /^\d+(?:\.\d+)?$/.test(price))
    )
      throw Error(`Invalid paired tick CSV at line ${lineNumber}`);
    const [at, bid, ask] = fields;
    yield { at, bid: Number(bid), ask: Number(ask) };
  }
}

const [manifestFile, csvFile, configFile, reportFile, datasetFile] =
  process.argv.slice(2);
if (
  !manifestFile ||
  !csvFile ||
  !configFile ||
  !reportFile ||
  process.argv.length > 7
) {
  console.error(
    "Usage: node scripts/pivex-history.mjs manifest.json ticks.csv config.json report.json [dataset.json]",
  );
  process.exitCode = 1;
} else {
  const [manifest, config] = await Promise.all(
    [manifestFile, configFile].map(async (file) =>
      JSON.parse(await readFile(file, "utf8")),
    ),
  );
  const input = createReadStream(csvFile);
  const hash = createHash("sha256");
  input.on("data", (chunk) => hash.update(chunk));
  try {
    const dataset = await prepareDukascopyHistory(
      manifest,
      readTicks(input),
      () => hash.digest("hex"),
    );
    const report = runProxyBacktest(dataset, config);
    const save = (file, value) =>
      writeFile(file, JSON.stringify(value, null, 2) + "\n", { flag: "wx" });
    await save(reportFile, report);
    if (datasetFile) await save(datasetFile, dataset);
  } finally {
    input.destroy();
  }
}
