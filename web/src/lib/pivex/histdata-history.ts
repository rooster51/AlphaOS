import { createHash } from "node:crypto";
import { timestamp, positive } from "./evidence.ts";
import type { Candle } from "./evidence.ts";
import { aggregate, candleGaps } from "./proxy-history.ts";

const minute = 60_000;
const five = 5 * minute;
const hour = 60 * minute;
const day = 24 * hour;
const iso = (at: number) => new Date(at).toISOString();
const hoursReference =
  "Modeled gold break using the published XAU schedule, checked against HistData M1 observations. https://www.dukascopy.com/wiki/en/page/preview/?url=%2Fdevelopment%2Fdata-export%2Ftrading-sessions";
const ny = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  timeZoneName: "shortOffset",
});

function modeledClosures(
  from: number,
  to: number,
  observed: Map<number, Candle>,
) {
  const closedPeriods = [];
  let conflictingCalendarWindows = 0;
  for (
    let date = Math.floor(from / day) * day - 2 * day;
    date < to;
    date += day
  ) {
    const weekday = new Date(date).getUTCDay();
    if (weekday === 0 || weekday === 6) continue;
    const endDate = weekday === 5 ? date + 2 * day : date;
    const offset = (d: number) =>
      Number(
        ny
          .formatToParts(d + 12 * hour)
          .find((p) => p.type === "timeZoneName")!
          .value.slice(3),
      );
    const candidates = [
      [date + 22 * hour, endDate + 23 * hour, "fixed EST"],
      [
        date + (17 - offset(date)) * hour,
        endDate + (18 - offset(endDate)) * hour,
        "New York local",
      ],
    ] as const;
    let conflict = false;
    for (const [start, end, clock] of candidates) {
      const clippedStart = Math.max(start, from),
        clippedEnd = Math.min(end, to);
      if (clippedStart >= clippedEnd) continue;
      let overlaps = false;
      for (let at = clippedStart; at < clippedEnd; at += minute) {
        if (observed.has(at)) {
          overlaps = true;
          break;
        }
      }
      if (overlaps) {
        conflict = true;
        continue;
      }
      closedPeriods.push({
        from: iso(clippedStart),
        to: iso(clippedEnd),
        source: `${clock}: ${hoursReference}`,
      });
      break;
    }
    if (conflict) conflictingCalendarWindows++;
  }
  return { closedPeriods, conflictingCalendarWindows };
}

export function prepareHistDataGold(
  bytes: Uint8Array,
  bounds: {
    from: string;
    to: string;
    exportedAt: string;
    exportReference: string;
  },
) {
  const { from, to, exportedAt, exportReference } = bounds;
  const start = Date.parse(from),
    end = Date.parse(to);
  if (
    ![from, to, exportedAt].every(timestamp) ||
    start % five ||
    end % five ||
    start >= end ||
    end > Date.parse(exportedAt) ||
    end - start > 366 * day ||
    typeof exportReference !== "string" ||
    !exportReference.trim()
  )
    throw Error(
      "Expected completed, aligned UTC coverage and an export reference",
    );

  const observed = new Map<number, Candle>();
  const lines = new TextDecoder("utf-8", { fatal: true })
    .decode(bytes)
    .trimEnd()
    .split(/\r?\n/);
  let duplicates = 0,
    outOfOrderTransitions = 0,
    outsideWindow = 0,
    previous = -Infinity;
  for (const [i, line] of lines.entries()) {
    const [stamp, ...fields] = line.split(";");
    const parts = /^(\d{4})(\d{2})(\d{2}) (\d{2})(\d{2})00$/.exec(stamp);
    if (
      !parts ||
      fields.length !== 5 ||
      !fields.every((s) => /^\d+(?:\.\d+)?$/.test(s))
    )
      throw Error(`Invalid HistData M1 record at line ${i + 1}`);
    const [, year, month, date, hh, mm] = parts;
    const localAsUtc = `${year}-${month}-${date}T${hh}:${mm}:00Z`;
    const [open, high, low, close] = fields.map(Number);
    if (
      !timestamp(localAsUtc) ||
      ![open, high, low, close].every(
        (p) => positive(p) && Math.abs(p * 1000 - Math.round(p * 1000)) < 1e-6,
      ) ||
      low > Math.min(open, close) ||
      high < Math.max(open, close)
    )
      throw Error(`Invalid HistData timestamp or OHLC at line ${i + 1}`);
    const at = Date.parse(localAsUtc) + 5 * hour;
    if (at < start || at >= end) {
      outsideWindow++;
      continue;
    }
    if (at < previous) outOfOrderTransitions++;
    previous = at;
    const existing = observed.get(at);
    if (existing) {
      if (
        existing.open !== open ||
        existing.high !== high ||
        existing.low !== low ||
        existing.close !== close
      )
        throw Error(`Conflicting HistData OHLC for ${iso(at)}`);
      duplicates++;
      continue;
    }
    observed.set(at, {
      openTime: iso(at),
      closeTime: iso(at + minute),
      complete: true,
      open,
      high,
      low,
      close,
    });
  }
  const m1 = [...observed].sort(([a], [b]) => a - b).map(([, bar]) => bar);
  const m5 = aggregate(m1, five, minute);
  if (!m5.length) throw Error("No complete five-minute observations");
  const candles = {
    m5,
    m15: aggregate(m5, 15 * minute),
    h1: aggregate(m5, hour),
  };
  const { closedPeriods, conflictingCalendarWindows } = modeledClosures(
    start,
    end,
    observed,
  );
  return {
    schema: 3 as const,
    mode: "external_proxy" as const,
    provider: "HistData.com",
    instrument: "XAUUSD",
    providerSymbol: "XAUUSD",
    instrumentType: "gold_usd_provider_quote",
    sourceTimeframe: "M1" as const,
    sourceTimezone: "Fixed UTC-05:00 (no DST)",
    quoteBasis: "bid" as const,
    sourceReference:
      "https://www.histdata.com/f-a-q/data-files-detailed-specification/",
    rightsReference:
      "Free local backtesting per https://www.histdata.com/f-a-q/; redistribution rights unverified",
    exportReference,
    from,
    to,
    exportedAt,
    closedPeriods,
    candles,
    tickSize: 0.001,
    inputSha256: createHash("sha256").update(bytes).digest("hex"),
    quality: {
      inputRows: lines.length,
      observedMinutes: m1.length,
      duplicates,
      outOfOrderTransitions,
      outsideWindow,
      firstObservation: m1[0].openTime,
      lastObservation: m1.at(-1)!.openTime,
      observedUtcDates: new Set(m1.map((bar) => bar.openTime.slice(0, 10)))
        .size,
      minutesExcludedFromIncompleteFiveMinuteBars: m1.length - 5 * m5.length,
      conflictingCalendarWindows,
      gaps: candleGaps(m5, start, end, closedPeriods),
      counts: { m5: m5.length, m15: candles.m15.length, h1: candles.h1.length },
    },
  };
}
