import { useQuery } from "@tanstack/react-query";
import { Check, Cpu, Download, HardDrive, MemoryStick } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Badge, Button, Card, ErrorNote, fmtBytes, Progress } from "./ui";

export function HardwareCard() {
  const { t } = useI18n();
  const { data } = useQuery({ queryKey: ["hardware"], queryFn: () => api("/hardware") });
  if (!data) return <Card className="p-5 text-sm text-muted">{t("loading")}</Card>;
  const { info, recommendation } = data;
  return (
    <Card className="p-5">
      <h3 className="mb-3 font-display text-xl">{t("hardwareTitle")}</h3>
      <div className="grid gap-3 text-sm sm:grid-cols-3">
        <div className="flex items-center gap-2">
          <Cpu size={16} className="text-accent" />
          <div>
            <div className="text-fg">{info.cpu}</div>
            <div className="text-xs text-faint">
              {info.arch} · {info.cpu_cores} cores
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <MemoryStick size={16} className="text-accent" />
          <div>
            <div className="text-fg">{info.ram_gb} GB</div>
            <div className="text-xs text-faint">{t("ram")}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <HardDrive size={16} className="text-accent" />
          <div>
            <div className="text-fg">{info.gpus?.[0] ? `${info.gpus[0].api} · ${info.gpus[0].memory_gb ?? "?"} GB` : "—"}</div>
            <div className="text-xs text-faint">
              {t("accelerator")}: {info.accelerator.toUpperCase()}
            </div>
          </div>
        </div>
      </div>
      <p className="mt-4 text-sm text-muted">{recommendation.speed_estimate}</p>
      <p className="mt-1 text-xs text-faint">{recommendation.note}</p>
    </Card>
  );
}

export function ModelsPanel() {
  const { t } = useI18n();
  const [err, setErr] = useState<unknown>(null);
  const { data: models, refetch } = useQuery({
    queryKey: ["models"],
    queryFn: () => api<any[]>("/models"),
    refetchInterval: (q) => ((q.state.data as any[] | undefined)?.some((m) => m.download?.state === "downloading") ? 1000 : false),
  });
  if (!models) return null;
  const missing = models.filter((m) => !m.installed);
  const size = missing.reduce((s, m) => s + m.size_bytes, 0);
  const download = async () => {
    setErr(null);
    try {
      await api("/models/download", { body: { ids: missing.map((m) => m.id), approved: true } });
      refetch();
    } catch (e) {
      setErr(e);
    }
  };
  return (
    <Card className="p-5">
      <h3 className="font-display text-xl">{t("modelsTitle")}</h3>
      <p className="mb-4 mt-1 text-sm text-muted">{t("modelsBody")}</p>
      <div className="space-y-3">
        {models.map((m) => (
          <div key={m.id} className="flex items-start gap-3 text-sm">
            <div className="mt-0.5">{m.installed ? <Check size={16} className="text-good" /> : <Download size={16} className="text-faint" />}</div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-fg">{m.name}</span>
                <Badge>{fmtBytes(m.size_bytes)}</Badge>
                <a href={m.license_url} target="_blank" rel="noreferrer" className="text-xs text-faint underline">
                  {m.license}
                </a>
              </div>
              <div className="text-xs text-muted">
                {m.purpose} <span className="text-faint">· {m.required_for}</span>
              </div>
              {m.download?.state === "downloading" && <Progress value={m.download.received / m.download.total} className="mt-1.5" />}
              {m.download?.state === "error" && <div className="text-xs text-bad">{m.download.error}</div>}
            </div>
          </div>
        ))}
      </div>
      <ErrorNote error={err} />
      {missing.length > 0 && (
        <Button variant="primary" className="mt-4" onClick={download} disabled={missing.some((m) => m.download?.state === "downloading")}>
          <Download size={15} /> {t("approveDownload", { size: fmtBytes(size) })}
        </Button>
      )}
    </Card>
  );
}
