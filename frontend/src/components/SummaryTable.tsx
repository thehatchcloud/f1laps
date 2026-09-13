import { useMemo, useState } from "react";
import { compoundColor, compoundShort, fmtDelta, fmtLap } from "../format";
import type { Driver, DriverStats } from "../types";

interface Props {
  drivers: Driver[];
  selected: string[];
  onToggle: (num: string) => void;
}

type Key = keyof Pick<
  DriverStats,
  "best_lap_ms" | "avg_ms" | "median_ms" | "ideal_lap_ms" | "best_s1_ms" | "best_s2_ms" | "best_s3_ms" | "trend_ms" | "laps_timed"
>;

const COLS: { key: Key; label: string; title: string; fmt: (v: number | null | undefined) => string }[] = [
  { key: "best_lap_ms", label: "Best", title: "Fastest valid lap", fmt: (v) => fmtLap(v) },
  { key: "avg_ms", label: "Avg", title: "Average of clean laps within 107% of the driver's best", fmt: (v) => fmtLap(v) },
  { key: "median_ms", label: "Median", title: "Median of clean representative laps", fmt: (v) => fmtLap(v) },
  { key: "ideal_lap_ms", label: "Ideal", title: "Sum of the driver's best three sectors", fmt: (v) => fmtLap(v) },
  { key: "best_s1_ms", label: "S1", title: "Best sector 1", fmt: (v) => fmtLap(v) },
  { key: "best_s2_ms", label: "S2", title: "Best sector 2", fmt: (v) => fmtLap(v) },
  { key: "best_s3_ms", label: "S3", title: "Best sector 3", fmt: (v) => fmtLap(v) },
  { key: "trend_ms", label: "Trend", title: "Second half of the run vs first half (negative = got faster)", fmt: (v) => fmtDelta(v, 2) },
  { key: "laps_timed", label: "Laps", title: "Timed laps", fmt: (v) => (v == null ? "—" : String(v)) },
];

export default function SummaryTable({ drivers, selected, onToggle }: Props) {
  const [sort, setSort] = useState<{ key: Key | "pos"; dir: 1 | -1 }>({ key: "pos", dir: 1 });

  const rows = useMemo(() => {
    const list = drivers.map((d, i) => ({ d, pos: i + 1 }));
    if (sort.key !== "pos") {
      const k = sort.key;
      list.sort((a, b) => {
        const av = a.d.stats[k];
        const bv = b.d.stats[k];
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return (av - bv) * sort.dir;
      });
    } else if (sort.dir === -1) list.reverse();
    return list;
  }, [drivers, sort]);

  const bests = useMemo(() => {
    const m = new Map<Key, number>();
    for (const c of COLS) {
      if (c.key === "laps_timed") continue;
      const vals = drivers.map((d) => d.stats[c.key]).filter((v): v is number => v != null);
      if (vals.length) m.set(c.key, Math.min(...vals));
    }
    return m;
  }, [drivers]);

  const header = (key: Key | "pos", label: string, title?: string) => (
    <th
      key={key}
      title={title}
      aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
      onClick={() => setSort((s) => ({ key, dir: s.key === key ? ((s.dir * -1) as 1 | -1) : 1 }))}
    >
      {label}
      {sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
    </th>
  );

  return (
    <div className="table-wrap">
      <table className="summary">
        <thead>
          <tr>
            <th className="sel" />
            {header("pos", "#")}
            <th>Driver</th>
            <th className="team-col">Team</th>
            {COLS.map((c) => header(c.key, c.label, c.title))}
            <th title="Tyre stints: compound and number of laps">Stints</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ d, pos }) => {
            const on = selected.includes(d.number);
            return (
              <tr key={d.number} className={on ? "on" : ""} style={{ ["--c" as string]: d.team_color }}>
                <td className="sel">
                  <input type="checkbox" checked={on} onChange={() => onToggle(d.number)} aria-label={`Show ${d.abbreviation}`} />
                </td>
                <td className="num">{d.position ?? pos}</td>
                <td className="drv">
                  <span className="team-bar" />
                  <span className="abbr">{d.abbreviation}</span>
                  <span className="name">{d.full_name}</span>
                </td>
                <td className="team-col">{d.team}</td>
                {COLS.map((c) => {
                  const v = d.stats[c.key];
                  const best = c.key !== "laps_timed" && v != null && bests.get(c.key) === v;
                  return (
                    <td key={c.key} className={`num${best ? " best" : ""}`}>
                      {c.fmt(v)}
                    </td>
                  );
                })}
                <td className="stints">
                  {(d.stats.stints ?? []).map((s) => {
                    const c = compoundColor(s.compound);
                    return (
                      <span
                        key={s.stint}
                        className="stint"
                        style={{ background: c.fill, color: c.text }}
                        title={`Stint ${s.stint}: ${s.compound.toLowerCase()} laps ${s.start_lap}–${s.end_lap}${s.avg_ms ? `, avg ${fmtLap(s.avg_ms)}` : ""}${s.deg_ms_per_lap != null ? `, ${fmtDelta(s.deg_ms_per_lap, 2)} s/lap` : ""}`}
                      >
                        {compoundShort(s.compound)}
                        {s.laps}
                      </span>
                    );
                  })}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
