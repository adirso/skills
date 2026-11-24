// Thin client for the local backend. All requests are same-origin; the session cookie is
// set by the backend when the app is loaded (or via /api/session in development).

export class ApiError extends Error {
  status: number;
  body: any;
  constructor(status: number, message: string, body: any) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

let sessionPromise: Promise<void> | null = null;
function ensureSession() {
  if (!sessionPromise) sessionPromise = fetch("/api/session", { credentials: "same-origin" }).then(() => undefined);
  return sessionPromise;
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}, retry = true): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    credentials: "same-origin",
    headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401 && retry) {
    sessionPromise = null;
    await ensureSession();
    return api<T>(path, opts, false);
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : res.statusText;
    throw new ApiError(res.status, detail, data);
  }
  return data as T;
}

export const img = {
  thumb: (pid: string, id: number) => `/api/projects/${pid}/photos/${id}/thumb`,
  preview: (pid: string, id: number) => `/api/projects/${pid}/photos/${id}/preview`,
  original: (pid: string, id: number) => `/api/projects/${pid}/photos/${id}/original`,
  face: (pid: string, faceId: number) => `/api/projects/${pid}/faces/${faceId}/crop`,
};

export { ensureSession };

// ---------- shared types ----------

export type Decision = "selected" | "rejected" | null;

export interface PhotoRow {
  id: number;
  width: number | null;
  height: number | null;
  taken_at: string | null;
  group_id: number | null;
  duplicate_of: number | null;
  technical: number | null;
  sharpness: number | null;
  category: string | null;
  decision: Decision;
  favorite: number | null;
  rating: number | null;
  album_rank: number | null;
}

export function rowsToPhotos(res: { columns: string[]; rows: any[][] }): PhotoRow[] {
  const idx = Object.fromEntries(res.columns.map((c, i) => [c, i]));
  return res.rows.map((r) => {
    const o: any = {};
    for (const c of res.columns) o[c] = r[idx[c]];
    return o as PhotoRow;
  });
}

export interface Job {
  id: number;
  kind: string;
  state: string;
  stage: string | null;
  done: number;
  total: number;
  message: string | null;
  error: string | null;
  result?: any;
}

export interface Person {
  id: number;
  name: string | null;
  role: "bride" | "groom" | null;
  importance: string;
  hidden: number;
  rep_face_id: number | null;
  photo_count: number;
  face_count: number;
  uncertain_count: number;
  confirmed_count: number;
  sample_faces: number[];
}
