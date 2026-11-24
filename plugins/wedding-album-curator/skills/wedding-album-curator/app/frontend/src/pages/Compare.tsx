import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Award } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, img } from "../api";
import { Badge, Button, Empty, PageHeader, pct } from "../components/ui";
import { useI18n } from "../i18n";

export default function ComparePage() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const qc = useQueryClient();
  const [mode, setMode] = useState<"couple" | "all">("all");
  const [after, setAfter] = useState(0);
  const [rejectOthers, setRejectOthers] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["compare", pid, mode, after], queryFn: () => api(`/projects/${pid}/compare/next?mode=${mode}&after=${after}`) });
  const g = data?.group;

  const keep = async (winner: number) => {
    await api(`/projects/${pid}/compare/decide`, {
      body: { winner_id: winner, loser_ids: g.photos.map((p: any) => p.id).filter((i: number) => i !== winner), reject_losers: rejectOthers },
    });
    qc.invalidateQueries({ queryKey: ["photos", pid] });
    setAfter(g.group_id);
  };

  return (
    <div>
      <PageHeader
        title={t("compare")}
        subtitle={t("compareIntro")}
        actions={
          <>
            <Button variant={mode === "all" ? "primary" : "secondary"} size="sm" onClick={() => (setMode("all"), setAfter(0))}>
              {t("allGroups")}
            </Button>
            <Button variant={mode === "couple" ? "primary" : "secondary"} size="sm" onClick={() => (setMode("couple"), setAfter(0))}>
              {t("onlyCouple")}
            </Button>
          </>
        }
      />
      {!isLoading && !g && <Empty>{t("noGroups")}</Empty>}
      {g && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-muted">
            {g.remaining_groups != null && <span>{t("remainingGroups", { n: g.remaining_groups })}</span>}
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={rejectOthers} onChange={(e) => setRejectOthers(e.target.checked)} className="accent-[var(--accent)]" /> {t("rejectOthers")}
            </label>
            <div className="flex-1" />
            <Button size="sm" variant="ghost" onClick={() => setAfter(g.group_id)}>
              {t("skipGroup")} →
            </Button>
          </div>
          <div className={clsx("grid gap-4", g.photos.length === 2 ? "md:grid-cols-2" : g.photos.length === 3 ? "md:grid-cols-3" : "md:grid-cols-2 xl:grid-cols-4")}>
            {g.photos.map((p: any) => {
              const rec = p.id === g.recommended;
              return (
                <div key={p.id} className={clsx("overflow-hidden rounded-2xl border bg-surface", rec ? "border-accent" : "border-line")}>
                  <div className="relative bg-sunken">
                    <img src={img.preview(pid, p.id)} alt="" className="h-[52vh] w-full object-contain" />
                    {rec && (
                      <div className="absolute start-3 top-3">
                        <Badge tone="accent" className="bg-black/60">
                          <Award size={12} /> {t("recommended")}
                        </Badge>
                      </div>
                    )}
                    {p.decision && (
                      <div className="absolute end-3 top-3">
                        <Badge tone={p.decision === "selected" ? "good" : "bad"}>{t(p.decision)}</Badge>
                      </div>
                    )}
                  </div>
                  <div className="p-4 text-sm">
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-muted">
                      <span>{t("sharpness")}</span>
                      <span className="text-end text-fg">{pct(p.sharpness)}</span>
                      <span>{t("exposure")}</span>
                      <span className="text-end text-fg">{pct(p.exposure)}</span>
                      <span>{t("composition")}</span>
                      <span className="text-end text-fg">{pct(p.composition)}</span>
                      {p.face_quality != null && (
                        <>
                          <span>Faces</span>
                          <span className="text-end text-fg">{pct(p.face_quality)}</span>
                        </>
                      )}
                      {p.eyes_closed > 0 && (
                        <>
                          <span className="text-bad">{t("closedEyes")}</span>
                          <span className="text-end text-bad">{p.eyes_closed}</span>
                        </>
                      )}
                    </div>
                    {rec && (
                      <ul className="mt-3 space-y-0.5 text-xs text-accent">
                        {g.explanation.map((e: string) => (
                          <li key={e} dir="auto">• {e}</li>
                        ))}
                      </ul>
                    )}
                    <Button variant={rec ? "primary" : "secondary"} className="mt-4 w-full" onClick={() => keep(p.id)}>
                      {t("keepThis")}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
