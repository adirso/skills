import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Crown, Eye, EyeOff, Images, Merge, RefreshCw, ScanFace } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, img, type Person } from "../api";
import { Badge, Button, Card, Empty, Modal, PageHeader, inputCls } from "../components/ui";
import { useI18n } from "../i18n";
import { useActiveJobs } from "../App";
import { FacesPendingBanner } from "../components/FacesPending";

export default function PeoplePage() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const qc = useQueryClient();
  const [mergeSel, setMergeSel] = useState<number[]>([]);
  const [openPerson, setOpenPerson] = useState<Person | null>(null);
  const [showHidden, setShowHidden] = useState(false);
  const [rescanOpen, setRescanOpen] = useState(false);
  const [rescanError, setRescanError] = useState<string | null>(null);
  const { active } = useActiveJobs(pid);
  const analyzing = active.some((j) => j.kind === "analyze");
  const rescan = async () => {
    setRescanError(null);
    try {
      await api(`/projects/${pid}/analyze?redo=faces`, { method: "POST" });
      setRescanOpen(false);
      qc.invalidateQueries({ queryKey: ["jobs", pid] });
    } catch (e: any) {
      setRescanError(String(e?.message ?? e));
    }
  };
  const { data: persons } = useQuery({ queryKey: ["persons", pid], queryFn: () => api<Person[]>(`/projects/${pid}/persons`) });
  const { data: levels } = useQuery({ queryKey: ["levels", pid], queryFn: () => api(`/projects/${pid}/importance-levels`) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["persons", pid] });
    qc.invalidateQueries({ queryKey: ["dashboard", pid] });
  };
  const patch = async (id: number, body: any) => {
    await api(`/projects/${pid}/persons/${id}`, { method: "PATCH", body });
    refresh();
  };
  const merge = async () => {
    const [target, ...rest] = mergeSel;
    await api(`/projects/${pid}/persons/merge`, { body: { target_id: target, source_ids: rest } });
    setMergeSel([]);
    refresh();
  };
  const visible = (persons ?? []).filter((p) => showHidden || !p.hidden);
  const hasBride = persons?.some((p) => p.role === "bride");
  const hasGroom = persons?.some((p) => p.role === "groom");
  const levelList = levels ? Object.entries(levels as Record<string, any>).sort((a, b) => a[1].order - b[1].order) : [];

  return (
    <div>
      <PageHeader
        title={t("people")}
        subtitle={t("peopleIntro")}
        actions={
          <>
            {mergeSel.length >= 2 && (
              <Button variant="primary" onClick={merge}>
                <Merge size={15} /> {t("merge")} ({mergeSel.length})
              </Button>
            )}
            <Button variant="ghost" onClick={() => setShowHidden((s) => !s)}>
              {showHidden ? <EyeOff size={15} /> : <Eye size={15} />} {showHidden ? t("hide") : t("unhide")}
            </Button>
            <Button onClick={() => api(`/projects/${pid}/recluster`, { method: "POST" }).then(refresh)} title={t("regroupHint")}>
              <RefreshCw size={15} /> {t("regroup")}
            </Button>
            <Button onClick={() => setRescanOpen(true)} disabled={analyzing}>
              <ScanFace size={15} /> {t("rescanFaces")}
            </Button>
          </>
        }
      />
      {persons && (!hasBride || !hasGroom) && persons.length > 0 && (
        <div className="mb-5 flex items-center gap-2 rounded-lg border border-accent/40 bg-accent/10 p-3 text-sm text-accent">
          <Crown size={16} /> {t("coupleMissing")}
        </div>
      )}
      <FacesPendingBanner pid={pid} />
      <Modal open={rescanOpen} onClose={() => setRescanOpen(false)} title={t("rescanFaces")}>
        <p className="text-sm text-muted">{t("rescanExplain")}</p>
        {rescanError && <p className="mt-3 text-sm text-bad" dir="auto">{rescanError}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setRescanOpen(false)}>{t("cancel")}</Button>
          <Button variant="primary" onClick={rescan}><ScanFace size={15} /> {t("rescanStart")}</Button>
        </div>
      </Modal>
      <p className="mb-4 text-xs text-faint">{t("mergeHint")}</p>
      {persons && persons.length === 0 && <Empty>{t("noPeople")}</Empty>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {visible.map((p) => (
          <Card key={p.id} className={clsx("p-4", mergeSel.includes(p.id) && "border-accent", p.hidden && "opacity-50")}>
            <div className="flex items-start gap-3">
              <button onClick={() => setOpenPerson(p)} className="shrink-0" aria-label="Open faces">
                {p.rep_face_id ? <img src={img.face(pid, p.rep_face_id)} alt="" className="h-16 w-16 rounded-full object-cover ring-2 ring-line" /> : <div className="h-16 w-16 rounded-full bg-raised" />}
              </button>
              <div className="min-w-0 flex-1">
                <input
                  className="w-full border-b border-transparent bg-transparent font-display text-xl outline-none focus:border-accent"
                  defaultValue={p.name ?? ""}
                  placeholder={p.role ? t(p.role) : t("unknownPerson")}
                  onBlur={(e) => e.target.value !== (p.name ?? "") && patch(p.id, { name: e.target.value })}
                  aria-label={t("name")}
                />
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                  {p.role && <Badge tone="accent">{t(p.role)}</Badge>}
                  <span>
                    {p.photo_count} {t("photos")}
                  </span>
                  {p.uncertain_count > 0 && <Badge tone="warn">{t("uncertainMatches", { n: p.uncertain_count })}</Badge>}
                </div>
              </div>
              <input type="checkbox" checked={mergeSel.includes(p.id)} onChange={(e) => setMergeSel((s) => (e.target.checked ? [...s, p.id] : s.filter((x) => x !== p.id)))} aria-label="Select for merge" className="mt-1 accent-[var(--accent)]" />
            </div>
            <div className="mt-3 flex gap-1">
              {p.sample_faces.slice(1, 6).map((f) => (
                <img key={f} src={img.face(pid, f)} alt="" className="h-9 w-9 rounded-full object-cover" loading="lazy" />
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <Button size="sm" variant={p.role === "bride" ? "primary" : "secondary"} onClick={() => patch(p.id, { role: p.role === "bride" ? "none" : "bride" })}>
                {t("bride")}
              </Button>
              <Button size="sm" variant={p.role === "groom" ? "primary" : "secondary"} onClick={() => patch(p.id, { role: p.role === "groom" ? "none" : "groom" })}>
                {t("groom")}
              </Button>
              <select
                className="h-8 flex-1 rounded-lg border border-line bg-sunken px-2 text-xs"
                value={p.role ? p.role : p.importance}
                disabled={!!p.role}
                onChange={(e) => patch(p.id, { importance: e.target.value })}
                aria-label={t("importance")}
              >
                {levelList
                  .filter(([k]) => k !== "bride" && k !== "groom")
                  .map(([k, v]) => (
                    <option key={k} value={k}>
                      {v.label}
                    </option>
                  ))}
                {p.role && <option value={p.role}>{t(p.role)}</option>}
              </select>
            </div>
            <div className="mt-2 flex gap-1">
              <Link to={`../library?person_id=${p.id}`} className="inline-flex">
                <Button size="sm" variant="ghost">
                  <Images size={14} /> {t("showPhotos")}
                </Button>
              </Link>
              <Button size="sm" variant="ghost" onClick={() => patch(p.id, { hidden: !p.hidden })}>
                {p.hidden ? t("unhide") : t("hide")}
              </Button>
            </div>
          </Card>
        ))}
      </div>
      <ImportanceEditor pid={pid} levels={levels} />
      {openPerson && <PersonFaces pid={pid} person={openPerson} persons={persons ?? []} onClose={() => setOpenPerson(null)} onChange={refresh} />}
    </div>
  );
}

function PersonFaces({ pid, person, persons, onClose, onChange }: { pid: string; person: Person; persons: Person[]; onClose: () => void; onChange: () => void }) {
  const { t } = useI18n();
  const [sel, setSel] = useState<number[]>([]);
  const { data: faces, refetch } = useQuery({ queryKey: ["pfaces", pid, person.id], queryFn: () => api<any[]>(`/projects/${pid}/persons/${person.id}/faces`) });
  const act = async (body: any) => {
    await api(`/projects/${pid}/faces`, { body: { face_ids: sel, ...body } });
    setSel([]);
    refetch();
    onChange();
  };
  return (
    <Modal open onClose={onClose} wide title={person.name ?? (person.role ? t(person.role) : t("unknownPerson"))}>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">{t("facesSelected", { n: sel.length })}</span>
        <Button size="sm" disabled={!sel.length} onClick={() => act({ action: "confirm" })}>
          {t("confirmFaces")}
        </Button>
        <Button size="sm" disabled={!sel.length} onClick={() => act({ action: "move", person_id: null })}>
          {t("notThisPerson")}
        </Button>
        <Button size="sm" disabled={!sel.length} onClick={() => act({ action: "move", new_person: true })}>
          {t("moveToNew")}
        </Button>
        <select
          className="h-8 rounded-lg border border-line bg-sunken px-2 text-xs"
          disabled={!sel.length}
          value=""
          onChange={(e) => e.target.value && act({ action: "move", person_id: Number(e.target.value) })}
        >
          <option value="">{t("moveTo")}</option>
          {persons
            .filter((p) => p.id !== person.id)
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.name ?? (p.role ? t(p.role) : `#${p.id}`)} ({p.photo_count})
              </option>
            ))}
        </select>
        <Button size="sm" disabled={!sel.length} onClick={() => act({ action: "uncertain" })}>
          {t("markUncertain")}
        </Button>
        <Button size="sm" variant="ghost" disabled={!sel.length} onClick={() => act({ action: "ignore" })}>
          {t("ignoreFace")}
        </Button>
      </div>
      <div className="grid grid-cols-5 gap-2 sm:grid-cols-8">
        {faces?.map((f) => (
          <button
            key={f.id}
            onClick={() => setSel((s) => (s.includes(f.id) ? s.filter((x) => x !== f.id) : [...s, f.id]))}
            className={clsx("relative aspect-square overflow-hidden rounded-lg", sel.includes(f.id) ? "ring-2 ring-accent" : f.uncertain ? "ring-2 ring-warn/70" : "")}
            title={f.match_conf != null ? `similarity ${f.match_conf.toFixed(2)}` : ""}
          >
            <img src={img.face(pid, f.id)} alt="" className="h-full w-full object-cover" loading="lazy" />
            {f.assignment === "user" && <span className="absolute bottom-0.5 end-0.5 rounded-full bg-good px-1 text-[10px] text-black">✓</span>}
          </button>
        ))}
      </div>
    </Modal>
  );
}

function ImportanceEditor({ pid, levels }: { pid: string; levels: any }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<any>(null);
  const [newKey, setNewKey] = useState("");
  if (!levels) return null;
  const cur = draft ?? levels;
  const entries = Object.entries(cur as Record<string, any>).sort((a, b) => a[1].order - b[1].order);
  const save = async () => {
    await api(`/projects/${pid}/importance-levels`, { method: "PUT", body: cur });
    setDraft(null);
    qc.invalidateQueries({ queryKey: ["levels", pid] });
  };
  return (
    <Card className="mt-8 p-5">
      <h2 className="mb-3 font-display text-2xl">{t("importanceLevels")}</h2>
      <div className="space-y-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-center gap-3 text-sm">
            <input className={clsx(inputCls, "h-8 max-w-56")} value={v.label} onChange={(e) => setDraft({ ...cur, [k]: { ...v, label: e.target.value } })} />
            <span className="text-xs text-muted">{t("weight")}</span>
            <input type="range" min={0} max={1} step={0.05} value={v.weight} onChange={(e) => setDraft({ ...cur, [k]: { ...v, weight: Number(e.target.value) } })} className="w-40 accent-[var(--accent)]" />
            <span className="w-10 text-xs text-muted">{v.weight.toFixed(2)}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 flex gap-2">
        <input className={clsx(inputCls, "h-8 max-w-56")} placeholder="+ custom level" value={newKey} onChange={(e) => setNewKey(e.target.value)} />
        <Button
          size="sm"
          disabled={!newKey}
          onClick={() => {
            setDraft({ ...cur, [`custom_${Date.now().toString(36)}`]: { label: newKey, weight: 0.4, order: 50 } });
            setNewKey("");
          }}
        >
          +
        </Button>
        {draft && (
          <Button size="sm" variant="primary" onClick={save}>
            {t("save")}
          </Button>
        )}
      </div>
    </Card>
  );
}
