import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useActiveJobs } from "../App";
import { HardwareCard, ModelsPanel } from "../components/ModelsPanel";
import { ProviderPanel } from "../components/ProviderPanel";
import { Button, Card, ErrorNote, PageHeader } from "../components/ui";
import { useI18n } from "../i18n";

export default function SettingsPage() {
  const { pid = "" } = useParams();
  const { t } = useI18n();
  const nav = useNavigate();
  const [scope, setScope] = useState("album");
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [test, setTest] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const { active } = useActiveJobs(pid);
  const { data: ai } = useQuery({ queryKey: ["ai", pid], queryFn: () => api(`/projects/${pid}/ai`) });
  const { data: est, refetch: refetchEst } = useQuery({
    queryKey: ["estimate", pid, scope, ai?.provider?.id, ai?.provider?.model],
    queryFn: () => api(`/projects/${pid}/ai/estimate?scope=${scope}`),
    enabled: !!ai && ai.provider.id !== "none",
  });
  const { data: usage } = useQuery({ queryKey: ["usage", pid], queryFn: () => api(`/projects/${pid}/ai/usage`) });
  const isCloud = ai?.provider?.id === "anthropic_api" || ai?.provider?.id === "claude_code";

  const run = async () => {
    setErr(null);
    try {
      await api(`/projects/${pid}/ai/run`, { body: { scope, confirm_upload: confirm } });
      setConfirm(false);
    } catch (e) {
      setErr(e);
    }
  };
  const runTest = async () => {
    setErr(null);
    setTest(null);
    try {
      setTest(await api(`/projects/${pid}/ai/test`, { method: "POST" }));
    } catch (e) {
      setErr(e);
    }
  };
  const privacy = async (what: string) => {
    if (!window.confirm(t("areYouSure"))) return;
    const r = await api(`/projects/${pid}/privacy/${what}`, { method: "POST" });
    setMsg(`✓ ${r.deleted}`);
  };

  return (
    <div className="max-w-4xl space-y-8">
      <PageHeader title={t("settings")} />
      <section>
        <h2 className="mb-3 font-display text-2xl">{t("providerTitle")}</h2>
        <ProviderPanel pid={pid} compact />
      </section>

      {ai && ai.provider.id !== "none" && (
        <Card className="space-y-4 p-6">
          <h2 className="font-display text-2xl">{t("runAI")}</h2>
          <div className="flex flex-wrap gap-4 text-sm">
            {[
              ["album", t("scopeAlbum")],
              ["uncategorized", t("scopeUncategorized")],
              ["all", t("scopeAll")],
            ].map(([k, l]) => (
              <label key={k} className="flex items-center gap-2">
                <input type="radio" checked={scope === k} onChange={() => setScope(k)} className="accent-[var(--accent)]" /> {l}
              </label>
            ))}
          </div>
          {est && (
            <div className="rounded-lg bg-raised p-4 text-sm">
              <div>
                {t("estimate")}: {est.images} {t("photos")} to analyze ({est.cached} already cached, free)
              </div>
              {est.cost_usd_typical != null && (
                <div className="mt-1">
                  ≈ <span className="text-fg">${est.cost_usd_typical}</span> typical · up to ${est.cost_usd_max} worst case
                  {est.spending_limit_usd != null && ` · limit $${est.spending_limit_usd} (spent $${est.spent_usd})`}
                </div>
              )}
              {ai.provider.id === "claude_code" && <div className="mt-1 text-muted">Cost depends on your Claude Code plan; this app cannot see your allowance.</div>}
              <div className="mt-1 text-xs text-faint">{est.basis}</div>
              <button className="mt-1 text-xs underline" onClick={() => refetchEst()}>
                ↻
              </button>
            </div>
          )}
          {isCloud && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} className="accent-[var(--accent)]" /> {t("confirmUpload")}
            </label>
          )}
          <ErrorNote error={err} />
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={run} disabled={(isCloud && (!confirm || !ai.consents[ai.provider.id])) || active.some((j) => j.kind === "ai")}>
              {t("runAI")}
            </Button>
            <Button onClick={runTest} disabled={isCloud && !ai.consents[ai.provider.id]}>
              {t("testConnection")}
            </Button>
          </div>
          {test && (
            <div className="text-xs text-muted">
              ✓ {test.seconds}s · {test.result.category} · “{test.result.caption}” {test.cost_usd != null && `· $${Number(test.cost_usd).toFixed(4)} (${test.cost_basis})`}
            </div>
          )}
          {usage?.usage?.length > 0 && (
            <div className="text-xs text-muted">
              <div className="mb-1 text-fg">{t("usage")}</div>
              {usage.usage.map((u: any) => (
                <div key={u.provider + u.model + u.cost_basis}>
                  {u.provider} · {u.model}: {u.requests} req · {u.input_tokens ?? "?"} in / {u.output_tokens ?? "?"} out · ${(u.cost_usd ?? 0).toFixed(4)} ({u.cost_basis})
                </div>
              ))}
              <div className="mt-1 text-faint">{usage.note}</div>
            </div>
          )}
        </Card>
      )}

      <HardwareCard />
      <ModelsPanel />

      <Card className="space-y-3 p-6">
        <h2 className="font-display text-2xl">{t("privacyControls")}</h2>
        <div className="flex flex-wrap gap-2">
          <Button variant="danger" onClick={() => privacy("delete-faces")}>
            {t("deleteFaces")}
          </Button>
          <Button variant="danger" onClick={() => privacy("delete-ai-results")}>
            {t("deleteAI")}
          </Button>
          <Button variant="danger" onClick={() => privacy("delete-embeddings")}>
            {t("deleteEmbeddings")}
          </Button>
          <Button variant="danger" onClick={() => privacy("delete-thumbnails")}>
            {t("deleteThumbs")}
          </Button>
        </div>
        {msg && <div className="text-sm text-good">{msg}</div>}
        <div className="border-t border-line pt-4">
          <Button
            variant="danger"
            onClick={async () => {
              if (!window.confirm(t("areYouSure"))) return;
              await api(`/projects/${pid}`, { method: "DELETE" });
              nav("/");
            }}
          >
            {t("deleteProject")}
          </Button>
          <p className="mt-1 text-xs text-faint">{t("deleteProjectNote")}</p>
        </div>
      </Card>
    </div>
  );
}
