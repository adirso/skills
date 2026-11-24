import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AlertTriangle, Cloud, HardDrive, Terminal } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Badge, Button, Card, ErrorNote, Field, inputCls } from "./ui";

/** Choose the AI provider for a project, with explicit cloud consent. */
export function ProviderPanel({ pid, compact }: { pid: string; compact?: boolean }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [err, setErr] = useState<unknown>(null);
  const { data: global, refetch: refetchGlobal } = useQuery({ queryKey: ["providers"], queryFn: () => api("/ai/providers") });
  const { data: s, refetch } = useQuery({ queryKey: ["ai", pid], queryFn: () => api(`/projects/${pid}/ai`) });
  const { data: ollama, refetch: refetchOllama } = useQuery({
    queryKey: ["ollama"],
    queryFn: () => api("/ollama"),
    refetchInterval: (q) => (Object.values((q.state.data as any)?.pulls ?? {}).some((p: any) => p.status && !["success", "error"].includes(p.status)) ? 1500 : false),
  });
  const { data: hw } = useQuery({ queryKey: ["hardware"], queryFn: () => api("/hardware") });
  const [key, setKey] = useState("");
  const current = s?.provider?.id ?? "none";
  const isCloud = current === "anthropic_api" || current === "claude_code";
  const consent = isCloud ? s?.consents?.[current] : true;

  const choose = async (id: string, model = "") => {
    setErr(null);
    try {
      const defModel = id === "anthropic_api" ? "claude-opus-5-5" : id === "ollama" ? hw?.recommendation?.ollama_model ?? "" : "";
      await api(`/projects/${pid}/ai/provider`, { method: "PUT", body: { id, model: model || (id === current ? s?.provider?.model : "") || defModel, options: s?.provider?.options ?? {} } });
      await refetch();
      qc.invalidateQueries({ queryKey: ["dashboard", pid] });
    } catch (e) {
      setErr(e);
    }
  };
  const giveConsent = async (accepted: boolean) => {
    await api(`/projects/${pid}/ai/consent`, { body: { provider: current, accepted, warning_text: global.cloud_warning } });
    refetch();
  };
  const caps = (id: string) => global?.providers?.find((p: any) => p.id === id);

  const options = [
    { id: "none", icon: HardDrive, title: t("providerLocalOnly"), body: t("aiNoneNote") },
    { id: "ollama", icon: HardDrive, title: t("aiLocal"), body: t("aiLocalBody") },
    { id: "claude_code", icon: Terminal, title: t("aiClaudeCode"), body: t("aiClaudeCodeBody") },
    { id: "anthropic_api", icon: Cloud, title: t("aiApi"), body: t("aiApiBody") },
  ];

  return (
    <div className="space-y-4">
      <div className={clsx("grid gap-3", compact ? "sm:grid-cols-2" : "md:grid-cols-2")}>
        {options.map((o) => {
          const c = caps(o.id);
          return (
            <button
              key={o.id}
              onClick={() => choose(o.id)}
              className={clsx("rounded-2xl border p-4 text-start transition-colors", current === o.id ? "border-accent bg-accent/5" : "border-line bg-surface hover:border-faint")}
            >
              <div className="flex items-center gap-2">
                <o.icon size={16} className="text-accent" />
                <span className="font-medium">{o.title}</span>
                {o.id !== "none" && c && <Badge tone={c.available ? "good" : "neutral"}>{c.available ? "✓" : "—"}</Badge>}
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{o.body}</p>
              {c && o.id !== "none" && <p className="mt-1 text-xs text-faint">{c.status}</p>}
            </button>
          );
        })}
      </div>
      <ErrorNote error={err} />

      {current === "ollama" && (
        <Card className="p-4">
          <h4 className="mb-2 font-medium">{t("ollamaTitle")}</h4>
          {!ollama?.status?.running ? (
            <p className="text-sm text-warn">{t("ollamaNotRunning")}</p>
          ) : (
            <div className="space-y-2 text-sm">
              {hw?.recommendation?.ollama_candidates?.map((m: any) => {
                const installed = ollama.models.some((x: any) => x.name === m.name);
                const pull = ollama.pulls?.[m.name];
                const fits = m.min_ram_gb <= (hw.info.ram_gb ?? 0);
                return (
                  <div key={m.name} className="flex flex-wrap items-center gap-2">
                    <input type="radio" name="ollama-model" checked={s?.provider?.model === m.name} disabled={!installed} onChange={() => choose("ollama", m.name)} />
                    <span className={clsx(!fits && "text-faint")}>{m.name}</span>
                    <Badge>{m.download_gb} GB</Badge>
                    {m.name === hw.recommendation.ollama_model && <Badge tone="accent">{t("recommended")}</Badge>}
                    <span className="text-xs text-faint">{m.note}</span>
                    {!installed && !pull && fits && (
                      <Button size="sm" onClick={() => api("/ollama/pull", { body: { model: m.name, approved: true } }).then(() => refetchOllama())}>
                        {t("approveDownload", { size: `${m.download_gb} GB` })}
                      </Button>
                    )}
                    {pull && pull.status !== "success" && (
                      <span className="text-xs text-muted">
                        {pull.status} {pull.total ? `${Math.round((100 * (pull.completed ?? 0)) / pull.total)}%` : ""}
                      </span>
                    )}
                  </div>
                );
              })}
              {ollama.models
                .filter((x: any) => x.vision && !hw?.recommendation?.ollama_candidates?.some((c: any) => c.name === x.name))
                .map((x: any) => (
                  <label key={x.name} className="flex items-center gap-2">
                    <input type="radio" name="ollama-model" checked={s?.provider?.model === x.name} onChange={() => choose("ollama", x.name)} /> {x.name}
                    <Badge>{x.size_gb} GB</Badge>
                  </label>
                ))}
            </div>
          )}
        </Card>
      )}

      {isCloud && (
        <Card className="border-warn/40 p-4">
          <div className="flex gap-3">
            <AlertTriangle className="mt-0.5 shrink-0 text-warn" size={20} />
            <div className="min-w-0 flex-1">
              <h4 className="font-medium text-warn">{t("cloudWarningTitle")}</h4>
              <p className="mt-1 text-sm text-fg">{global?.cloud_warning}</p>
              <p className="mt-2 text-xs text-muted">{caps(current)?.cost_note}</p>
              {current === "claude_code" && (
                <p className="mt-2 text-xs text-muted">
                  Runs <code>claude -p</code> on this computer with all tools disabled. This app never reads your Claude Code credentials. Experimental: verify with the test button after
                  Claude Code updates.
                </p>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {consent ? (
                  <>
                    <Badge tone="good">{t("consentGiven")}</Badge>
                    <Button size="sm" variant="ghost" onClick={() => giveConsent(false)}>
                      {t("revokeConsent")}
                    </Button>
                  </>
                ) : (
                  <Button size="sm" variant="primary" onClick={() => giveConsent(true)}>
                    {t("iAgree")}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Card>
      )}

      {current === "anthropic_api" && (
        <Card className="space-y-4 p-4">
          <Field label="Model">
            <select className={inputCls} value={s?.provider?.model} onChange={(e) => choose("anthropic_api", e.target.value)}>
              {caps("anthropic_api")?.models?.map((m: any) => (
                <option key={m.id} value={m.id}>
                  {m.label} — {m.note}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("apiKey")} hint={global?.api_key_source ? t("apiKeyStored", { where: global.api_key_source }) : undefined}>
            <div className="flex gap-2">
              <input type="password" autoComplete="off" className={inputCls} value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-ant-…" />
              <Button
                onClick={async () => {
                  await api("/secrets/anthropic", { method: "PUT", body: { key } });
                  setKey("");
                  refetchGlobal();
                }}
                disabled={!key}
              >
                {t("save")}
              </Button>
              {global?.api_key_source && global.api_key_source !== "environment" && (
                <Button variant="ghost" onClick={() => api("/secrets/anthropic", { method: "DELETE" }).then(() => refetchGlobal())}>
                  {t("delete")}
                </Button>
              )}
            </div>
          </Field>
          <SpendingLimit pid={pid} value={s?.spending_limit_usd} spent={s?.spent_usd?.anthropic_api} onSaved={refetch} />
          <p className="text-xs text-faint">
            Prices as of {global?.pricing_as_of}.{" "}
            <a className="underline" href={global?.pricing_url} target="_blank" rel="noreferrer">
              Verify current pricing
            </a>
            .
          </p>
        </Card>
      )}
    </div>
  );
}

function SpendingLimit({ pid, value, spent, onSaved }: { pid: string; value: number | null; spent?: number; onSaved: () => void }) {
  const { t } = useI18n();
  const [v, setV] = useState<string>(value == null ? "" : String(value));
  return (
    <Field label={t("spendingLimit")} hint={`${t("spendingLimitNote")} · spent so far: $${(spent ?? 0).toFixed(2)}`}>
      <div className="flex gap-2">
        <input type="number" min={0} step={1} className={inputCls} value={v} onChange={(e) => setV(e.target.value)} placeholder="e.g. 10" />
        <Button onClick={() => api(`/projects/${pid}/ai/spending-limit`, { method: "PUT", body: { limit_usd: v === "" ? null : Number(v) } }).then(onSaved)}>{t("save")}</Button>
      </div>
    </Field>
  );
}
