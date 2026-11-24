import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, X } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, img } from "../api";
import { PhotoViewer, useSetState } from "../components/PhotoViewer";
import { Button, Empty, PageHeader } from "../components/ui";
import { useI18n } from "../i18n";

export default function ReviewPage() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const qc = useQueryClient();
  const setState = useSetState(pid);
  const [kind, setKind] = useState("couple_issues");
  const [open, setOpen] = useState<number | null>(null);
  const { data: meta } = useQuery({ queryKey: ["review", pid], queryFn: () => api(`/projects/${pid}/review`) });
  const { data: items } = useQuery({ queryKey: ["review", pid, kind], queryFn: () => api<any[]>(`/projects/${pid}/review/${kind}`) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["review", pid] });
  };
  const ids = (items ?? []).map((i) => i.photo_id);
  return (
    <div>
      <PageHeader title={t("review")} subtitle={t("reviewIntro")} />
      <div className="mb-5 flex flex-wrap gap-2">
        {meta &&
          Object.entries(meta.queues as Record<string, string>).map(([k, label]) => (
            <button key={k} onClick={() => setKind(k)} className={clsx("rounded-full px-3 py-1 text-sm", kind === k ? "bg-accent text-accent-ink" : "bg-raised text-muted hover:text-fg")}>
              {label} <span className="opacity-70">({meta.counts[k]})</span>
            </button>
          ))}
      </div>
      {items && items.length === 0 && <Empty>{t("queueEmpty")}</Empty>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {items?.map((it, i) => (
          <div key={`${it.photo_id}-${it.face_id ?? ""}`} className="overflow-hidden rounded-xl border border-line bg-surface">
            <button className="relative block aspect-[4/3] w-full bg-sunken" onClick={() => setOpen(i)}>
              <img src={img.thumb(pid, it.photo_id)} alt="" className="h-full w-full object-cover" loading="lazy" />
              {it.face_id && <img src={img.face(pid, it.face_id)} alt="" className="absolute bottom-2 end-2 h-14 w-14 rounded-full object-cover ring-2 ring-warn" />}
            </button>
            <div className="p-3">
              <ul className="min-h-10 text-xs text-muted">
                {it.reasons.map((r: string) => (
                  <li key={r} dir="auto">• {r}</li>
                ))}
              </ul>
              <div className="mt-2 flex gap-1">
                {kind === "uncertain_faces" ? (
                  <>
                    <Button size="sm" onClick={() => api(`/projects/${pid}/faces`, { body: { face_ids: [it.face_id], action: "confirm" } }).then(refresh)}>
                      <Check size={13} /> {t("confirmFaces")}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => api(`/projects/${pid}/faces`, { body: { face_ids: [it.face_id], action: "move", person_id: null } }).then(refresh)}>
                      {t("notThisPerson")}
                    </Button>
                  </>
                ) : (
                  <>
                    <Button size="sm" onClick={() => api(`/projects/${pid}/review/mark-reviewed`, { body: { ids: [it.photo_id] } }).then(refresh)}>
                      <Check size={13} /> {t("markReviewed")}
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => setState([it.photo_id], { decision: "rejected" }).then(refresh)}>
                      <X size={13} /> {t("reject")}
                    </Button>
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      {open != null && (
        <PhotoViewer
          pid={pid}
          ids={ids}
          index={open}
          onIndex={setOpen}
          onClose={() => {
            setOpen(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}
