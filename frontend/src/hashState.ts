/** Shareable UI state kept in the URL hash: #s=2025&e=14&ss=R&d=1,4&m=lap */
import { useCallback, useEffect, useState } from "react";

export interface HashState {
  season?: number;
  round?: number;
  session?: string;
  drivers?: string[];
  metric?: string;
}

function parse(hash: string): HashState {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const num = (k: string) => (p.get(k) ? Number(p.get(k)) : undefined);
  return {
    season: num("s"),
    round: num("e"),
    session: p.get("ss") ?? undefined,
    drivers: p.get("d") ? p.get("d")!.split(",").filter(Boolean) : undefined,
    metric: p.get("m") ?? undefined,
  };
}

function serialize(s: HashState): string {
  const p = new URLSearchParams();
  if (s.season) p.set("s", String(s.season));
  if (s.round) p.set("e", String(s.round));
  if (s.session) p.set("ss", s.session);
  if (s.drivers?.length) p.set("d", s.drivers.join(","));
  if (s.metric && s.metric !== "lap") p.set("m", s.metric);
  return p.toString();
}

export function useHashState(): [HashState, (patch: Partial<HashState>) => void] {
  const [state, setState] = useState<HashState>(() => parse(window.location.hash));

  useEffect(() => {
    const onHash = () => setState(parse(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const update = useCallback((patch: Partial<HashState>) => {
    setState((prev) => {
      const next = { ...prev, ...patch };
      const h = serialize(next);
      if (h !== window.location.hash.replace(/^#/, "")) history.replaceState(null, "", h ? `#${h}` : window.location.pathname);
      return next;
    });
  }, []);

  return [state, update];
}
