import { METRIC_LABELS } from "../format";
import type { ChartOptions, Driver, Metric, Smoothing, YMode } from "../types";

interface Props {
  opts: ChartOptions;
  onChange: (next: ChartOptions) => void;
  drivers: Driver[];
  selected: string[];
}

export default function Controls({ opts, onChange, drivers, selected }: Props) {
  const set = <K extends keyof ChartOptions>(key: K, value: ChartOptions[K]) => onChange({ ...opts, [key]: value });
  const refCandidates = drivers.filter((d) => selected.includes(d.number));
  return (
    <div className="controls" role="group" aria-label="Chart options">
      <label>
        <span>Show</span>
        <select value={opts.metric} onChange={(e) => set("metric", e.target.value as Metric)}>
          {(Object.keys(METRIC_LABELS) as Metric[]).map((m) => (
            <option key={m} value={m}>
              {METRIC_LABELS[m]}
            </option>
          ))}
        </select>
      </label>
      {opts.metric === "gap" && (
        <label>
          <span>Reference</span>
          <select value={opts.reference ?? ""} onChange={(e) => set("reference", e.target.value || null)}>
            {!refCandidates.length && <option value="">select a driver</option>}
            {refCandidates.map((d) => (
              <option key={d.number} value={d.number}>
                {d.abbreviation}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        <span>Smoothing</span>
        <select value={opts.smoothing} onChange={(e) => set("smoothing", Number(e.target.value) as Smoothing)}>
          <option value={0}>None</option>
          <option value={3}>3-lap average</option>
          <option value={5}>5-lap average</option>
        </select>
      </label>
      <label>
        <span>Y-axis</span>
        <select value={opts.yMode} onChange={(e) => set("yMode", e.target.value as YMode)}>
          <option value="tight">Tight (hide slow outliers)</option>
          <option value="full">Full range</option>
        </select>
      </label>
      <label className="check">
        <input type="checkbox" checked={opts.hidePit} onChange={(e) => set("hidePit", e.target.checked)} />
        <span>Hide in/out laps</span>
      </label>
      <label className="check">
        <input type="checkbox" checked={opts.hideFlags} onChange={(e) => set("hideFlags", e.target.checked)} />
        <span>Hide SC / VSC / yellow laps</span>
      </label>
      <label className="check">
        <input type="checkbox" checked={opts.hideDeleted} onChange={(e) => set("hideDeleted", e.target.checked)} />
        <span>Hide deleted laps</span>
      </label>
    </div>
  );
}
