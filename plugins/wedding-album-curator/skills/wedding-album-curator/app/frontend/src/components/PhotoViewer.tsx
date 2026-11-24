import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronLeft, ChevronRight, Lock, Maximize2, Minimize2, Star, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, img } from "../api";
import { useI18n } from "../i18n";
import { Badge, Button, pct } from "./ui";

export function useSetState(pid: string) {
  const qc = useQueryClient();
  return useCallback(
    async (ids: number[], patch: { decision?: "selected" | "rejected" | "none"; favorite?: boolean; rating?: number }) => {
      await api(`/projects/${pid}/photos/state`, { body: { ids, ...patch } });
      qc.invalidateQueries({ queryKey: ["photos", pid] });
      qc.invalidateQueries({ queryKey: ["photo", pid] });
      qc.invalidateQueries({ queryKey: ["album", pid] });
      qc.invalidateQueries({ queryKey: ["dashboard", pid] });
    },
    [pid, qc],
  );
}

export function PhotoViewer({ pid, ids, index, onIndex, onClose }: { pid: string; ids: number[]; index: number; onIndex: (i: number) => void; onClose: () => void }) {
  const { t, dir } = useI18n();
  const id = ids[index];
  const [zoom, setZoom] = useState(false);
  const setState = useSetState(pid);
  const qc = useQueryClient();
  const { data: d } = useQuery({ queryKey: ["photo", pid, id], queryFn: () => api(`/projects/${pid}/photos/${id}`), enabled: id != null });
  const { data: cats } = useQuery({ queryKey: ["categories"], queryFn: () => api("/categories") });

  const go = useCallback((delta: number) => onIndex(Math.max(0, Math.min(ids.length - 1, index + delta))), [ids.length, index, onIndex]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "SELECT" || (e.target as HTMLElement)?.tagName === "INPUT") return;
      const fwd = dir === "rtl" ? "ArrowLeft" : "ArrowRight";
      const bwd = dir === "rtl" ? "ArrowRight" : "ArrowLeft";
      const k = e.key.toLowerCase();
      if (e.key === fwd) go(1);
      else if (e.key === bwd) go(-1);
      else if (e.key === "Escape") onClose();
      else if (k === "p" || e.key === "Enter") setState([id], { decision: "selected" });
      else if (k === "x") setState([id], { decision: "rejected" });
      else if (k === "u") setState([id], { decision: "none" });
      else if (k === "f") setState([id], { favorite: !d?.state?.favorite });
      else if (k === "z") setZoom((z) => !z);
      else if (/^[0-5]$/.test(e.key)) setState([id], { rating: Number(e.key) });
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dir, go, id, onClose, setState, d]);

  useEffect(() => setZoom(false), [id]);

  // preload neighbours
  useEffect(() => {
    for (const j of [index + 1, index - 1]) if (ids[j] != null) new Image().src = img.preview(pid, ids[j]);
  }, [index, ids, pid]);

  if (id == null) return null;
  const decision = d?.state?.decision;
  const q = d?.quality;
  const Prev = dir === "rtl" ? ChevronRight : ChevronLeft;
  const Next = dir === "rtl" ? ChevronLeft : ChevronRight;

  return (
    <div className="fixed inset-0 z-40 flex bg-sunken/95 backdrop-blur" role="dialog" aria-modal="true">
      <div className="relative flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-2 p-3">
          <div className="truncate text-sm text-muted">
            {index + 1} / {ids.length} · {d?.file_name} {d?.taken_at && <span className="text-faint">· {d.taken_at.replace("T", " ").slice(0, 16)}</span>}
          </div>
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" onClick={() => setZoom((z) => !z)} aria-label="Zoom">
              {zoom ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </Button>
            <Button size="sm" variant="ghost" onClick={onClose} aria-label={t("close")}>
              <X size={18} />
            </Button>
          </div>
        </div>
        <div className={clsx("relative min-h-0 flex-1", zoom ? "overflow-auto scroll-thin" : "flex items-center justify-center overflow-hidden")}>
          {zoom ? (
            <img src={img.original(pid, id)} alt="" className="max-w-none cursor-zoom-out" onClick={() => setZoom(false)} />
          ) : (
            <img key={id} src={img.preview(pid, id)} alt="" className="max-h-full max-w-full cursor-zoom-in object-contain" onClick={() => setZoom(true)} />
          )}
          {!zoom && (
            <>
              <button onClick={() => go(-1)} className="absolute start-3 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-2 text-white hover:bg-black/60" aria-label="Previous">
                <Prev />
              </button>
              <button onClick={() => go(1)} className="absolute end-3 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-2 text-white hover:bg-black/60" aria-label="Next">
                <Next />
              </button>
            </>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2 p-3">
          <Button variant={decision === "selected" ? "primary" : "secondary"} onClick={() => setState([id], { decision: decision === "selected" ? "none" : "selected" })}>
            <Lock size={15} /> {t("select")} <kbd className="text-xs opacity-60">P</kbd>
          </Button>
          <Button variant={decision === "rejected" ? "danger" : "secondary"} onClick={() => setState([id], { decision: decision === "rejected" ? "none" : "rejected" })}>
            <X size={15} /> {t("reject")} <kbd className="text-xs opacity-60">X</kbd>
          </Button>
          <Button variant="secondary" onClick={() => setState([id], { favorite: !d?.state?.favorite })}>
            <Star size={15} className={d?.state?.favorite ? "fill-accent text-accent" : ""} /> {t("favorite")}
          </Button>
          <div className="flex items-center gap-0.5 ps-2" aria-label="Rating">
            {[1, 2, 3, 4, 5].map((r) => (
              <button key={r} onClick={() => setState([id], { rating: d?.state?.rating === r ? 0 : r })} className={clsx("px-0.5 text-lg", (d?.state?.rating ?? 0) >= r ? "text-accent" : "text-faint hover:text-muted")} aria-label={`${r} stars`}>
                ★
              </button>
            ))}
          </div>
        </div>
        <div className="pb-2 text-center text-[11px] text-faint">{t("shortcuts")}</div>
      </div>

      <aside className="hidden w-80 shrink-0 overflow-y-auto border-s border-line bg-surface p-5 text-sm scroll-thin lg:block">
        {d?.selection && (
          <section className="mb-5">
            <h3 className="mb-2 font-display text-lg text-accent">{t("whyThis")}</h3>
            <ul className="space-y-1 text-muted">
              {d.selection.reasons.reasons.map((r: string) => (
                <li key={r} dir="auto">• {r}</li>
              ))}
            </ul>
          </section>
        )}
        <section className="mb-5">
          <h3 className="mb-2 font-display text-lg">{t("moment")}</h3>
          <select
            className="h-9 w-full rounded-lg border border-line bg-sunken px-2"
            value={d?.event?.category ?? ""}
            onChange={async (e) => {
              await api(`/projects/${pid}/photos/category`, { body: { ids: [id], category: e.target.value } });
              qc.invalidateQueries({ queryKey: ["photo", pid, id] });
              qc.invalidateQueries({ queryKey: ["photos", pid] });
            }}
          >
            <option value="" disabled>
              —
            </option>
            {cats?.categories.map((c: string) => (
              <option key={c} value={c}>
                {t(`cat_${c}`)}
              </option>
            ))}
          </select>
          {d?.event && (
            <div className="mt-1 text-xs text-faint">
              {d.event.source === "user" ? "✓ you" : `${d.event.source} · ${pct(d.event.confidence)}%`}
            </div>
          )}
        </section>
        {q && (
          <section className="mb-5">
            <h3 className="mb-2 font-display text-lg">{t("qualitySignals")}</h3>
            {(["sharpness", "exposure", "contrast", "noise", "composition", "technical"] as const).map((k) => (
              <div key={k} className="mb-1.5">
                <div className="flex justify-between text-xs text-muted">
                  <span>{t(k)}</span>
                  <span>{pct(q[k])}</span>
                </div>
                <div className="h-1 rounded bg-raised">
                  <div className={clsx("h-1 rounded", q[k] < 0.3 ? "bg-bad" : q[k] < 0.55 ? "bg-warn" : "bg-good")} style={{ width: `${(q[k] ?? 0) * 100}%` }} />
                </div>
              </div>
            ))}
          </section>
        )}
        {d?.faces?.length > 0 && (
          <section className="mb-5">
            <h3 className="mb-2 font-display text-lg">{t("facesInPhoto")}</h3>
            <div className="space-y-2">
              {d.faces.map((f: any) => (
                <div key={f.id} className="flex items-center gap-2">
                  <img src={img.face(pid, f.id)} alt="" className="h-10 w-10 rounded-full object-cover" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate">
                      {f.person_role ? t(f.person_role) : f.person_name ?? <span className="text-faint">{t("unknownPerson")}</span>}
                      {f.person_role && f.person_name ? ` · ${f.person_name}` : ""}
                    </div>
                    <div className="text-xs text-faint">
                      {f.eyes_closed == null ? "" : f.eyes_closed && f.eyes_reliable ? <span className="text-bad">{t("eyesClosed")}</span> : f.eyes_reliable ? t("eyesOpen") : ""}
                      {f.uncertain ? <Badge tone="warn" className="ms-1">?</Badge> : null}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
        {d?.ai_results?.length > 0 && (
          <section className="mb-5">
            <h3 className="mb-2 font-display text-lg">{t("aiCaption")}</h3>
            {d.ai_results.map((a: any) => (
              <div key={a.provider + a.model} className="mb-2 text-muted">
                “{a.result.caption}” <div className="text-xs text-faint">{a.provider} · {a.model}</div>
              </div>
            ))}
          </section>
        )}
        {d?.group_members?.length > 1 && (
          <section>
            <h3 className="mb-2 font-display text-lg">{t("similarShots")}</h3>
            <div className="grid grid-cols-4 gap-1">
              {d.group_members.map((gid: number) => (
                <button
                  key={gid}
                  onClick={() => {
                    const j = ids.indexOf(gid);
                    if (j >= 0) onIndex(j);
                  }}
                  className={clsx("aspect-square overflow-hidden rounded", gid === id && "ring-2 ring-accent")}
                >
                  <img src={img.thumb(pid, gid)} alt="" className="h-full w-full object-cover" />
                </button>
              ))}
            </div>
          </section>
        )}
      </aside>
    </div>
  );
}
