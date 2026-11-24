import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, RefreshCw } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useActiveJobs } from "../App";
import { Button, Card, PageHeader, Progress, Stat } from "../components/ui";
import { useI18n } from "../i18n";
import { FacesPendingBanner } from "../components/FacesPending";

export default function DashboardPage() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const { data: d, refetch } = useQuery({ queryKey: ["dashboard", pid], queryFn: () => api(`/projects/${pid}/dashboard`) });
  const { active } = useActiveJobs(pid);
  if (!d) return <div className="text-muted">{t("loading")}</div>;
  const la = d.last_analysis;
  const steps = [
    { done: d.couple_identified >= 2, label: t("stepIdentify"), to: "people" },
    { done: d.similar_groups === 0, label: t("stepCompare"), to: "compare" },
    { done: d.suggested > 0, label: t("stepGenerate"), to: "album" },
    { done: false, label: t("stepReview"), to: "review" },
    { done: false, label: t("stepExport"), to: "export" },
  ];
  return (
    <div>
      <PageHeader
        title={d.name}
        subtitle={<span dir="ltr">{d.source_dir}</span>}
        actions={
          <Button
            onClick={() => api(`/projects/${pid}/analyze`, { method: "POST" }).then(() => refetch())}
            disabled={active.some((j) => j.kind === "analyze") || !d.source_available}
          >
            <RefreshCw size={15} /> {t("runAnalysis")}
          </Button>
        }
      />
      <FacesPendingBanner pid={pid} />
      {!d.source_available && <div className="mb-6 rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn">{t("missingSource")}</div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label={t("totalPhotos")} value={d.total.toLocaleString()} hint={d.duplicates ? `${d.duplicates} exact duplicates · ${d.errors} unreadable` : d.errors ? `${d.errors} unreadable` : undefined} />
        <Stat label={t("processed")} value={d.processed.toLocaleString()} hint={<Progress value={d.total ? d.processed / d.total : 0} className="mt-2" />} />
        <Stat label={t("discoveredPeople")} value={d.people} hint={d.couple_identified < 2 ? t("coupleMissing") : `${d.named_people} named`} />
        <Stat label={t("target")} value={d.target} hint={`${d.suggested} ${t("suggested").toLowerCase()} · ${d.selected} ${t("selected").toLowerCase()} · ${d.rejected} ${t("rejected").toLowerCase()}`} />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <h2 className="mb-4 font-display text-2xl">{t("nextSteps")}</h2>
          <ol className="space-y-2">
            {steps.map((s, i) => (
              <li key={s.to}>
                <Link to={s.to} className="flex items-center gap-3 rounded-lg px-2 py-2 text-sm hover:bg-raised">
                  <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${s.done ? "bg-good text-black" : "bg-raised text-muted"}`}>
                    {s.done ? <Check size={13} /> : i + 1}
                  </span>
                  <span className="flex-1">{s.label}</span>
                  <ArrowRight size={14} className="text-faint rtl:rotate-180" />
                </Link>
              </li>
            ))}
          </ol>
        </Card>
        <Card className="p-6">
          <h2 className="mb-4 font-display text-2xl">{t("moment")}</h2>
          <div className="space-y-2">
            {Object.entries(d.categories as Record<string, number>)
              .sort((a, b) => b[1] - a[1])
              .map(([c, n]) => (
                <Link key={c} to={`library?category=${c}`} className="block">
                  <div className="flex justify-between text-sm">
                    <span>{t(`cat_${c}`)}</span>
                    <span className="text-muted">{n}</span>
                  </div>
                  <Progress value={n / Math.max(1, d.processed)} className="mt-1" />
                </Link>
              ))}
            {Object.keys(d.categories).length === 0 && <p className="text-sm text-muted">{la?.moments?.reason ?? "—"}</p>}
          </div>
        </Card>
      </div>

      {la && (
        <Card className="mt-6 p-6 text-sm">
          <h2 className="mb-3 font-display text-2xl">{t("measured")}</h2>
          <div className="grid gap-2 text-muted sm:grid-cols-4">
            <div>
              Photos/s: <span className="text-fg">{la.timings?.analyze_rate ?? "—"}</span>
            </div>
            <div>
              Embeddings: <span className="text-fg">{la.timings?.embed_s}s</span>
            </div>
            <div>
              Organize: <span className="text-fg">{la.timings?.organize_s}s</span>
            </div>
            <div>
              Total: <span className="text-fg">{la.timings?.total_s}s</span>
            </div>
          </div>
          {typeof la.people?.skipped === "string" && <p className="mt-2 text-warn">People: {la.people.skipped}</p>}
          {typeof la.embeddings === "string" && <p className="mt-1 text-warn">{la.embeddings}</p>}
        </Card>
      )}
    </div>
  );
}
