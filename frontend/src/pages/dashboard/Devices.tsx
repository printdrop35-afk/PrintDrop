import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowUpCircle, Download, KeyRound, Loader2, Monitor, Printer, ShieldOff, Star, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useDashboard } from "@/hooks/useDashboard";
import { apiGet, apiPatch, apiPost, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/i18n";
import { cn } from "@/lib/utils";
import { PrinterManager, useAgentCommand } from "@/components/PrinterManager";
import { AgentSetupGuide } from "@/components/AgentSetupGuide";
import type { AgentDownloadOut, AgentOut, CommandOut, NotificationStatusOut, PairingCodeOut, PrinterOut, PrinterUpdateIn } from "@/lib/types";

export default function Devices() {
  const { shop, can } = useDashboard();
  const qc = useQueryClient();
  const manage = can("devices:manage");
  const [pairing, setPairing] = useState<PairingCodeOut | null>(null);

  const agents = useQuery({ queryKey: ["agents", shop.id], queryFn: () => apiGet<AgentOut[]>(`/shops/${shop.id}/agents`), refetchInterval: 5000 });
  const printers = useQuery({ queryKey: ["printers", shop.id], queryFn: () => apiGet<PrinterOut[]>(`/shops/${shop.id}/printers`), refetchInterval: 5000 });
  const dl = useQuery({ queryKey: ["agent-download"], queryFn: () => apiGet<AgentDownloadOut>("/agent-download") });
  const notif = useQuery({ queryKey: ["notif-status"], queryFn: () => apiGet<NotificationStatusOut>("/notifications/status") });

  const code = useMutation({
    mutationFn: () => apiPost<PairingCodeOut>(`/shops/${shop.id}/agents/pairing-code`),
    onSuccess: setPairing,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const [updating, setUpdating] = useState<Record<string, string>>({}); // agent id -> target version
  const lastUpd = useRef("");
  const updCmd = useAgentCommand((c) => {
    if (c.status === "done") toast.success("Installation lancée sur le PC du comptoir : acceptez la demande Windows si elle s'affiche. PrintDrop redémarre tout seul.", { duration: 9000 });
    else { toast.error(c.error || "Le PC n'a pas répondu"); const id = lastUpd.current; setUpdating((u) => Object.fromEntries(Object.entries(u).filter(([k]) => k !== id))); }
  });
  const update = useMutation({
    mutationFn: (a: AgentOut) => apiPost<CommandOut>(`/agents/${a.id}/update`),
    onSuccess: (c, a) => { lastUpd.current = a.id; setUpdating((u) => ({ ...u, [a.id]: a.latest_version })); updCmd.start(c); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => apiPost<AgentOut>(`/agents/${id}/revoke`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["agents", shop.id] }); qc.invalidateQueries({ queryKey: ["printers", shop.id] }); toast.success("Agent révoqué"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const updatePrinter = useMutation({
    mutationFn: ({ id, body }: { id: string; body: PrinterUpdateIn }) => apiPatch<PrinterOut>(`/printers/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["printers", shop.id] }),
    onError: (e) => toast.error(errorMessage(e)),
  });

  const agentList = agents.isError ? [] : agents.data ?? [];
  const outdated = agentList.filter((a) => a.update_available);
  const release = dl.isError ? undefined : dl.data;
  const printerList = printers.isError ? [] : printers.data ?? [];
  const n = notif.isError ? undefined : notif.data;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">{shop.name}</p>
        <h1 className="mt-1 text-3xl font-bold text-ink">Imprimantes & agent</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          L'agent local PrintDrop s'installe sur le PC Windows du comptoir et imprime automatiquement les commandes que vous lancez,
          avec les pilotes de vos imprimantes (Windows 10 et 11, 64 bits). Aucun autre logiciel à installer.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          {outdated.length > 0 && (
            <section className="flex flex-wrap items-start gap-3 rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950" data-testid="agent-update-notice">
              <ArrowUpCircle className="mt-0.5 size-5 shrink-0 text-azure" />
              <div className="min-w-0 flex-1">
                <p className="font-semibold">Nouvelle version de l'agent disponible : v{outdated[0].latest_version}</p>
                <p className="mt-0.5 text-xs">
                  {outdated.map((a) => `${a.name} (v${a.version})`).join(", ")} {outdated.length > 1 ? "utilisent" : "utilise"} une version plus ancienne.
                  Cliquez sur « Mettre à jour en un clic » à côté du poste (il doit être allumé) ou téléchargez l'installateur. L'appairage et les imprimantes sont conservés.
                </p>
                {release?.notes && <p className="mt-1 text-xs text-sky-800" data-testid="agent-update-notes">Nouveautés : {release.notes}</p>}
              </div>
              {release?.available && (
                <a href={release.url} className="inline-flex items-center gap-1.5 rounded-lg bg-azure px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-azure/90" data-testid="agent-update-download">
                  <Download className="size-3.5" /> Mettre à jour
                </a>
              )}
            </section>
          )}
          <section className="rounded-2xl border bg-card">
            <div className="flex items-center justify-between border-b p-5">
              <h2 className="text-lg font-semibold text-ink">Postes associés</h2>
            </div>
            {agentList.length === 0 ? (
              <p className="p-6 text-sm text-muted-foreground" data-testid="agents-empty">Aucun agent associé. Générez un code d'appairage et suivez le guide d'installation.</p>
            ) : (
              <ul className="divide-y" data-testid="agents-list">
                {agentList.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center gap-3 p-4" data-testid={`agent-row-${a.id}`}>
                    <Monitor className="size-5 text-slate-400" />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-ink">{a.name} <span className="text-xs text-muted-foreground">{a.hostname} · v{a.version || "?"}</span>
                        {a.update_available && <span className="ml-2 inline-block whitespace-nowrap rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-semibold text-sky-800" data-testid={`agent-update-badge-${a.id}`}>Mise à jour v{a.latest_version}</span>}</p>
                      <p className="text-xs text-muted-foreground">Dernier contact : {a.last_seen_at ? formatDateTime(a.last_seen_at) : "jamais"}</p>
                    </div>
                    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold",
                      a.status === "revoked" ? "bg-slate-200 text-slate-600" : a.online ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800")} data-testid={`agent-status-${a.id}`}>
                      <span className={cn("size-1.5 rounded-full bg-current", a.online && "animate-pulse-soft")} />
                      {a.status === "revoked" ? "Révoqué" : a.online ? "En ligne" : "Hors ligne"}
                    </span>
                    {updating[a.id] && a.version !== updating[a.id] && (
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-sky-800" data-testid={`agent-updating-${a.id}`}><Loader2 className="size-3.5 animate-spin" /> Mise à jour vers v{updating[a.id]}…</span>
                    )}
                    {updating[a.id] && a.version === updating[a.id] && <span className="text-xs font-semibold text-emerald-700" data-testid={`agent-updated-${a.id}`}>À jour ✓</span>}
                    {manage && a.update_available && a.online && release?.available && (release.size_bytes ?? 0) > 0 && !updating[a.id] && (
                      <Button size="sm" onClick={() => update.mutate(a)} disabled={update.isPending} data-testid={`agent-update-${a.id}`}>
                        <ArrowUpCircle className="size-3.5" /> Mettre à jour en un clic
                      </Button>
                    )}
                    {manage && a.status === "active" && (
                      <Button size="sm" variant="ghost" className="text-rose-700" onClick={() => revoke.mutate(a.id)} data-testid={`agent-revoke-${a.id}`}><ShieldOff className="size-3.5" /> Révoquer</Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <AgentSetupGuide />

          <PrinterManager shopId={shop.id} agents={agents.data ?? []} printers={printerList} manage={manage} />
        </div>

        <aside className="space-y-4">
          {manage && (
            <section className="rounded-2xl border bg-ink p-5 text-white">
              <KeyRound className="size-6 text-sky-400" />
              <h2 className="mt-3 text-lg font-semibold">Associer un nouveau poste</h2>
              <p className="mt-1 text-sm text-slate-300">Code à usage unique, valable 10 minutes.</p>
              {pairing ? (
                <div className="mt-4 rounded-xl bg-white/10 p-4 text-center">
                  <p className="font-mono text-3xl font-bold tracking-[0.2em]" data-testid="pairing-code">{pairing.code}</p>
                  <p className="mt-1 text-xs text-slate-300">Expire à {formatDateTime(pairing.expires_at)}</p>
                  <p className="mt-3 text-left text-xs text-slate-300" data-testid="pairing-command">Sur le PC du comptoir, ouvrez PrintDrop et saisissez ce code.</p>
                </div>
              ) : null}
              <Button className="mt-4 w-full" disabled={code.isPending} onClick={() => code.mutate()} data-testid="generate-pairing-code-button">
                {pairing ? "Générer un nouveau code" : "Générer un code d'appairage"}
              </Button>
            </section>
          )}
          <section className="rounded-2xl border bg-card p-5 text-sm">
            <Download className="size-5 text-azure" />
            <h3 className="mt-2 font-semibold text-ink">Installer l'agent Windows</h3>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
              <li>Sur le PC du comptoir (Windows 10 ou 11), cliquez sur « Télécharger l'agent Windows »</li>
              <li>Ouvrez le fichier. Si Windows affiche « Windows a protégé votre ordinateur », cliquez sur « Informations complémentaires » puis « Exécuter quand même »</li>
              <li>Laissez cochée « Démarrer PrintDrop automatiquement avec Windows » (décochez-la si vous ne le souhaitez pas ; désactivable plus tard dans le Gestionnaire des tâches › Démarrage)</li>
              <li>PrintDrop s'ouvre : saisissez le code d'appairage généré ci-dessus</li>
              <li>Cliquez sur « Ajouter une imprimante » : les imprimantes USB, Wi-Fi et réseau du PC sont détectées</li>
            </ol>
            {release?.available ? (
              <a href={release.url} className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-azure px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-azure/90" data-testid="devices-download-agent">
                <Download className="size-4" /> Télécharger l'agent Windows (v{release.version})
              </a>
            ) : null}
            {release?.available && release.size_bytes > 0 ? (
              <p className="mt-1 text-[11px] text-muted-foreground" data-testid="devices-download-meta">Windows 10/11 · {(release.size_bytes / 1048576).toFixed(1)} Mo · SHA-256 <span className="font-mono">{release.sha256.slice(0, 16)}…</span></p>
            ) : null}
            {release?.available ? null : (
              <p className="mt-3 rounded-lg bg-slate-50 p-2 text-xs text-muted-foreground" data-testid="devices-download-unavailable">L'installateur Windows n'est pas encore publié : le bouton de téléchargement apparaîtra ici dès qu'il aura été compilé, testé et mis en ligne par PrintDrop.</p>
            )}

          </section>
          <section className="rounded-2xl border bg-card p-5 text-sm" data-testid="notification-config">
            <h3 className="font-semibold text-ink">Notifications « commande prête »</h3>
            <p className="mt-2 flex items-center justify-between"><span>E-mail</span><span className={n?.email_configured ? "font-semibold text-emerald-700" : "text-rose-700"} data-testid="email-config-status">{n?.email_configured ? "Actif" : "Non configuré"}</span></p>
            <p className="mt-1 flex items-center justify-between"><span>SMS (Twilio)</span><span className={n?.sms_configured ? "font-semibold text-emerald-700" : "text-rose-700"} data-testid="sms-config-status">{n?.sms_configured ? "Actif" : "Non configuré"}</span></p>
          </section>
          <section className="flex gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900">
            <TriangleAlert className="size-4 shrink-0" />
            Tests matériels requis : recto-verso, couleur, formats, bourrage, imprimante hors ligne, redémarrage pendant impression.
          </section>
        </aside>
      </div>
    </div>
  );
}
