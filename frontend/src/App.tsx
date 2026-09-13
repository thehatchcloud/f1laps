import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import LapChart from "./chart/LapChart";
import Controls from "./components/Controls";
import DriverPanel from "./components/DriverPanel";
import RefreshBar from "./components/RefreshBar";
import SessionPicker from "./components/SessionPicker";
import SummaryTable from "./components/SummaryTable";
import { fmtDateTime, fmtLap } from "./format";
import { useHashState } from "./hashState";
import { buildSeries } from "./series";
import type { ChartOptions, EventInfo, Metric, SessionDetail } from "./types";

const DEFAULT_OPTS: ChartOptions = {
  metric: "lap",
  reference: null,
  smoothing: 0,
  hidePit: true,
  hideFlags: true,
  hideDeleted: false,
  yMode: "tight",
};

function loadOpts(): ChartOptions {
  try {
    const raw = localStorage.getItem("f1laps.opts");
    return raw ? { ...DEFAULT_OPTS, ...(JSON.parse(raw) as Partial<ChartOptions>) } : DEFAULT_OPTS;
  } catch {
    return DEFAULT_OPTS;
  }
}

function useMedia(query: string): boolean {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const h = () => setMatch(mq.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, [query]);
  return match;
}

/** The most interesting session to open by default: the latest ingested one. */
function pickDefaultEvent(events: EventInfo[]): EventInfo | null {
  const withData = events.filter((e) => e.sessions.some((s) => s.status === "ingested"));
  return withData.length ? withData[withData.length - 1] : events[0] ?? null;
}

function pickDefaultSession(ev: EventInfo | null): string | null {
  if (!ev) return null;
  const ingested = ev.sessions.filter((s) => s.status === "ingested");
  if (!ingested.length) return null;
  return (ingested.find((s) => s.code === "R") ?? ingested[ingested.length - 1]).code;
}

export default function App() {
  const compact = useMedia("(max-width: 900px)");
  const [hash, setHash] = useHashState();
  const [seasons, setSeasons] = useState<number[]>([]);
  const [events, setEvents] = useState<EventInfo[]>([]);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opts, setOpts] = useState<ChartOptions>(() => ({ ...loadOpts(), metric: (hash.metric as Metric) || "lap" }));
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    try {
      localStorage.setItem("f1laps.opts", JSON.stringify(opts));
    } catch {
      /* ignore */
    }
  }, [opts]);

  // Seasons
  useEffect(() => {
    api
      .seasons()
      .then((list) => {
        const ss = list.map((s) => s.season);
        setSeasons(ss);
        if (!hash.season && ss.length) {
          const withData = list.find((s) => s.events > 0);
          setHash({ season: (withData ?? list[0]).season });
        }
      })
      .catch((e) => setError((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadTick]);

  // Events of the selected season
  useEffect(() => {
    if (!hash.season) return;
    let cancelled = false;
    api
      .events(hash.season)
      .then((evs) => {
        if (cancelled) return;
        setEvents(evs);
        const current = evs.find((e) => e.round === hash.round) ?? null;
        if (!current) {
          const ev = pickDefaultEvent(evs);
          setHash({ round: ev?.round, session: pickDefaultSession(ev) ?? undefined, drivers: undefined });
        } else if (!current.sessions.some((s) => s.code === hash.session && s.status === "ingested")) {
          setHash({ session: pickDefaultSession(current) ?? undefined, drivers: undefined });
        }
      })
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hash.season, reloadTick]);

  const event = useMemo(() => events.find((e) => e.round === hash.round) ?? null, [events, hash.round]);
  const sessionInfo = useMemo(() => event?.sessions.find((s) => s.code === hash.session) ?? null, [event, hash.session]);

  // Session detail
  useEffect(() => {
    if (!sessionInfo || sessionInfo.status !== "ingested") {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .session(sessionInfo.id)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setError(null);
        if (!hash.drivers) setHash({ drivers: d.drivers.map((x) => x.number) });
      })
      .catch((e) => !cancelled && setError((e as Error).message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionInfo?.id, sessionInfo?.ingested_at]);

  const selected = useMemo(() => hash.drivers ?? [], [hash.drivers]);
  const setSelected = useCallback((next: string[]) => setHash({ drivers: next }), [setHash]);
  const toggle = useCallback(
    (num: string) => setSelected(selected.includes(num) ? selected.filter((x) => x !== num) : [...selected, num]),
    [selected, setSelected],
  );

  const effectiveOpts = useMemo<ChartOptions>(() => {
    if (opts.metric !== "gap") return opts;
    const ref = opts.reference && selected.includes(opts.reference) ? opts.reference : selected[0] ?? null;
    return { ...opts, reference: ref };
  }, [opts, selected]);

  const series = useMemo(
    () => (detail ? buildSeries(detail.drivers, detail.laps, selected, effectiveOpts) : []),
    [detail, selected, effectiveOpts],
  );
  const maxLap = useMemo(() => {
    if (!detail) return 1;
    let m = detail.session.total_laps ?? 1;
    for (const laps of Object.values(detail.laps)) for (const l of laps) if (l.lap_number > m) m = l.lap_number;
    return m;
  }, [detail]);
  const referenceDriver = detail?.drivers.find((d) => d.number === effectiveOpts.reference) ?? null;

  const onOpts = (next: ChartOptions) => {
    setOpts(next);
    if (next.metric !== opts.metric) setHash({ metric: next.metric });
  };

  const onRefreshFinished = useCallback(() => setReloadTick((t) => t + 1), []);

  const fastest = detail?.drivers.find((d) => d.number === detail.fastest_driver);

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden="true" />
          <h1>F1 Laps</h1>
        </div>
        <SessionPicker
          seasons={seasons}
          season={hash.season ?? null}
          events={events}
          eventRound={hash.round ?? null}
          sessionCode={hash.session ?? null}
          onSeason={(s) => setHash({ season: s, round: undefined, session: undefined, drivers: undefined })}
          onEvent={(r) => {
            const ev = events.find((e) => e.round === r) ?? null;
            setHash({ round: r, session: pickDefaultSession(ev) ?? undefined, drivers: undefined });
          }}
          onSession={(c) => setHash({ session: c, drivers: undefined })}
        />
        <RefreshBar onFinished={onRefreshFinished} />
      </header>

      {error && <div className="banner warn">{error}</div>}

      {!detail && !loading && (
        <div className="empty">
          {events.length === 0 ? (
            <>
              <h2>No data yet</h2>
              <p>The calendar is empty. Use “Check for new data” to fetch the schedule and every finished session.</p>
            </>
          ) : (
            <>
              <h2>{event ? `${event.name}` : "Pick a session"}</h2>
              <p>
                {sessionInfo && sessionInfo.status !== "ingested"
                  ? sessionInfo.last_error
                    ? `This session could not be fetched yet: ${sessionInfo.last_error}`
                    : "This session has no data yet. It is fetched automatically after the weekend, or run a check now."
                  : "Choose a Grand Prix and a session with data."}
              </p>
            </>
          )}
        </div>
      )}

      {detail && (
        <main className={`layout${compact ? " compact" : ""}${loading ? " loading" : ""}`}>
          {!compact && <DriverPanel drivers={detail.drivers} selected={selected} onChange={setSelected} compact={false} />}

          <section className="content">
            <div className="session-meta">
              <h2>
                {detail.event.name} · {detail.session.name}
              </h2>
              <p>
                {detail.event.location}, {detail.event.country} · {fmtDateTime(detail.session.start_utc)}
                {fastest && detail.fastest_lap_ms ? ` · fastest lap ${fmtLap(detail.fastest_lap_ms)} (${fastest.abbreviation})` : ""}
                {detail.session.total_laps ? ` · ${detail.session.total_laps} laps` : ""}
              </p>
            </div>

            {compact && <DriverPanel drivers={detail.drivers} selected={selected} onChange={setSelected} compact />}

            {compact ? (
              <details className="options" open={optionsOpen} onToggle={(e) => setOptionsOpen((e.target as HTMLDetailsElement).open)}>
                <summary>Chart options</summary>
                <Controls opts={opts} onChange={onOpts} drivers={detail.drivers} selected={selected} />
              </details>
            ) : (
              <Controls opts={opts} onChange={onOpts} drivers={detail.drivers} selected={selected} />
            )}

            <div className="chart-card">
              {series.length ? (
                <LapChart series={series} opts={effectiveOpts} maxLap={maxLap} referenceDriver={referenceDriver} compact={compact} />
              ) : (
                <div className="chart-empty">Select at least one driver.</div>
              )}
              <div className="legend-hint">
                <span className="hint-item"><span className="dot tyre" /> tyre change (colour = compound)</span>
                <span className="hint-item">dashed line = second car of a team</span>
                <span className="hint-item">{compact ? "pinch to zoom, drag to pan" : "scroll to zoom laps, shift+scroll to zoom time, drag to pan"}</span>
              </div>
            </div>

            <SummaryTable drivers={detail.drivers} selected={selected} onToggle={toggle} />
          </section>
        </main>
      )}
    </div>
  );
}
