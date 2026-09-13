import type { EventInfo, SessionInfo } from "../types";

interface Props {
  seasons: number[];
  season: number | null;
  events: EventInfo[];
  eventRound: number | null;
  sessionCode: string | null;
  onSeason: (s: number) => void;
  onEvent: (round: number) => void;
  onSession: (code: string) => void;
}

function sessionLabel(s: SessionInfo): string {
  if (s.status === "ingested") return s.name;
  if (s.status === "unavailable") return `${s.name} (no data)`;
  if (s.status === "failed") return `${s.name} (not fetched yet)`;
  if (s.start_utc && new Date(s.start_utc).getTime() > Date.now()) return `${s.name} (upcoming)`;
  return `${s.name} (not fetched yet)`;
}

export default function SessionPicker(p: Props) {
  const event = p.events.find((e) => e.round === p.eventRound) ?? null;
  return (
    <div className="picker" role="group" aria-label="Select a session">
      <label>
        <span>Season</span>
        <select value={p.season ?? ""} onChange={(e) => p.onSeason(Number(e.target.value))}>
          {p.seasons.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Grand Prix</span>
        <select value={p.eventRound ?? ""} onChange={(e) => p.onEvent(Number(e.target.value))} disabled={!p.events.length}>
          {!p.events.length && <option value="">No events yet</option>}
          {p.events.map((e) => {
            const ready = e.sessions.some((s) => s.status === "ingested");
            return (
              <option key={e.id} value={e.round}>
                {e.round}. {e.location || e.name}
                {ready ? "" : " ·"}
              </option>
            );
          })}
        </select>
      </label>
      <label>
        <span>Session</span>
        <select value={p.sessionCode ?? ""} onChange={(e) => p.onSession(e.target.value)} disabled={!event}>
          {!event && <option value="">—</option>}
          {event?.sessions.map((s) => (
            <option key={s.id} value={s.code} disabled={s.status !== "ingested"}>
              {sessionLabel(s)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
