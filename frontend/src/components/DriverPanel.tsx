import { fmtDelta, fmtLap } from "../format";
import type { Driver } from "../types";

interface Props {
  drivers: Driver[];
  selected: string[];
  onChange: (next: string[]) => void;
  compact: boolean;
}

/** Group drivers by team, keeping the classification order of the first driver of each team. */
function groupByTeam(drivers: Driver[]): { team: string; color: string; drivers: Driver[] }[] {
  const groups: { team: string; color: string; drivers: Driver[] }[] = [];
  for (const d of drivers) {
    let g = groups.find((x) => x.team === d.team);
    if (!g) {
      g = { team: d.team || "Unknown team", color: d.team_color, drivers: [] };
      groups.push(g);
    }
    g.drivers.push(d);
  }
  return groups;
}

export default function DriverPanel({ drivers, selected, onChange, compact }: Props) {
  const toggle = (num: string) =>
    onChange(selected.includes(num) ? selected.filter((x) => x !== num) : [...selected, num]);
  const all = () => onChange(drivers.map((d) => d.number));
  const none = () => onChange([]);
  const top = (n: number) => onChange(drivers.slice(0, n).map((d) => d.number));
  const groups = groupByTeam(drivers);
  const dashIndex = new Map<string, number>();

  const actions = (
    <div className="panel-actions">
      <button type="button" onClick={all}>All</button>
      <button type="button" onClick={() => top(10)}>Top 10</button>
      <button type="button" onClick={() => top(5)}>Top 5</button>
      <button type="button" onClick={none}>None</button>
    </div>
  );

  if (compact) {
    return (
      <div className="chips-wrap">
        {actions}
        <div className="chips" role="group" aria-label="Drivers">
          {drivers.map((d) => {
            const on = selected.includes(d.number);
            const idx = dashIndex.get(d.team) ?? 0;
            dashIndex.set(d.team, idx + 1);
            return (
              <button
                key={d.number}
                type="button"
                className={`chip${on ? " on" : ""}`}
                style={{ ["--c" as string]: d.team_color }}
                aria-pressed={on}
                onClick={() => toggle(d.number)}
                title={`${d.full_name || d.abbreviation} · ${d.team}`}
              >
                <span className={`swatch ${idx % 2 ? "dashed" : ""}`} />
                {d.abbreviation}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <aside className="panel" aria-label="Drivers">
      <div className="panel-head">
        <h2>Drivers</h2>
        {actions}
      </div>
      <ul className="teams">
        {groups.map((g) => (
          <li key={g.team} className="team">
            <div className="team-name" style={{ ["--c" as string]: g.color }}>
              <span className="team-bar" />
              {g.team}
            </div>
            {g.drivers.map((d, i) => {
              const on = selected.includes(d.number);
              const stats = d.stats;
              return (
                <label key={d.number} className={`driver${on ? " on" : ""}`} style={{ ["--c" as string]: d.team_color }}>
                  <input type="checkbox" checked={on} onChange={() => toggle(d.number)} />
                  <span className={`swatch ${i % 2 ? "dashed" : ""}`} aria-hidden="true" />
                  <span className="abbr">{d.abbreviation}</span>
                  <span className="name">{d.full_name || `#${d.number}`}</span>
                  <span className="best" title="Best lap">
                    {fmtLap(stats.best_lap_ms)}
                  </span>
                  <span className="gap" title="Gap to session-best lap">
                    {stats.gap_to_fastest_ms ? fmtDelta(stats.gap_to_fastest_ms) : stats.best_lap_ms ? "fastest" : ""}
                  </span>
                </label>
              );
            })}
          </li>
        ))}
      </ul>
    </aside>
  );
}
