/** Turns raw laps into the per-driver point lists the chart draws. */
import { isGreen, metricValue } from "./format";
import type { ChartOptions, Driver, Lap } from "./types";

export interface Point {
  lap: number;
  value: number | null; // null = gap in the line
  raw: Lap;
}

export interface TyreChange {
  lap: number; // first visible lap of the stint
  fittedLap: number; // lap on which the stint began
  stint: number;
  compound: string;
  value: number;
}

export interface DriverSeries {
  driver: Driver;
  dashed: boolean;
  points: Point[];
  tyreChanges: TyreChange[];
}

export function lapVisible(lap: Lap, opts: ChartOptions): boolean {
  if (opts.hidePit && (lap.pit_in || lap.pit_out)) return false;
  if (opts.hideFlags && !isGreen(lap.track_status)) return false;
  if (opts.hideDeleted && lap.deleted) return false;
  return true;
}

function rolling(values: (number | null)[], window: number): (number | null)[] {
  if (window <= 1) return values;
  const half = Math.floor(window / 2);
  return values.map((v, i) => {
    if (v == null) return null;
    let sum = 0;
    let n = 0;
    for (let j = Math.max(0, i - half); j <= Math.min(values.length - 1, i + half); j++) {
      const x = values[j];
      if (x != null) {
        sum += x;
        n++;
      }
    }
    return n ? sum / n : null;
  });
}

/** Map lap number -> metric value of the reference driver (for the gap metric). */
function referenceMap(laps: Lap[] | undefined, opts: ChartOptions): Map<number, number> {
  const m = new Map<number, number>();
  for (const lap of laps ?? []) {
    if (!lapVisible(lap, opts)) continue;
    const v = metricValue(lap, "lap");
    if (v != null) m.set(lap.lap_number, v);
  }
  return m;
}

export function buildSeries(
  drivers: Driver[],
  lapsByDriver: Record<string, Lap[]>,
  selected: string[],
  opts: ChartOptions,
): DriverSeries[] {
  const ref = opts.metric === "gap" && opts.reference ? referenceMap(lapsByDriver[opts.reference], opts) : null;
  const teamSeen = new Map<string, number>();
  const out: DriverSeries[] = [];

  for (const d of drivers) {
    const idx = teamSeen.get(d.team) ?? 0;
    teamSeen.set(d.team, idx + 1);
    if (!selected.includes(d.number)) continue;

    const laps = [...(lapsByDriver[d.number] ?? [])].sort((a, b) => a.lap_number - b.lap_number);
    const values = laps.map((lap) => {
      if (!lapVisible(lap, opts)) return null;
      let v = metricValue(lap, opts.metric === "gap" ? "lap" : opts.metric);
      if (v == null) return null;
      if (ref) {
        const r = ref.get(lap.lap_number);
        if (r == null) return null;
        v = v - r;
      }
      return v;
    });
    const smoothed = rolling(values, opts.smoothing);
    const points: Point[] = laps.map((lap, i) => ({ lap: lap.lap_number, value: smoothed[i], raw: lap }));

    // Tyre changes: first lap with a value in every stint after the first one
    // (and the first stint too in practice/qualifying, where every run is a "new tyre" event).
    const tyreChanges: TyreChange[] = [];
    let lastStint: number | null = null;
    let pendingStart: { stint: number; compound: string; lap: number } | null = null;
    for (const p of points) {
      const st = p.raw.stint;
      if (st != null && st !== lastStint) {
        pendingStart = { stint: st, compound: p.raw.compound, lap: p.lap };
        lastStint = st;
      }
      if (pendingStart && p.value != null && pendingStart.stint > 1) {
        tyreChanges.push({
          lap: p.lap,
          fittedLap: pendingStart.lap,
          stint: pendingStart.stint,
          compound: pendingStart.compound,
          value: p.value,
        });
        pendingStart = null;
      } else if (pendingStart && p.value != null) {
        pendingStart = null;
      }
    }

    out.push({ driver: d, dashed: idx % 2 === 1, points, tyreChanges });
  }
  return out;
}

function percentile(sorted: number[], p: number): number {
  if (!sorted.length) return NaN;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.floor((sorted.length - 1) * p)));
  return sorted[i];
}

/** Y-axis range: "tight" cuts the slow outliers so 2-3 s differences fill the plot. */
export function yRange(series: DriverSeries[], opts: ChartOptions): [number, number] | null {
  const vals = series
    .flatMap((s) => s.points.map((p) => p.value))
    .filter((v): v is number => v != null)
    .sort((a, b) => a - b);
  if (!vals.length) return null;
  const lo = vals[0];
  const hi = vals[vals.length - 1];
  if (opts.yMode === "full" || vals.length < 6) {
    const pad = Math.max(200, (hi - lo) * 0.05);
    return [lo - pad, hi + pad];
  }
  const p85 = percentile(vals, 0.85);
  const span = Math.max(2500, p85 - lo + 800); // at least 2.5 s of range
  const top = Math.min(hi + 300, lo + span);
  return [lo - 250, top];
}
