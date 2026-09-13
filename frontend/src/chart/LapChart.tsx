import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption, SeriesOption } from "echarts";

import { compoundColor, esc, fmtDelta, fmtLap, METRIC_LABELS, trackStatusLabel } from "../format";
import { yRange, type DriverSeries, type TyreChange } from "../series";
import type { ChartOptions, Driver } from "../types";

echarts.use([LineChart, ScatterChart, GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, CanvasRenderer]);

interface Props {
  series: DriverSeries[];
  opts: ChartOptions;
  maxLap: number;
  referenceDriver: Driver | null;
  compact: boolean;
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export default function LapChart({ series, opts, maxLap, referenceDriver, compact }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.current?.dispose();
      chart.current = null;
    };
  }, []);

  const option = useMemo<EChartsOption>(() => {
    const ink = cssVar("--ink") || "#ddd";
    const muted = cssVar("--ink-muted") || "#999";
    const grid = cssVar("--grid") || "rgba(128,128,128,0.25)";
    const surface = cssVar("--surface") || "#1e1e28";
    const isGap = opts.metric === "gap";
    const fmtY = (v: number) => (isGap ? fmtDelta(v, 1) : fmtLap(v, 1));
    const range = yRange(series, opts);
    const showEndLabels = series.length <= 8 && !compact;
    const seriesById = new Map<string, DriverSeries>();

    const lines: SeriesOption[] = series.map((s) => {
      seriesById.set(s.driver.number, s);
      return {
        id: `line-${s.driver.number}`,
        name: s.driver.abbreviation,
        type: "line",
        data: s.points.map((p) => [p.lap, p.value == null ? null : Math.round(p.value)]),
        connectNulls: false,
        showSymbol: false,
        symbol: "circle",
        symbolSize: 8,
        lineStyle: { width: 2, color: s.driver.team_color, type: s.dashed ? [6, 4] : "solid" },
        itemStyle: { color: s.driver.team_color, borderColor: surface, borderWidth: 2 },
        emphasis: { focus: "series", lineStyle: { width: 3 } },
        blur: { lineStyle: { opacity: 0.15 } },
        endLabel: {
          show: showEndLabels,
          formatter: s.driver.abbreviation,
          color: ink,
          fontSize: 11,
          fontWeight: 600,
          distance: 6,
        },
        labelLayout: { moveOverlap: "shiftY" },
        z: 2,
      };
    });

    const markers: SeriesOption[] = series
      .filter((s) => s.tyreChanges.length)
      .map((s) => ({
        id: `tyre-${s.driver.number}`,
        name: `${s.driver.abbreviation} tyres`,
        type: "scatter",
        data: s.tyreChanges.map((t) => ({
          value: [t.lap, Math.round(t.value)],
          itemStyle: { color: compoundColor(t.compound).fill, borderColor: s.driver.team_color, borderWidth: 2 },
          tyre: t,
        })),
        symbol: "circle",
        symbolSize: 13,
        tooltip: { show: false },
        emphasis: { scale: 1.3 },
        z: 5,
      }));

    const tooltip: EChartsOption["tooltip"] = {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: muted, width: 1, type: "solid" } },
      backgroundColor: surface,
      borderColor: grid,
      textStyle: { color: ink, fontSize: 12 },
      confine: true,
      appendToBody: false,
      formatter: (params) => {
        const items = (Array.isArray(params) ? params : [params]).filter((p) => String(p.seriesId).startsWith("line-"));
        if (!items.length) return "";
        const lap = Number((items[0].value as number[])[0]);
        const rows = items
          .map((p) => {
            const num = String(p.seriesId).replace("line-", "");
            const s = seriesById.get(num);
            const point = s?.points.find((x) => x.lap === lap);
            const v = (p.value as (number | null)[])[1];
            return { s, point, v };
          })
          .filter((r) => r.s && r.point && r.v != null)
          .sort((a, b) => (a.v as number) - (b.v as number));
        if (!rows.length) return "";
        const head = `<div class="tt-head">Lap ${lap}${isGap && referenceDriver ? ` · gap to ${esc(referenceDriver.abbreviation)}` : ""}</div>`;
        const body = rows
          .map(({ s, point, v }) => {
            const d = s!.driver;
            const raw = point!.raw;
            const t = s!.tyreChanges.find((x) => x.lap === lap);
            const tags: string[] = [];
            if (t) tags.push(`new ${t.compound.toLowerCase()} tyres`);
            if (raw.pit_in) tags.push("pit in");
            if (raw.pit_out) tags.push("pit out");
            if (raw.track_status !== "1") tags.push(trackStatusLabel(raw.track_status).toLowerCase());
            if (raw.deleted) tags.push("deleted");
            if (raw.is_personal_best) tags.push("PB");
            const sectors = [raw.s1_ms, raw.s2_ms, raw.s3_ms].map((x) => fmtLap(x, 3)).join(" · ");
            const comp = compoundColor(raw.compound);
            const dash = s!.dashed ? "dashed" : "solid";
            const shownVal = isGap ? fmtDelta(v, 3) : fmtLap(v, 3);
            const rawVal = opts.smoothing && !isGap ? ` <span class="tt-muted">(${fmtLap(raw.lap_time_ms)})</span>` : "";
            return (
              `<div class="tt-row">` +
              `<span class="tt-key" style="border-top:2px ${dash} ${esc(d.team_color)}"></span>` +
              `<span class="tt-abbr">${esc(d.abbreviation)}</span>` +
              `<span class="tt-val">${shownVal}${rawVal}</span>` +
              `<span class="tt-comp" style="background:${comp.fill};color:${comp.text}">${esc((raw.compound || "?")[0])}${raw.tyre_life != null ? esc(raw.tyre_life) : ""}</span>` +
              (compact ? "" : `<span class="tt-sec">${sectors}</span>`) +
              (tags.length ? `<span class="tt-tags">${esc(tags.join(", "))}</span>` : "") +
              `</div>`
            );
          })
          .join("");
        return `<div class="tt">${head}${body}</div>`;
      },
    };

    return {
      animation: false,
      backgroundColor: "transparent",
      grid: { left: compact ? 52 : 64, right: showEndLabels ? 56 : compact ? 12 : 36, top: 30, bottom: compact ? 44 : 36 },
      xAxis: {
        type: "value",
        name: "Lap",
        nameLocation: "middle",
        nameGap: 22,
        nameTextStyle: { color: muted, fontSize: 11 },
        min: 1,
        max: Math.max(2, maxLap),
        minInterval: 1,
        axisLine: { lineStyle: { color: grid } },
        axisTick: { show: false },
        axisLabel: { color: muted, fontSize: 11 },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        name: METRIC_LABELS[opts.metric],
        nameTextStyle: { color: muted, fontSize: 11, align: "left" },
        min: range ? Math.floor(range[0]) : undefined,
        max: range ? Math.ceil(range[1]) : undefined,
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: muted, fontSize: 11, formatter: fmtY },
        splitLine: { lineStyle: { color: grid, type: "solid" } },
      },
      dataZoom: [
        { type: "inside", xAxisIndex: 0, filterMode: "none", zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
        { type: "inside", yAxisIndex: 0, filterMode: "none", zoomOnMouseWheel: "shift", moveOnMouseMove: "shift", moveOnMouseWheel: false },
      ],
      tooltip,
      series: [
        ...lines,
        ...markers,
        ...(isGap
          ? [
              {
                id: "zero",
                type: "line",
                data: [],
                markLine: {
                  silent: true,
                  symbol: "none",
                  data: [{ yAxis: 0 }],
                  lineStyle: { color: muted, type: "solid", width: 1 },
                  label: { show: false },
                },
              } as SeriesOption,
            ]
          : []),
      ],
    };
  }, [series, opts, maxLap, referenceDriver, compact]);

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true });
  }, [option]);

  // Re-render on theme change (CSS variables are read at option build time).
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => chart.current?.setOption(option, { notMerge: true });
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [option]);

  return <div ref={ref} className="chart" role="img" aria-label="Lap time chart" />;
}

export type { TyreChange };
