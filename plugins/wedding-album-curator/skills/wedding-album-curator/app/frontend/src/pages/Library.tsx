import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, rowsToPhotos } from "../api";
import { PhotoGrid } from "../components/PhotoGrid";
import { PhotoViewer, useSetState } from "../components/PhotoViewer";
import { Button, Empty } from "../components/ui";
import { useI18n } from "../i18n";

export default function LibraryPage() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const [sp, setSp] = useSearchParams();
  const [open, setOpen] = useState<number | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [tile, setTile] = useState(180);
  const setState = useSetState(pid);
  const params = new URLSearchParams();
  for (const k of ["sort", "decision", "favorite", "in_album", "category", "person_id", "issue", "group_id"]) {
    const v = sp.get(k);
    if (v) params.set(k, v);
  }
  const { data: cats } = useQuery({ queryKey: ["categories"], queryFn: () => api("/categories") });
  const { data, isLoading } = useQuery({ queryKey: ["photos", pid, params.toString()], queryFn: () => api(`/projects/${pid}/photos?${params}`) });
  const photos = useMemo(() => (data ? rowsToPhotos(data) : []), [data]);
  const ids = useMemo(() => photos.map((p) => p.id), [photos]);
  const set = (k: string, v: string | null) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v);
    else n.delete(k);
    setSp(n, { replace: true });
  };
  const status = sp.get("in_album") === "true" ? "album" : sp.get("favorite") ? "fav" : sp.get("decision") ?? "all";
  const setStatus = (s: string) => {
    const n = new URLSearchParams(sp);
    n.delete("in_album");
    n.delete("favorite");
    n.delete("decision");
    if (s === "album") n.set("in_album", "true");
    else if (s === "fav") n.set("favorite", "true");
    else if (s !== "all") n.set("decision", s);
    setSp(n, { replace: true });
  };
  const chip = (active: boolean) => clsx("rounded-full px-3 py-1 text-sm transition-colors", active ? "bg-accent text-accent-ink" : "bg-raised text-muted hover:text-fg");
  const sel = "h-8 rounded-lg border border-line bg-sunken px-2 text-sm";

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h1 className="me-4 font-display text-3xl">{t("library")}</h1>
        {[
          ["all", t("filterAll")],
          ["undecided", t("filterUndecided")],
          ["album", t("filterInAlbum")],
          ["selected", t("selected")],
          ["rejected", t("rejected")],
          ["fav", t("favorites")],
        ].map(([k, l]) => (
          <button key={k} className={chip(status === k)} onClick={() => setStatus(k)}>
            {l}
          </button>
        ))}
        <div className="flex-1" />
        <select className={sel} value={sp.get("category") ?? ""} onChange={(e) => set("category", e.target.value || null)} aria-label={t("moment")}>
          <option value="">{t("anyMoment")}</option>
          {cats?.categories.map((c: string) => (
            <option key={c} value={c}>
              {t(`cat_${c}`)}
            </option>
          ))}
        </select>
        <select className={sel} value={sp.get("issue") ?? ""} onChange={(e) => set("issue", e.target.value || null)}>
          <option value="">{t("anyIssue")}</option>
          <option value="blurry">{t("blurry")}</option>
          <option value="exposure">{t("exposureIssue")}</option>
          <option value="closed_eyes">{t("closedEyes")}</option>
        </select>
        <select className={sel} value={sp.get("sort") ?? "time"} onChange={(e) => set("sort", e.target.value)}>
          <option value="time">{t("sortTime")}</option>
          <option value="quality">{t("sortQuality")}</option>
          <option value="score">{t("sortScore")}</option>
          <option value="name">{t("sortName")}</option>
        </select>
        <input type="range" min={110} max={320} value={tile} onChange={(e) => setTile(Number(e.target.value))} aria-label="Thumbnail size" className="w-24 accent-[var(--accent)]" />
      </div>
      {sp.get("person_id") && (
        <div className="mb-3 text-sm text-muted">
          Filtered by person #{sp.get("person_id")}{" "}
          <button className="underline" onClick={() => set("person_id", null)}>
            ×
          </button>
        </div>
      )}
      <div className="mb-3 flex h-8 items-center gap-2 text-sm text-muted">
        <span>
          {photos.length.toLocaleString()} {t("photos")}
        </span>
        {picked.size > 0 && (
          <>
            <span>· {picked.size} ✓</span>
            <Button size="sm" onClick={() => setState([...picked], { decision: "selected" }).then(() => setPicked(new Set()))}>
              {t("select")}
            </Button>
            <Button size="sm" onClick={() => setState([...picked], { decision: "rejected" }).then(() => setPicked(new Set()))}>
              {t("reject")}
            </Button>
            <Button size="sm" onClick={() => setState([...picked], { favorite: true }).then(() => setPicked(new Set()))}>
              {t("favorite")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>
              {t("cancel")}
            </Button>
          </>
        )}
      </div>
      {!isLoading && photos.length === 0 ? (
        <Empty>{t("noPhotos")}</Empty>
      ) : (
        <PhotoGrid
          pid={pid}
          photos={photos}
          tile={tile}
          onOpen={setOpen}
          selectable
          picked={picked}
          onTogglePick={(id) =>
            setPicked((s) => {
              const n = new Set(s);
              if (n.has(id)) n.delete(id);
              else n.add(id);
              return n;
            })
          }
        />
      )}
      {open != null && <PhotoViewer pid={pid} ids={ids} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />}
    </div>
  );
}
