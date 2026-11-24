import { useQuery } from "@tanstack/react-query";
import { FolderSearch } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { useActiveJobs } from "../App";
import { Button, Card, ErrorNote, Field, PageHeader, fmtBytes, inputCls } from "../components/ui";
import { useI18n } from "../i18n";

export default function ExportPage() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const [dest, setDest] = useState("");
  const [sub, setSub] = useState(false);
  const [mode, setMode] = useState<"album" | "selected_only">("album");
  const [preview, setPreview] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const { active } = useActiveJobs(pid);
  const { data: last, refetch } = useQuery({ queryKey: ["export", pid], queryFn: () => api(`/projects/${pid}/export/last`), refetchInterval: active.length ? 2000 : false });
  const body = { destination: dest, category_subfolders: sub, mode };
  const check = async () => {
    setErr(null);
    setPreview(null);
    try {
      setPreview(await api(`/projects/${pid}/export/preview`, { body }));
    } catch (e) {
      setErr(e);
    }
  };
  const run = async () => {
    setErr(null);
    try {
      await api(`/projects/${pid}/export`, { body });
      setPreview(null);
      setTimeout(() => refetch(), 1500);
    } catch (e) {
      setErr(e);
    }
  };
  const r = last?.report;
  return (
    <div className="max-w-3xl">
      <PageHeader title={t("export")} subtitle={t("exportIntro")} />
      <Card className="space-y-5 p-6">
        <Field label={t("destination")}>
          <div className="flex gap-2">
            <input className={inputCls} dir="ltr" value={dest} onChange={(e) => (setDest(e.target.value), setPreview(null))} placeholder="/Users/…/Our Album" />
            <Button onClick={() => api("/pick-export-folder", { method: "POST" }).then((r) => r.path && (setDest(r.path), setPreview(null)))}>
              <FolderSearch size={15} /> {t("browse")}
            </Button>
          </div>
        </Field>
        <fieldset>
          <legend className="mb-2 text-sm text-muted">{t("exportMode")}</legend>
          <label className="mb-1 flex items-center gap-2 text-sm">
            <input type="radio" checked={mode === "album"} onChange={() => (setMode("album"), setPreview(null))} className="accent-[var(--accent)]" /> {t("exportAlbum")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" checked={mode === "selected_only"} onChange={() => (setMode("selected_only"), setPreview(null))} className="accent-[var(--accent)]" /> {t("exportSelectedOnly")}
          </label>
        </fieldset>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={sub} onChange={(e) => setSub(e.target.checked)} className="accent-[var(--accent)]" /> {t("subfolders")}
        </label>
        <ErrorNote error={err} />
        {preview && (
          <div className="rounded-lg bg-raised p-4 text-sm">
            <div>
              {preview.count} {t("photos")} · {fmtBytes(preview.bytes)} · free: {fmtBytes(preview.free_bytes)}
            </div>
            {!preview.enough_space && <div className="mt-1 text-bad">{t("notEnoughSpace")}</div>}
            {preview.missing.length > 0 && (
              <div className="mt-1 text-warn">
                {t("missingFiles")}: {preview.missing.length}
              </div>
            )}
          </div>
        )}
        <div className="flex gap-2">
          <Button onClick={check} disabled={!dest}>
            {t("checkExport")}
          </Button>
          <Button variant="primary" onClick={run} disabled={!preview || !preview.count || !preview.enough_space || active.some((j) => j.kind === "export")}>
            {t("startExport", { n: preview?.count ?? 0 })}
          </Button>
        </div>
      </Card>
      {r && (
        <Card className="mt-6 p-6 text-sm">
          <h2 className="mb-2 font-display text-2xl">{t("exportDone")}</h2>
          <div className="text-muted" dir="ltr">
            {r.destination}
          </div>
          <div className="mt-2">
            {r.exported} / {r.requested} {t("photos")} · checksums verified: {r.verified_checksums ? "✓" : "—"}
          </div>
          {r.missing.length > 0 && (
            <div className="mt-3">
              <div className="text-warn">{t("missingFiles")}:</div>
              <ul className="mt-1 max-h-40 overflow-auto text-xs text-muted scroll-thin" dir="ltr">
                {r.missing.map((m: any) => (
                  <li key={m.photo_id}>{m.source}</li>
                ))}
              </ul>
            </div>
          )}
          {r.failed.length > 0 && (
            <ul className="mt-3 text-xs text-bad" dir="ltr">
              {r.failed.map((m: any) => (
                <li key={m.photo_id}>
                  {m.source}: {m.error}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-faint">album_manifest.json · album_manifest.csv</p>
        </Card>
      )}
    </div>
  );
}
