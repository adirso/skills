import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Columns2, FolderOutput, Heart, Images, LayoutDashboard, Languages, ListChecks, Moon, Settings2, Sun, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, Route, Routes, useParams } from "react-router-dom";
import { api, type Job } from "./api";
import { Button, Progress } from "./components/ui";
import { useI18n } from "./i18n";
import AlbumPage from "./pages/Album";
import ComparePage from "./pages/Compare";
import DashboardPage from "./pages/Dashboard";
import ExportPage from "./pages/Export";
import LibraryPage from "./pages/Library";
import Onboarding from "./pages/Onboarding";
import PeoplePage from "./pages/People";
import ProjectsPage from "./pages/Projects";
import ReviewPage from "./pages/Review";
import SettingsPage from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectsPage />} />
      <Route path="/new" element={<Onboarding />} />
      <Route path="/p/:pid" element={<ProjectLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="people" element={<PeoplePage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="album" element={<AlbumPage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="export" element={<ExportPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

export function TopControls() {
  const { lang, setLang, t } = useI18n();
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || "dark");
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("wac.theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return (
    <div className="flex items-center gap-1">
      <Button size="sm" variant="ghost" onClick={() => setLang(lang === "he" ? "en" : "he")} aria-label={t("language")}>
        <Languages size={15} /> {lang === "he" ? "English" : "עברית"}
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={t("theme")}>
        {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
      </Button>
    </div>
  );
}

function ProjectLayout() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const { data: dash } = useQuery({ queryKey: ["dashboard", pid], queryFn: () => api(`/projects/${pid}/dashboard`), refetchInterval: 5000 });
  const nav = [
    { to: "", icon: LayoutDashboard, label: t("dashboard"), end: true },
    { to: "library", icon: Images, label: t("library") },
    { to: "people", icon: Users, label: t("people") },
    { to: "compare", icon: Columns2, label: t("compare") },
    { to: "review", icon: ListChecks, label: t("review") },
    { to: "album", icon: Heart, label: t("album") },
    { to: "export", icon: FolderOutput, label: t("export") },
    { to: "settings", icon: Settings2, label: t("settings") },
  ];
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-e border-line bg-surface">
        <NavLink to="/" className="block px-5 pb-4 pt-6">
          <div className="font-display text-2xl leading-none text-accent">{t("appName")}</div>
          <div className="mt-2 truncate text-sm text-muted">{dash?.name}</div>
        </NavLink>
        <nav className="flex-1 space-y-0.5 px-3">
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                clsx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors", isActive ? "bg-raised text-fg" : "text-muted hover:bg-raised/60 hover:text-fg")
              }
            >
              <n.icon size={17} strokeWidth={1.6} />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-line p-3">
          <TopControls />
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <JobBanner pid={pid} />
        <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7 scroll-thin">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

export function useActiveJobs(pid: string) {
  const qc = useQueryClient();
  const prevActive = useRef(false);
  const q = useQuery({
    queryKey: ["jobs", pid],
    queryFn: () => api<Job[]>(`/projects/${pid}/jobs`),
    refetchInterval: (query) => ((query.state.data as Job[] | undefined)?.some((j) => ["queued", "running", "paused"].includes(j.state)) ? 1000 : 5000),
  });
  const active = (q.data ?? []).filter((j) => ["queued", "running", "paused"].includes(j.state));
  useEffect(() => {
    if (prevActive.current && active.length === 0) {
      // a job just finished: refresh everything derived from analysis
      qc.invalidateQueries();
    }
    prevActive.current = active.length > 0;
  }, [active.length, qc]);
  return { jobs: q.data ?? [], active };
}

function JobBanner({ pid }: { pid: string }) {
  const { t } = useI18n();
  const { active } = useActiveJobs(pid);
  if (!active.length) return null;
  const j = active[0];
  const act = (a: string) => api(`/projects/${pid}/jobs/${j.id}/${a}`, { method: "POST" });
  return (
    <div className="border-b border-line bg-surface px-8 py-3">
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between text-sm">
            <span className="truncate text-fg">
              {j.kind === "analyze" ? t("analysis") : j.kind === "ai" ? "AI" : j.kind === "export" ? t("export") : j.kind}
              {j.state === "paused" && " · ⏸"} <span className="text-muted">· {j.message}</span>
            </span>
            {j.total > 0 && (
              <span className="text-xs text-muted">
                {j.done}/{j.total}
              </span>
            )}
          </div>
          <Progress value={j.total ? j.done / j.total : 0} className="mt-2" />
        </div>
        {j.state === "paused" ? (
          <Button size="sm" onClick={() => act("resume")}>
            {t("resume")}
          </Button>
        ) : (
          <Button size="sm" onClick={() => act("pause")}>
            {t("pause")}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => act("cancel")}>
          {t("stop")}
        </Button>
      </div>
    </div>
  );
}
