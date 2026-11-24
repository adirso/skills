import { useQuery } from "@tanstack/react-query";
import { FolderOpen, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { TopControls } from "../App";
import { Badge, Button, Card, Empty } from "../components/ui";
import { useI18n } from "../i18n";

export default function ProjectsPage() {
  const { t } = useI18n();
  const { data } = useQuery({ queryKey: ["projects"], queryFn: () => api<any[]>("/projects") });
  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <div className="mb-10 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-5xl text-accent">{t("appName")}</h1>
          <p className="mt-3 max-w-xl text-muted">{t("tagline")}</p>
        </div>
        <TopControls />
      </div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-2xl">{t("projects")}</h2>
        <Link to="/new">
          <Button variant="primary">
            <Plus size={16} /> {t("newProject")}
          </Button>
        </Link>
      </div>
      {data && data.length === 0 && <Empty>{t("noProjects")}</Empty>}
      <div className="grid gap-3 sm:grid-cols-2">
        {data?.map((p) => (
          <Link key={p.id} to={`/p/${p.id}`}>
            <Card className="p-5 transition-colors hover:border-accent/60">
              <div className="flex items-center gap-2">
                <FolderOpen size={18} className="text-accent" />
                <span className="font-display text-xl">{p.name}</span>
              </div>
              <div className="mt-2 truncate text-xs text-faint" dir="ltr">
                {p.source_dir}
              </div>
              {!p.source_available && (
                <Badge tone="warn" className="mt-2">
                  {t("missingSource")}
                </Badge>
              )}
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
