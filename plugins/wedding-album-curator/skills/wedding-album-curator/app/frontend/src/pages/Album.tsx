import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Lock, RefreshCw, Replace, RotateCcw, Sparkles, Unlock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, img } from "../api";
import { PhotoViewer, useSetState } from "../components/PhotoViewer";
import { Badge, Button, Card, Empty, ErrorNote, Modal, PageHeader, Progress, inputCls } from "../components/ui";
import { useI18n } from "../i18n";

const BUCKETS = ["getting_ready", "couple", "family_friends", "ceremony", "reception_dancing", "other"];
const WEIGHTS = [
  ["technical", "wTechnical"],
  ["faces", "wFaces"],
  ["people", "wPeople"],
  ["moment", "wMoment"],
  ["preference", "wPreference"],
  ["rating", "wRating"],
];

export default function AlbumPage() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const qc = useQueryClient();
  const setState = useSetState(pid);
  const [cfg, setCfg] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [bucket, setBucket] = useState<string | null>(null);
  const [alts, setAlts] = useState<{ for: number; ids: number[] } | null>(null);
  const { data: conf } = useQuery({ queryKey: ["albumcfg", pid], queryFn: () => api(`/projects/${pid}/album/config`) });
  const { data: album } = useQuery({ queryKey: ["album", pid], queryFn: () => api(`/projects/${pid}/album`) });
  const { data: pref, refetch: refetchPref } = useQuery({ queryKey: ["prefs", pid], queryFn: () => api(`/projects/${pid}/preferences`) });
  useEffect(() => {
    if (conf && !cfg) setCfg(conf.config);
  }, [conf, cfg]);

  const generate = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api(`/projects/${pid}/album/config`, { method: "PUT", body: cfg });
      await api(`/projects/${pid}/album/generate`, { method: "POST" });
      qc.invalidateQueries({ queryKey: ["album", pid] });
      qc.invalidateQueries({ queryKey: ["photos", pid] });
      qc.invalidateQueries({ queryKey: ["dashboard", pid] });
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  const items = useMemo(() => (album?.items ?? []).filter((i: any) => i.decision !== "rejected" && (!bucket || i.bucket === bucket)), [album, bucket]);
  const ids = useMemo(() => items.map((i: any) => i.photo_id), [items]);
  const summary = album?.run?.summary;
  // "Our defaults": the recommended settings; the album size the couple chose is kept
  const defaults = conf?.defaults ? { ...conf.defaults, target: cfg?.target ?? conf.defaults.target } : null;
  const isDefault = !!cfg && !!defaults && JSON.stringify(cfg) === JSON.stringify(defaults);
  const resetToDefaults = () => defaults && setCfg(structuredClone(defaults));
  const allocTotal = cfg ? BUCKETS.reduce((s, b) => s + Math.max(0, cfg.allocations[b] ?? 0), 0) : 100;
  // same rounding as the backend (selection.py: bucket_target)
  const plannedCount = (b: string) =>
    cfg ? Math.round((cfg.target * Math.max(0, cfg.allocations[b] ?? 0)) / Math.max(1, allocTotal)) : 0;

  const replace = async (photoId: number) => {
    const r = await api(`/projects/${pid}/album/replace/${photoId}`, { method: "POST" });
    qc.invalidateQueries({ queryKey: ["album", pid] });
    if (r.alternatives.length) setAlts({ for: photoId, ids: r.alternatives });
  };

  return (
    <div>
      <PageHeader
        title={t("album")}
        actions={
          <Button variant="primary" onClick={generate} disabled={busy || !cfg}>
            {album?.run ? <RefreshCw size={15} /> : <Sparkles size={15} />} {album?.run ? t("regenerate") : t("generate")}
          </Button>
        }
      />
      <ErrorNote error={err} />
      {cfg && defaults && (
        <div className="mb-3 flex flex-wrap items-center justify-end gap-3 text-xs text-faint">
          <span>{isDefault ? t("usingOurDefaults") : t("customSettings")}</span>
          <Button variant="ghost" onClick={resetToDefaults} disabled={isDefault} title={t("resetDefaultsHint")}>
            <RotateCcw size={14} /> {t("resetDefaults")}
          </Button>
        </div>
      )}
      {cfg && (
        <div className="mb-6 grid gap-4 xl:grid-cols-3">
          <Card className="p-5">
            <label className="text-sm text-muted">{t("target")}</label>
            <input type="number" min={1} max={20000} className={clsx(inputCls, "mt-1.5 font-display text-2xl")} value={cfg.target} onChange={(e) => setCfg({ ...cfg, target: Number(e.target.value) })} />
            {summary && (
              <div className="mt-4 space-y-1 text-sm text-muted">
                <div>
                  {t("suggested")}: <span className="text-fg">{summary.selected}</span> · {t("locked")}: <span className="text-fg">{summary.locked}</span>
                </div>
                <div>
                  {t("coupleShare")}: <span className="text-fg">{Math.round(summary.couple_share * 100)}%</span>
                </div>
                {summary.shortfall > 0 && (
                  <div className="text-warn">
                    {t("shortfall")}: {summary.shortfall}
                  </div>
                )}
              </div>
            )}
            <div className="mt-4 border-t border-line pt-3 text-xs text-muted">
              <div className="mb-1 text-fg">{t("learnedTaste")}</div>
              {pref?.method === "none" ? (
                <div>{pref?.note || t("prefNone")}</div>
              ) : (
                <div>
                  {pref?.method?.replaceAll("_", " ")} · +{pref?.positives} / −{pref?.negatives}
                </div>
              )}
              <button className="mt-1 underline" onClick={() => api(`/projects/${pid}/preferences/reset`, { method: "POST" }).then(() => refetchPref())}>
                {t("resetTaste")}
              </button>
            </div>
          </Card>
          <Card className="p-5">
            <div className="mb-3 flex items-baseline justify-between">
              <span className="text-sm text-muted">{t("allocation")}</span>
              <span className="text-xs text-faint">{t("allocationHint")}</span>
            </div>
            {BUCKETS.map((b) => (
              <div key={b} className="mb-2">
                <div className="flex justify-between text-xs">
                  <span>{t(`bucket_${b}`)}</span>
                  <span className="text-muted">
                    {Math.round(((cfg.allocations[b] ?? 0) / Math.max(1, allocTotal)) * 100)}%
                    {" · "}
                    <span className="font-medium text-fg">{t("nPhotos", { n: plannedCount(b).toLocaleString() })}</span>
                  </span>
                </div>
                <div className="flex justify-between text-[11px] text-faint">
                  <span className={clsx(conf?.available && plannedCount(b) > (conf.available[b] ?? 0) && "text-warn")}>
                    {conf?.available ? t("availableInMoment", { n: (conf.available[b] ?? 0).toLocaleString() }) : ""}
                  </span>
                  {summary && <span>{t("lastAlbumGot", { n: summary.bucket_achieved?.[b] ?? 0 })}</span>}
                </div>
                <input type="range" min={0} max={60} value={cfg.allocations[b] ?? 0} onChange={(e) => setCfg({ ...cfg, allocations: { ...cfg.allocations, [b]: Number(e.target.value) } })} className="w-full accent-[var(--accent)]" />
              </div>
            ))}
          </Card>
          <Card className="p-5">
            <div className="mb-3 text-sm text-muted">{t("weights")}</div>
            {WEIGHTS.map(([k, label]) => (
              <div key={k} className="mb-2">
                <div className="flex justify-between text-xs">
                  <span>{t(label)}</span>
                  <span className="text-muted">{(cfg.weights[k] ?? 0).toFixed(2)}</span>
                </div>
                <input type="range" min={0} max={0.6} step={0.05} value={cfg.weights[k] ?? 0} onChange={(e) => setCfg({ ...cfg, weights: { ...cfg.weights, [k]: Number(e.target.value) } })} className="w-full accent-[var(--accent)]" />
              </div>
            ))}
          </Card>
        </div>
      )}

      {summary?.notes?.length > 0 && (
        <div className="mb-4 space-y-1 rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn">
          {summary.notes.map((n: string) => (
            <div key={n} dir="auto">
              {n}
            </div>
          ))}
        </div>
      )}

      {!album?.run ? (
        <Empty>{t("albumEmpty")}</Empty>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            <button className={clsx("rounded-full px-3 py-1 text-sm", !bucket ? "bg-accent text-accent-ink" : "bg-raised text-muted")} onClick={() => setBucket(null)}>
              {t("filterAll")} ({(album.items ?? []).filter((i: any) => i.decision !== "rejected").length})
            </button>
            {BUCKETS.map((b) => (
              <button key={b} className={clsx("rounded-full px-3 py-1 text-sm", bucket === b ? "bg-accent text-accent-ink" : "bg-raised text-muted")} onClick={() => setBucket(b)}>
                {t(`bucket_${b}`)} ({summary?.bucket_achieved?.[b] ?? 0})
              </button>
            ))}
          </div>
          <Progress value={summary.selected / Math.max(1, summary.target)} className="mb-4" />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
            {items.map((it: any, i: number) => (
              <div key={it.photo_id} className="group overflow-hidden rounded-xl border border-line bg-surface">
                <button className="relative block aspect-[4/3] w-full bg-sunken" onClick={() => setOpen(i)}>
                  <img src={img.thumb(pid, it.photo_id)} alt="" loading="lazy" className="h-full w-full object-cover" />
                  {it.decision === "selected" && (
                    <span className="absolute start-2 top-2 rounded-full bg-good p-1 text-black">
                      <Lock size={11} />
                    </span>
                  )}
                </button>
                <div className="p-2.5">
                  <div dir="auto" className="line-clamp-2 min-h-8 text-xs text-muted" title={it.reasons.join(" · ")}>
                    {it.reasons.slice(0, 2).join(" · ")}
                  </div>
                  <div className="mt-2 flex gap-1 opacity-70 transition-opacity group-hover:opacity-100">
                    {it.decision === "selected" ? (
                      <Button size="sm" variant="ghost" onClick={() => setState([it.photo_id], { decision: "none" })} title={t("locked")}>
                        <Unlock size={13} />
                      </Button>
                    ) : (
                      <Button size="sm" variant="ghost" onClick={() => setState([it.photo_id], { decision: "selected" })} title={t("lock")}>
                        <Lock size={13} />
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => replace(it.photo_id)} title={t("replace")}>
                      <Replace size={13} /> {t("replace")}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          {album.selected_not_in_run?.length > 0 && (
            <p className="mt-4 text-sm text-muted">
              <Badge tone="good">+{album.selected_not_in_run.length}</Badge> selected after the last generation — they will be kept when you regenerate.
            </p>
          )}
        </>
      )}
      {open != null && <PhotoViewer pid={pid} ids={ids} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />}
      <Modal open={!!alts} onClose={() => setAlts(null)} title={t("alternatives")} wide>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {alts?.ids.map((a) => (
            <button
              key={a}
              className="overflow-hidden rounded-lg border border-line hover:border-accent"
              onClick={async () => {
                await setState([a], { decision: "selected" });
                setAlts(null);
              }}
            >
              <img src={img.thumb(pid, a)} alt="" className="aspect-[4/3] w-full object-cover" />
              <div className="p-2 text-xs">{t("select")}</div>
            </button>
          ))}
        </div>
      </Modal>
    </div>
  );
}
