import type { EventInfo, RefreshStatus, SessionDetail } from "./types";

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} (${url})`);
  return (await res.json()) as T;
}

export const api = {
  seasons: () => get<{ season: number; events: number }[]>("/api/seasons"),
  events: (season: number) => get<EventInfo[]>(`/api/seasons/${season}/events`),
  session: (id: number) => get<SessionDetail>(`/api/sessions/${id}`),
  refreshStatus: () => get<RefreshStatus>("/api/refresh/status"),
  triggerRefresh: async (body: { season?: number; session_id?: number; force?: boolean } = {}) => {
    const res = await fetch("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return (await res.json()) as RefreshStatus & { started: boolean };
  },
};
