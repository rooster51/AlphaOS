"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { IChartApi, IPriceLine, ISeriesApi, Time } from "lightweight-charts";
import type { CandleChartSeries, EmaPeriod } from "@/lib/candle-chart";

type ChartApi = {
  chart: IChartApi;
  candles: ISeriesApi<"Candlestick">;
  volume: ISeriesApi<"Histogram">;
  ema: Record<EmaPeriod, ISeriesApi<"Line">>;
  priceLine: IPriceLine | null;
  lineStyleDashed: number;
  lastSnapshotId: string | null;
};

export function LightweightCandleChart({
  series,
  activeEmas,
  quote,
  label,
}: {
  series: CandleChartSeries | null;
  activeEmas: EmaPeriod[];
  quote: { price: number; label: string } | null;
  label: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const apiRef = useRef<ChartApi | null>(null);
  const [ready, setReady] = useState(false);
  const [rendererError, setRendererError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void import("lightweight-charts").then((lib) => {
      if (cancelled || !containerRef.current) return;
      const chart = lib.createChart(containerRef.current, {
        autoSize: true,
        layout: {
          background: { type: lib.ColorType.Solid, color: "#080B10" },
          textColor: "#A2B4CC",
          fontFamily: "JetBrains Mono, SFMono-Regular, Menlo, monospace",
          fontSize: 11,
          attributionLogo: true,
        },
        grid: {
          vertLines: { color: "#18202D" },
          horzLines: { color: "#18202D" },
        },
        rightPriceScale: { borderColor: "#243042", scaleMargins: { top: 0.08, bottom: 0.08 } },
        timeScale: {
          borderColor: "#243042",
          timeVisible: true,
          secondsVisible: false,
          rightOffset: 3,
          barSpacing: 5,
          tickMarkFormatter: (time: Time) =>
            typeof time === "number"
              ? new Date(time * 1000).toISOString().slice(11, 16)
              : "",
        },
        localization: {
          timeFormatter: (time: Time) =>
            typeof time === "number"
              ? `${new Date(time * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC`
              : "",
        },
        crosshair: { mode: lib.CrosshairMode.Normal },
        handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
        handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
      });

      const candles = chart.addSeries(lib.CandlestickSeries, {
        upColor: "#10B981",
        downColor: "#EF4444",
        borderVisible: false,
        wickUpColor: "#10B981",
        wickDownColor: "#EF4444",
        priceLineVisible: true,
        lastValueVisible: true,
      }, 0);
      const volume = chart.addSeries(lib.HistogramSeries, {
        priceFormat: { type: "volume" },
        priceLineVisible: false,
        lastValueVisible: false,
      }, 1);
      const ema = {
        9: chart.addSeries(lib.LineSeries, {
          color: "#38BDF8", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "EMA 9",
        }, 0),
        21: chart.addSeries(lib.LineSeries, {
          color: "#F59E0B", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "EMA 21",
        }, 0),
        50: chart.addSeries(lib.LineSeries, {
          color: "#A78BFA", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "EMA 50",
        }, 0),
      } as Record<EmaPeriod, ISeriesApi<"Line">>;

      const panes = chart.panes();
      panes[0]?.setStretchFactor(3.4);
      panes[1]?.setStretchFactor(1);
      chart.priceScale("right", 1).applyOptions({ scaleMargins: { top: 0.08, bottom: 0 } });

      apiRef.current = {
        chart,
        candles,
        volume,
        ema,
        priceLine: null,
        lineStyleDashed: lib.LineStyle.Dashed,
        lastSnapshotId: null,
      };
      setReady(true);
    }).catch(() => {
      if (!cancelled) setRendererError("The chart renderer could not be initialized.");
    });

    return () => {
      cancelled = true;
      apiRef.current?.chart.remove();
      apiRef.current = null;
    };
  }, []);

  const applySeries = useCallback(() => {
    const api = apiRef.current;
    if (!api || !series) return;
    api.candles.setData(series.candles);
    api.volume.setData(series.volume);
    for (const period of [9, 21, 50] as EmaPeriod[]) {
      const visible = activeEmas.includes(period);
      api.ema[period].applyOptions({ visible });
      api.ema[period].setData(visible ? series.ema[period] : []);
    }
    if (api.lastSnapshotId !== series.snapshotId) {
      api.chart.timeScale().fitContent();
      api.lastSnapshotId = series.snapshotId;
    }
  }, [activeEmas, series]);

  const applyQuote = useCallback(() => {
    const api = apiRef.current;
    if (!api) return;
    if (quote) {
      if (api.priceLine) {
        api.priceLine.applyOptions({ price: quote.price, title: quote.label });
      } else {
        api.priceLine = api.candles.createPriceLine({
          price: quote.price,
          color: "#38BDF8",
          lineWidth: 1,
          lineStyle: api.lineStyleDashed,
          axisLabelVisible: true,
          title: quote.label,
        });
      }
    } else if (api.priceLine) {
      api.candles.removePriceLine(api.priceLine);
      api.priceLine = null;
    }
  }, [quote]);

  useEffect(() => {
    if (!ready) return;
    applySeries();
  }, [applySeries, ready]);

  useEffect(() => {
    if (!ready) return;
    applyQuote();
  }, [applyQuote, ready]);

  return (
    <div className="relative min-w-0 w-full overflow-hidden rounded-lg border border-terminal-800 bg-terminal-950">
      <div
        ref={containerRef}
        role="img"
        aria-label={label}
        className="h-[330px] w-full min-w-0 sm:h-[440px]"
      />
      {!ready && !rendererError && (
        <p className="absolute inset-0 grid place-items-center font-mono text-xs text-terminal-400">
          Initializing chart…
        </p>
      )}
      {rendererError && (
        <p role="alert" className="absolute inset-0 grid place-items-center px-6 text-center font-mono text-xs text-warning">
          {rendererError}
        </p>
      )}
    </div>
  );
}
