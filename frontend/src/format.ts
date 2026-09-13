import type { Lap, Metric } from "./types";

/** 90456 -> "1:30.456" */
export function fmtLap(ms: number | null | undefined, decimals = 3): string {
  if (ms == null || !isFinite(ms)) return "—";
  const sign = ms < 0 ? "-" : "";
  ms = Math.abs(ms);
  const minutes = Math.floor(ms / 60000);
  const seconds = (ms - minutes * 60000) / 1000;
  const sec = seconds.toFixed(decimals).padStart(decimals ? 3 + decimals : 2, "0");
  return minutes > 0 ? `${sign}${minutes}:${sec}` : `${sign}${sec}`;
}

/** 456 -> "+0.456", -120 -> "-0.120" */
export function fmtDelta(ms: number | null | undefined, decimals = 3): string {
  if (ms == null || !isFinite(ms)) return "—";
  const sign = ms > 0 ? "+" : ms < 0 ? "-" : "";
  return `${sign}${(Math.abs(ms) / 1000).toFixed(decimals)}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export const COMPOUND_COLORS: Record<string, { fill: string; text: string }> = {
  SOFT: { fill: "#e8202a", text: "#ffffff" },
  MEDIUM: { fill: "#f6d21c", text: "#1a1a1a" },
  HARD: { fill: "#f4f4f4", text: "#1a1a1a" },
  INTERMEDIATE: { fill: "#3fb548", text: "#ffffff" },
  WET: { fill: "#1f6fe0", text: "#ffffff" },
  UNKNOWN: { fill: "#8a8a8a", text: "#ffffff" },
  TEST_UNKNOWN: { fill: "#8a8a8a", text: "#ffffff" },
};

export function compoundColor(compound: string | null | undefined) {
  return COMPOUND_COLORS[(compound || "UNKNOWN").toUpperCase()] ?? COMPOUND_COLORS.UNKNOWN;
}

export function compoundShort(compound: string | null | undefined): string {
  const c = (compound || "?").toUpperCase();
  if (c === "INTERMEDIATE") return "I";
  if (c === "UNKNOWN" || c === "TEST_UNKNOWN") return "?";
  return c[0];
}

export const TRACK_STATUS: Record<string, string> = {
  "1": "Green",
  "2": "Yellow flag",
  "4": "Safety car",
  "5": "Red flag",
  "6": "VSC",
  "7": "VSC ending",
};

export function trackStatusLabel(status: string): string {
  const codes = Array.from(new Set((status || "1").split("")));
  const labels = codes.filter((c) => c !== "1").map((c) => TRACK_STATUS[c] ?? `status ${c}`);
  return labels.length ? labels.join(", ") : "Green";
}

export function isGreen(status: string): boolean {
  return (status || "1") === "1";
}

export const METRIC_LABELS: Record<Metric, string> = {
  lap: "Lap time",
  s1: "Sector 1",
  s2: "Sector 2",
  s3: "Sector 3",
  gap: "Gap to driver",
};

export function metricValue(lap: Lap, metric: Metric): number | null {
  switch (metric) {
    case "s1":
      return lap.s1_ms;
    case "s2":
      return lap.s2_ms;
    case "s3":
      return lap.s3_ms;
    default:
      return lap.lap_time_ms;
  }
}

/** Plain-text escaping for tooltip HTML built from API data. */
export function esc(s: string | number | null | undefined): string {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
}
