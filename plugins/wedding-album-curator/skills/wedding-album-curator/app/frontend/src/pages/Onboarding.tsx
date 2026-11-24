import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, FolderSearch, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { TopControls } from "../App";
import { HardwareCard, ModelsPanel } from "../components/ModelsPanel";
import { ProviderPanel } from "../components/ProviderPanel";
import { Button, Card, ErrorNote, Field, inputCls } from "../components/ui";
import { useI18n } from "../i18n";

const STEPS = ["stepWelcome", "stepFolder", "stepAI", "stepHardware", "stepPrivacy", "stepStart"];

export default function Onboarding() {
  const { t } = useI18n();
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [check, setCheck] = useState<any>(null);
  const [pid, setPid] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data: ai } = useQuery({ queryKey: ["ai", pid], queryFn: () => api(`/projects/${pid}/ai`), enabled: !!pid });

  const browse = async () => {
    setErr(null);
    const r = await api("/pick-folder", { method: "POST" });
    if (r.path) {
      setPath(r.path);
      validate(r.path);
    }
  };
  const validate = async (p = path) => {
    setErr(null);
    setCheck(null);
    try {
      setCheck(await api("/validate-folder", { body: { path: p } }));
    } catch (e) {
      setErr(e);
    }
  };
  const createProject = async () => {
    setBusy(true);
    setErr(null);
    try {
      const p = await api("/projects", { body: { name, source_dir: check.path } });
      setPid(p.id);
      setStep(2);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  const start = async () => {
    await api(`/projects/${pid}/analyze`, { method: "POST" });
    nav(`/p/${pid}`);
  };
  const cloud = ai?.provider?.id === "anthropic_api" || ai?.provider?.id === "claude_code";
  const cloudBlocked = cloud && !ai?.consents?.[ai.provider.id];

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div className="font-display text-2xl text-accent">{t("appName")}</div>
        <TopControls />
      </div>
      <ol className="mb-8 flex flex-wrap gap-2">
        {STEPS.map((s, i) => (
          <li key={s} className={clsx("flex items-center gap-1.5 rounded-full px-3 py-1 text-xs", i === step ? "bg-accent text-accent-ink" : i < step ? "bg-raised text-fg" : "text-faint")}>
            {i < step ? <Check size={12} /> : <span>{i + 1}</span>} {t(s)}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <Card className="p-8">
          <h1 className="font-display text-4xl">{t("welcomeTitle")}</h1>
          <p className="mt-4 leading-relaxed text-muted">{t("welcomeBody")}</p>
          <Button variant="primary" className="mt-8" onClick={() => setStep(1)}>
            {t("continue")}
          </Button>
        </Card>
      )}

      {step === 1 && (
        <Card className="space-y-5 p-8">
          <Field label={t("projectName")}>
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("projectNamePh")} />
          </Field>
          <Field label={t("folderPath")} hint={t("folderHint")}>
            <div className="flex gap-2">
              <input className={inputCls} dir="ltr" value={path} onChange={(e) => setPath(e.target.value)} onBlur={() => path && validate()} placeholder="/Users/…/Wedding" />
              <Button onClick={browse}>
                <FolderSearch size={16} /> {t("browse")}
              </Button>
            </div>
          </Field>
          {check && <div className="text-sm text-good">✓ {t("photosFound", { n: check.photo_count.toLocaleString() })}</div>}
          <ErrorNote error={err} />
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setStep(0)}>
              {t("back")}
            </Button>
            <Button variant="primary" disabled={!check || check.photo_count === 0 || busy} onClick={createProject}>
              {t("continue")}
            </Button>
          </div>
        </Card>
      )}

      {step === 2 && pid && (
        <div className="space-y-5">
          <h2 className="font-display text-3xl">{t("aiChoiceTitle")}</h2>
          <ProviderPanel pid={pid} />
          <div className="flex gap-2">
            <Button variant="primary" onClick={() => setStep(3)}>
              {t("continue")}
            </Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-5">
          <HardwareCard />
          <ModelsPanel />
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setStep(2)}>
              {t("back")}
            </Button>
            <Button variant="primary" onClick={() => setStep(4)}>
              {t("continue")}
            </Button>
          </div>
        </div>
      )}

      {step === 4 && (
        <Card className="p-8">
          <div className="flex items-center gap-2">
            <ShieldCheck className="text-good" />
            <h2 className="font-display text-3xl">{t("privacyTitle")}</h2>
          </div>
          <ul className="mt-5 space-y-3 text-sm">
            {["privacy1", "privacy2", "privacy3", "privacy4"].map((k) => (
              <li key={k} className="flex gap-2">
                <Check size={16} className="mt-0.5 shrink-0 text-good" /> {t(k)}
              </li>
            ))}
          </ul>
          {cloudBlocked && <div className="mt-5 rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn">{t("cloudWarningTitle")}: consent is still required (step 3).</div>}
          <div className="mt-8 flex gap-2">
            <Button variant="ghost" onClick={() => setStep(3)}>
              {t("back")}
            </Button>
            <Button variant="primary" onClick={() => setStep(5)}>
              {t("continue")}
            </Button>
          </div>
        </Card>
      )}

      {step === 5 && (
        <Card className="p-8 text-center">
          <h2 className="font-display text-3xl">{t("startAnalysis")}</h2>
          <p className="mx-auto mt-3 max-w-md text-sm text-muted">
            {t("photosFound", { n: check?.photo_count?.toLocaleString() ?? "?" })}. {t("aiNoneNote")}
          </p>
          <Button variant="primary" className="mt-8" onClick={start}>
            {t("startAnalysis")}
          </Button>
        </Card>
      )}
    </div>
  );
}
