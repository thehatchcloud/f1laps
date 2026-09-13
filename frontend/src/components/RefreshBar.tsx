import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtDateTime } from "../format";
import type { RefreshStatus } from "../types";

interface Props {
  onFinished: () => void;
}

export default function RefreshBar({ onFinished }: Props) {
  const [status, setStatus] = useState<RefreshStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const load = async () => {
    try {
      setStatus(await api.refreshStatus());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // Poll while a check is running.
  useEffect(() => {
    if (!status?.running) return;
    const t = setInterval(async () => {
      try {
        const s = await api.refreshStatus();
        setStatus(s);
        if (!s.running) onFinished();
      } catch (e) {
        setError((e as Error).message);
      }
    }, 2000);
    return () => clearInterval(t);
  }, [status?.running, onFinished]);

  const trigger = async () => {
    try {
      const s = await api.triggerRefresh();
      setStatus(s);
      setOpen(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const last = status?.last_run;
  return (
    <div className={`refresh${open ? " open" : ""}`}>
      <button type="button" className="primary" onClick={trigger} disabled={!!status?.running}>
        {status?.running ? "Checking…" : "Check for new data"}
      </button>
      <button type="button" className="ghost" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {status?.running ? status.step ?? "Working" : last ? `Last check ${fmtDateTime(last.finished_at ?? last.started_at)}` : "Status"}
      </button>
      {open && status && (
        <div className="refresh-details">
          {status.running && <p>Running ({status.trigger}): {status.step}</p>}
          {last && (
            <p>
              Last run ({last.trigger}) {fmtDateTime(last.started_at)}: {last.ok ? "ok" : "problems"} — {last.summary}
            </p>
          )}
          {last?.ingested.length ? <p>New: {last.ingested.join("; ")}</p> : null}
          {last?.failed.length ? <p className="warn">Failed: {last.failed.join("; ")}</p> : null}
          {last?.schedule_errors.length ? <p className="warn">Schedule: {last.schedule_errors.join("; ")}</p> : null}
          <p>
            Scheduled checks: {status.schedule.enabled ? `${status.schedule.days} at ${status.schedule.time} ${status.schedule.timezone}` : "disabled"}
            {status.next_scheduled ? ` · next ${fmtDateTime(status.next_scheduled)}` : ""}
          </p>
          {error && <p className="warn">{error}</p>}
        </div>
      )}
    </div>
  );
}
