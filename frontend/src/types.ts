export interface SessionInfo {
  id: number;
  code: string;
  name: string;
  number: number;
  start_utc: string | null;
  status: "pending" | "ingested" | "failed" | "unavailable";
  ingested_at: string | null;
  lap_count: number;
  driver_count: number;
  total_laps: number | null;
  last_error: string;
}

export interface EventInfo {
  id: number;
  season: number;
  round: number;
  name: string;
  official_name: string;
  location: string;
  country: string;
  format: string;
  date: string | null;
  sessions: SessionInfo[];
}

export interface Lap {
  lap_number: number;
  lap_time_ms: number | null;
  s1_ms: number | null;
  s2_ms: number | null;
  s3_ms: number | null;
  stint: number | null;
  compound: string;
  tyre_life: number | null;
  fresh_tyre: boolean;
  pit_in: boolean;
  pit_out: boolean;
  track_status: string;
  position: number | null;
  deleted: boolean;
  deleted_reason: string;
  is_accurate: boolean;
  is_personal_best: boolean;
}

export interface Stint {
  stint: number;
  compound: string;
  start_lap: number;
  end_lap: number;
  laps: number;
  avg_ms: number | null;
  deg_ms_per_lap: number | null;
}

export interface DriverStats {
  laps_total: number;
  laps_timed: number;
  laps_clean: number;
  best_lap_ms: number | null;
  best_lap_number: number | null;
  avg_ms: number | null;
  median_ms: number | null;
  best_s1_ms: number | null;
  best_s2_ms: number | null;
  best_s3_ms: number | null;
  ideal_lap_ms: number | null;
  trend_ms: number | null;
  gap_to_fastest_ms: number | null;
  stints: Stint[];
}

export interface Driver {
  number: string;
  abbreviation: string;
  full_name: string;
  team: string;
  team_color: string;
  position: number | null;
  headshot_url: string;
  stats: Partial<DriverStats>;
}

export interface SessionDetail {
  session: SessionInfo;
  event: Omit<EventInfo, "sessions">;
  fastest_lap_ms: number | null;
  fastest_driver: string | null;
  drivers: Driver[];
  laps: Record<string, Lap[]>;
}

export interface RefreshRun {
  trigger: string;
  started_at: string;
  finished_at: string | null;
  ok: boolean | null;
  summary: string;
  ingested: string[];
  failed: string[];
  schedule_errors: string[];
}

export interface RefreshStatus {
  running: boolean;
  trigger: string | null;
  step: string | null;
  started_at: string | null;
  last_run: RefreshRun | null;
  next_scheduled: string | null;
  schedule: { days: string; time: string; timezone: string; enabled: boolean };
}

export type Metric = "lap" | "s1" | "s2" | "s3" | "gap";
export type Smoothing = 0 | 3 | 5;
export type YMode = "tight" | "full";

export interface ChartOptions {
  metric: Metric;
  reference: string | null; // driver number for the "gap" metric
  smoothing: Smoothing;
  hidePit: boolean;
  hideFlags: boolean;
  hideDeleted: boolean;
  yMode: YMode;
}
