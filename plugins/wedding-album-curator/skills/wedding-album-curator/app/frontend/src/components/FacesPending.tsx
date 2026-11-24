import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "../api";
import { useActiveJobs } from "../App";
import { useI18n } from "../i18n";
import { Button } from "./ui";

/** Shown when photos were analyzed before the face models were installed. */
export function FacesPendingBanner({ pid }: { pid: string }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { active } = useActiveJobs(pid);
  const { data: d } = useQuery({ queryKey: ["dashboard", pid], queryFn: () => api<any>(`/projects/${pid}/dashboard`) });
  if (!d || !d.faces_pending || active.some((j) => j.kind === "analyze")) return null;
  const run = () => api(`/projects/${pid}/analyze`, { method: "POST" }).then(() => qc.invalidateQueries({ queryKey: ["jobs", pid] }));
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn">
      <Users size={16} />
      <span className="flex-1">
        {d.face_models_installed ? t("facesPending", { n: d.faces_pending.toLocaleString() }) : t("facesPendingNoModels")}
      </span>
      {d.face_models_installed && d.source_available && (
        <Button variant="primary" onClick={run}>{t("findPeopleNow")}</Button>
      )}
    </div>
  );
}
