import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, Cable, Loader2, Plus, Printer, RefreshCw, Search, Star, Trash2, Wifi } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut, errorMessage, ApiError } from "@/lib/api";
import { formatDateTime } from "@/i18n";
import { cn } from "@/lib/utils";
import type { AgentOut, CommandOut, DiscoveredNetwork, DiscoveredUsb, InstallPrinterIn, ManualPrinterIn, PrinterOut, PrinterRule, PrinterRulesIO, PrinterUpdateIn } from "@/lib/types";

export const CONN_LABEL: Record<string, string> = {
  usb: "USB", wifi: "Wi-Fi", ethernet: "Ethernet / Réseau", network: "Réseau (Wi-Fi ou Ethernet à préciser)", virtual: "Imprimante virtuelle", unknown: "Inconnue",
};

/** Sends a command to the agent and polls its real result (never fabricated client-side). */
function useAgentCommand(onDone: (c: CommandOut) => void) {
  const [cmdId, setCmdId] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["agent-cmd", cmdId], enabled: !!cmdId, queryFn: () => apiGet<CommandOut>(`/agent-commands/${cmdId}`),
    refetchInterval: (query) => (["queued", "sent"].includes(query.state.data?.status ?? "queued") ? 1500 : false),
  });
  const cmd = q.data && q.data.id === cmdId ? q.data : undefined;
  if (cmd && !["queued", "sent"].includes(cmd.status)) {
    setCmdId(null);
    onDone(cmd);
  }
  return { running: !!cmdId, start: (c: CommandOut) => setCmdId(c.id), status: cmd?.status };
}

/** Official manufacturer driver pages only — never a third-party download site. */
const DRIVER_SITES: [string, string][] = [
  ["hp", "https://support.hp.com/fr-fr/drivers"], ["samsung", "https://support.hp.com/fr-fr/drivers"], ["canon", "https://www.canon.fr/support/"],
  ["epson", "https://www.epson.fr/fr_FR/support"], ["brother", "https://support.brother.com/g/b/countrytop.aspx?c=fr&lang=fr"],
  ["kyocera", "https://www.kyoceradocumentsolutions.eu/fr/support/downloads.html"], ["ricoh", "https://www.ricoh.fr/support"],
  ["xerox", "https://www.support.xerox.com/fr-fr"], ["lexmark", "https://support.lexmark.com/fr_fr.html"], ["konica", "https://www.konicaminolta.fr/fr-fr/support/download-centre"],
  ["sharp", "https://www.sharp.fr/assistance"], ["oki", "https://www.oki.com/fr/printing/support/drivers-and-utilities/"], ["dell", "https://www.dell.com/support/home/fr-fr"],
];
export function driverSite(text: string): string | null {
  const t = text.toLowerCase();
  return DRIVER_SITES.find(([k]) => new RegExp(`\\b${k}`).test(t))?.[1] ?? null;
}

export function DriverGuide({ hint, error }: { hint: string; error?: string }) {
  const site = driverSite(hint);
  return (
    <div className="space-y-1 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950" data-testid="driver-guide">
      {error && <p className="font-medium">{error}</p>}
      <p className="font-semibold">Installer le pilote officiel :</p>
      <ol className="list-decimal space-y-0.5 pl-5 text-xs">
        <li>{site ? <>Ouvrez le site officiel du fabricant : <a href={site} target="_blank" rel="noreferrer" className="font-semibold underline" data-testid="driver-guide-link">{new URL(site).hostname}</a></> : "Ouvrez le site officiel du fabricant de l'imprimante (marque indiquée sur l'appareil)."}</li>
        <li>Recherchez le modèle exact{hint ? ` (« ${hint} »)` : ""} et téléchargez le pilote complet pour Windows 10/11 (impression + scan).</li>
        <li>Lancez l'installation, puis revenez ici et cliquez sur « Rechercher les imprimantes ».</li>
      </ol>
      <p className="text-xs">Ne téléchargez jamais de pilote depuis un autre site que celui du fabricant.</p>
    </div>
  );
}

type Pending = { name: string; hint: string } | null;

function AddPrinterDialog({ shopId, agents, printers, open, onOpenChange }: { shopId: string; agents: AgentOut[]; printers: PrinterOut[]; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const online = agents.filter((a) => a.online && a.status === "active");
  const [agentId, setAgentId] = useState("");
  const [scan, setScan] = useState<CommandOut | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const [guide, setGuide] = useState<{ hint: string; error: string } | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [manual, setManual] = useState<ManualPrinterIn>({ agent_id: "", name: "", host: "", protocol: "ipp", port: null, queue: "", driver_name: "", connection_type: "wifi" });
  const agent = agentId || online[0]?.id || "";
  const refresh = () => qc.invalidateQueries({ queryKey: ["printers", shopId] });
  const connect = useMutation({
    mutationFn: (name: string) => apiPost<CommandOut>(`/shops/${shopId}/printers/connect`, { agent_id: agent, name }),
    onSuccess: (c) => { refresh(); cmd.start(c); },
    onError: (e) => { setBusy(null); toast.error(errorMessage(e)); },
  });
  const cmd = useAgentCommand((c) => {
    refresh();
    if (c.type === "discover_all") { setBusy(null); if (c.status === "done") setScan(c); else toast.error(c.error || "L'agent n'a pas répondu"); return; }
    if (c.type === "install_printer" || c.type === "add_network_printer") {
      if (c.status === "done") { connect.mutate(String(c.result.installed)); return; }
      setBusy(null); setGuide({ hint: pending?.hint ?? "", error: c.error || "Installation impossible" }); return;
    }
    setBusy(null);
    if (c.status === "done") toast.success("Imprimante connectée et vérifiée : elle est prête");
    else toast.error(`Imprimante enregistrée mais pas prête : ${c.error || "l'agent n'a pas répondu"}`);
  });
  const discover = useMutation({
    mutationFn: () => apiPost<CommandOut>(`/shops/${shopId}/printers/discover-all`, { agent_id: agent }),
    onSuccess: (c) => { setScan(null); setGuide(null); setBusy("discover"); cmd.start(c); }, onError: (e) => toast.error(errorMessage(e)),
  });
  const install = useMutation({
    mutationFn: (b: Omit<InstallPrinterIn, "agent_id">) => apiPost<CommandOut>(`/shops/${shopId}/printers/install`, { ...b, agent_id: agent }),
    onSuccess: (c) => cmd.start(c), onError: (e) => { setBusy(null); toast.error(errorMessage(e)); },
  });
  const manualSend = useMutation({
    mutationFn: () => apiPost<CommandOut>(`/shops/${shopId}/printers/manual`, { ...manual, agent_id: agent, port: manual.port || null }),
    onSuccess: (c) => { setBusy("manual"); setPending({ name: manual.name, hint: "" }); cmd.start(c); }, onError: (e) => toast.error(errorMessage(e)),
  });
  const r = scan?.result ?? {};
  const installed = ((r.installed as (PrinterOut & { detail?: string })[] | undefined) ?? []).filter((p) => p.connection_type !== "virtual");
  const network = ((r.network as DiscoveredNetwork[] | undefined) ?? []).filter((d) => !d.already_installed);
  const usb = (r.usb_missing_driver as DiscoveredUsb[] | undefined) ?? [];
  const isConnected = (name: string) => printers.some((p) => p.agent_id === agent && p.name === name && p.enabled);
  const working = busy !== null || cmd.running;
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { setScan(null); setGuide(null); } }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl" data-testid="add-printer-dialog">
        <DialogHeader>
          <DialogTitle>Ajouter une imprimante</DialogTitle>
          <DialogDescription>Branchez l'imprimante en USB ou connectez-la au Wi-Fi / réseau de la boutique, puis lancez la recherche. Le PC du comptoir (agent PrintDrop) s'occupe du reste.</DialogDescription>
        </DialogHeader>
        {online.length === 0 ? (
          <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900" data-testid="add-printer-no-agent">Aucun PC du comptoir en ligne. Installez PrintDrop pour Windows sur ce PC et associez-le (section « Agents » ci-dessus).</p>
        ) : (
          <>
            {online.length > 1 && (
              <Select value={agent} onValueChange={setAgentId}>
                <SelectTrigger className="w-full" data-testid="add-printer-agent"><SelectValue>{(v) => online.find((a) => a.id === v)?.name ?? "PC"}</SelectValue></SelectTrigger>
                <SelectContent>{online.map((a) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent>
              </Select>
            )}
            <Button className="h-11 font-bold" onClick={() => discover.mutate()} disabled={working || discover.isPending} data-testid="add-printer-discover">
              {busy === "discover" ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
              {busy === "discover" ? "Recherche USB, Wi-Fi et réseau… (jusqu'à 1 min)" : scan ? "Relancer la recherche" : "Rechercher les imprimantes"}
            </Button>
            {guide && <DriverGuide hint={guide.hint} error={guide.error} />}
            {scan && (
              <div className="space-y-4" data-testid="discover-results">
                {installed.length + network.length + usb.length === 0 && (
                  <p className="text-sm text-muted-foreground" data-testid="discover-empty">Aucune imprimante trouvée. Vérifiez qu'elle est allumée, branchée en USB à ce PC ou connectée au même réseau, puis relancez.</p>
                )}
                {installed.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Installées dans Windows</p>
                    {installed.map((p, i) => (
                      <div key={p.name} className="flex flex-wrap items-center gap-3 rounded-xl border p-3" data-testid={`found-installed-${i}`}>
                        {p.connection_type === "usb" ? <Cable className="size-5 text-azure" /> : <Wifi className="size-5 text-azure" />}
                        <div className="min-w-0 flex-1 text-sm">
                          <p className="font-semibold text-ink">{p.name}</p>
                          <p className="text-xs text-muted-foreground">{[p.manufacturer, p.model || p.driver_name, CONN_LABEL[p.connection_type], p.ip_address].filter(Boolean).join(" · ")} · {p.status === "online" ? "disponible" : `${p.status === "error" ? "en erreur" : "hors ligne"}${p.detail ? ` (${p.detail})` : ""}`}</p>
                          <p className="text-xs text-muted-foreground">{p.capabilities?.color ? "Couleur" : "N&B"}{p.capabilities?.duplex ? " · recto-verso" : ""}{p.driver_name ? ` · pilote ${p.driver_name}` : " · pilote manquant"}</p>
                        </div>
                        {isConnected(p.name) ? <span className="text-xs font-semibold text-emerald-700" data-testid={`found-installed-${i}-connected`}>Déjà connectée</span>
                          : <Button size="sm" disabled={working} onClick={() => { setBusy(p.name); setPending({ name: p.name, hint: p.driver_name }); connect.mutate(p.name); }} data-testid={`found-installed-${i}-connect`}>
                            {busy === p.name ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />} Connecter cette imprimante</Button>}
                      </div>
                    ))}
                  </div>
                )}
                {network.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Sur le réseau (Wi-Fi / Ethernet) — pas encore installées</p>
                    {network.map((d, i) => {
                      const name = d.model || `Imprimante ${d.ip_address}`;
                      return (
                        <div key={d.ip_address} className="flex flex-wrap items-center gap-3 rounded-xl border p-3" data-testid={`found-network-${i}`}>
                          <Wifi className="size-5 text-azure" />
                          <div className="min-w-0 flex-1 text-sm">
                            <p className="font-semibold text-ink">{d.model || "Modèle non communiqué"}</p>
                            <p className="font-mono text-xs text-muted-foreground">{d.ip_address}{d.hostname ? ` · ${d.hostname}` : ""} · {d.protocols.join(", ")}</p>
                          </div>
                          {d.protocols.includes("ipp") ? (
                            <Button size="sm" disabled={working} data-testid={`found-network-${i}-connect`}
                              onClick={() => { setBusy(d.ip_address); setGuide(null); setPending({ name, hint: d.model }); install.mutate({ kind: "network", name, host: d.ip_address, ipp_path: "ipp/print", device_id: "", manufacturer: d.manufacturer, model: d.model, connection_type: "network" }); }}>
                              {busy === d.ip_address ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />} Connecter cette imprimante</Button>
                          ) : <Button size="sm" variant="outline" onClick={() => setGuide({ hint: d.model || d.hostname, error: "Cette imprimante ne propose pas l'installation automatique (IPP)." })} data-testid={`found-network-${i}-guide`}>Installer le pilote</Button>}
                        </div>
                      );
                    })}
                  </div>
                )}
                {usb.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Appareils USB sans pilote</p>
                    {usb.map((d, i) => (
                      <div key={d.device_id || i} className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-200 p-3" data-testid={`found-usb-${i}`}>
                        <AlertTriangle className="size-5 text-amber-600" />
                        <div className="min-w-0 flex-1 text-sm"><p className="font-semibold text-ink">{d.name}</p><p className="text-xs text-muted-foreground">Windows voit l'appareil mais n'a pas son pilote.</p></div>
                        <Button size="sm" disabled={working} data-testid={`found-usb-${i}-install`}
                          onClick={() => { setBusy(d.device_id); setGuide(null); setPending({ name: d.name, hint: `${d.manufacturer} ${d.name}` }); install.mutate({ kind: "usb", name: d.name.slice(0, 120), host: "", ipp_path: "", device_id: d.device_id, manufacturer: d.manufacturer, model: d.name, connection_type: "usb" }); }}>
                          {busy === d.device_id ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />} Installer automatiquement</Button>
                      </div>
                    ))}
                  </div>
                )}
                {working && busy !== "discover" && <p className="text-xs text-muted-foreground" data-testid="add-printer-working">Installation et vérification en cours… Si Windows affiche une demande d'autorisation administrateur sur le PC du comptoir, acceptez-la.</p>}
              </div>
            )}
            <button type="button" className="text-left text-xs font-semibold text-azure underline" onClick={() => setAdvanced(!advanced)} data-testid="add-printer-advanced-toggle">
              {advanced ? "Masquer" : "Imprimante introuvable ? Configuration avancée (adresse IP)"}
            </button>
            {advanced && (
              <div className="space-y-2 rounded-2xl border p-4" data-testid="manual-printer-form">
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input placeholder="Nom (ex : Couleur A4)" value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })} data-testid="manual-name" />
                  <Input placeholder="Adresse IP ou nom d'hôte" value={manual.host} onChange={(e) => setManual({ ...manual, host: e.target.value.trim() })} className="font-mono" data-testid="manual-host" />
                  <Select value={manual.protocol} onValueChange={(v: string) => setManual({ ...manual, protocol: v as ManualPrinterIn["protocol"] })}>
                    <SelectTrigger className="w-full" data-testid="manual-protocol"><SelectValue>{(v) => ({ ipp: "IPP (port 631)", raw9100: "RAW / JetDirect (9100)", lpd: "LPD (515)" })[v as string]}</SelectValue></SelectTrigger>
                    <SelectContent><SelectItem value="ipp">IPP (port 631)</SelectItem><SelectItem value="raw9100">RAW / JetDirect (9100)</SelectItem><SelectItem value="lpd">LPD (515)</SelectItem></SelectContent>
                  </Select>
                  <Select value={manual.connection_type} onValueChange={(v: string) => setManual({ ...manual, connection_type: v as ManualPrinterIn["connection_type"] })}>
                    <SelectTrigger className="w-full" data-testid="manual-conn"><SelectValue>{(v) => CONN_LABEL[v as string]}</SelectValue></SelectTrigger>
                    <SelectContent><SelectItem value="wifi">Wi-Fi</SelectItem><SelectItem value="ethernet">Ethernet / câble réseau</SelectItem></SelectContent>
                  </Select>
                  <Input placeholder="File / chemin (facultatif, ex : ipp/print)" value={manual.queue} onChange={(e) => setManual({ ...manual, queue: e.target.value })} data-testid="manual-queue" />
                  {manual.protocol !== "ipp" && <Input placeholder="Pilote Windows installé (nom exact)" value={manual.driver_name} onChange={(e) => setManual({ ...manual, driver_name: e.target.value })} data-testid="manual-driver" />}
                </div>
                <Button size="sm" onClick={() => manualSend.mutate()} disabled={!manual.name || !manual.host || working} data-testid="manual-submit">Tester et installer</Button>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Plain-French fix for what Windows reports. */
export function statusHint(detail: string, status: string): string {
  const d = detail.toLowerCase();
  if (d.includes("papier") && d.includes("bourrage")) return "Ouvrez les capots, retirez la feuille coincée, refermez puis réessayez.";
  if (d.includes("plus de papier")) return "Ajoutez du papier dans le bac puis réessayez.";
  if (d.includes("toner") || d.includes("encre")) return "Remplacez la cartouche de toner / d'encre indiquée par l'imprimante.";
  if (d.includes("capot")) return "Refermez le capot de l'imprimante.";
  if (d.includes("hors connexion")) return "Dans Windows, décochez « Utiliser l'imprimante hors connexion » (Paramètres › Imprimantes).";
  if (d.includes("non détectée")) return "Vérifiez que l'imprimante est allumée et que le câble USB ou le Wi-Fi est connecté, puis cliquez sur « Reconnecter ».";
  if (status === "offline") return "Allumez l'imprimante, vérifiez le câble USB ou le Wi-Fi, puis cliquez sur « Reconnecter ».";
  if (status === "error") return "Regardez l'écran de l'imprimante, corrigez le problème puis cliquez sur « Reconnecter ».";
  return "";
}

function PrinterCard({ p, manage, shopId }: { p: PrinterOut; manage: boolean; shopId: string }) {
  const qc = useQueryClient();
  const [name, setName] = useState(p.display_name || p.name);
  const refresh = () => qc.invalidateQueries({ queryKey: ["printers", shopId] });
  const upd = useMutation({ mutationFn: (b: PrinterUpdateIn) => apiPatch<PrinterOut>(`/printers/${p.id}`, b), onSuccess: () => { refresh(); toast.success("Imprimante mise à jour"); }, onError: (e) => toast.error(errorMessage(e)) });
  const cmd = useAgentCommand((c) => { refresh(); return c.status === "done" ? toast.success(c.type === "test_page" ? String(c.result.note ?? "Page de test envoyée") : "Imprimante vérifiée : prête") : toast.error(c.error || "Échec"); });
  const run = useMutation({ mutationFn: (k: "test-connection" | "test-page") => apiPost<CommandOut>(`/printers/${p.id}/${k}`), onSuccess: (c) => cmd.start(c), onError: (e) => toast.error(errorMessage(e)) });
  const del = useMutation({
    mutationFn: (jobs: string) => apiDelete<{ ok: boolean }>(`/printers/${p.id}${jobs ? `?jobs=${jobs}` : ""}`),
    onSuccess: () => { refresh(); toast.success("Imprimante supprimée"); },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409 && window.confirm(`${errorMessage(e)}\n\nOK = renvoyer ces travaux en affectation automatique, Annuler = ne rien faire.`)) del.mutate("reassign");
      else toast.error(errorMessage(e));
    },
  });
  const caps = p.capabilities;
  return (
    <li className={cn("space-y-3 p-4", !p.enabled && "opacity-60")} data-testid={`printer-row-${p.id}`}>
      <div className="flex flex-wrap items-start gap-3">
        <Printer className={cn("mt-0.5 size-5", p.online ? "text-emerald-600" : "text-slate-400")} />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink">{p.display_name || p.name} {p.is_default && <Star className="inline size-3.5 fill-amber-400 text-amber-400" />}</p>
          <p className={cn("text-xs", p.online ? "text-emerald-700" : "text-rose-700")} data-testid={`printer-status-${p.id}`}>
            {p.online ? (p.verified_at ? "Prête" : "Connectée — cliquez sur « Reconnecter » pour la vérifier") : p.status === "error" ? "En erreur" : "Hors ligne"}{p.status_detail ? ` · ${p.status_detail}` : ""}
          </p>
          {!p.online && statusHint(p.status_detail, p.status) && <p className="text-xs text-amber-800" data-testid={`printer-hint-${p.id}`}>{statusHint(p.status_detail, p.status)}</p>}
          {p.driver_ok === false && <div className="mt-2"><DriverGuide hint={p.model || p.name} error="Pilote manquant ou incomplet" /></div>}
          <p className="mt-1 text-xs text-muted-foreground" data-testid={`printer-info-${p.id}`}>
            {CONN_LABEL[p.connection_type]}{p.ip_address ? ` · ${p.ip_address}` : ""} · File Windows « {p.name} » · {p.manufacturer ? `${p.manufacturer} · ` : ""}{p.driver_name || "pilote inconnu"} · Agent {p.agent_name}
            {p.last_seen_at ? ` · vue ${formatDateTime(p.last_seen_at)}` : ""}
          </p>
          <p className="text-xs text-muted-foreground">
            {caps.color === null ? "Couleur non communiquée" : caps.color ? "Couleur + N&B" : "N&B uniquement"} · {caps.duplex === null ? "recto-verso ?" : caps.duplex ? "Recto-verso" : "Recto seul"} · Formats : {caps.paper_sizes.length ? caps.paper_sizes.slice(0, 6).join(", ") : "non communiqués"}
            {p.active_jobs > 0 ? ` · ${p.active_jobs} travail(aux) en cours` : ""}
          </p>
        </div>
      </div>
      {manage && (
        <div className="flex flex-wrap items-center gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} className="h-8 w-48 text-xs" data-testid={`printer-name-${p.id}`} />
          {p.connection_type !== "usb" && p.connection_type !== "virtual" && (
            <Select value={p.connection_confirmed ? p.connection_type : ""} onValueChange={(v: string) => upd.mutate({ connection_type: v as "wifi" | "ethernet" })}>
              <SelectTrigger size="sm" className="w-40" data-testid={`printer-conn-${p.id}`}><SelectValue>{(v) => (v ? CONN_LABEL[v as string] : "Préciser Wi-Fi / Ethernet")}</SelectValue></SelectTrigger>
              <SelectContent><SelectItem value="wifi">Wi-Fi</SelectItem><SelectItem value="ethernet">Ethernet / Réseau</SelectItem></SelectContent>
            </Select>
          )}
          <Button size="xs" variant="outline" onClick={() => upd.mutate({ display_name: name })} data-testid={`printer-save-${p.id}`}>Renommer</Button>
          <Button size="xs" variant="outline" disabled={cmd.running} onClick={() => run.mutate("test-connection")} data-testid={`printer-test-conn-${p.id}`}>Reconnecter</Button>
          <Button size="xs" variant="outline" disabled={cmd.running} onClick={() => run.mutate("test-page")} data-testid={`printer-test-page-${p.id}`}>Tester l'imprimante</Button>
          {!p.is_default && <Button size="xs" variant="outline" onClick={() => upd.mutate({ is_default: true })} data-testid={`printer-default-${p.id}`}>Définir comme imprimante par défaut</Button>}
          <label className="flex items-center gap-1.5 text-xs"><Checkbox checked={p.enabled} onCheckedChange={(c: boolean) => upd.mutate({ enabled: c })} data-testid={`printer-enabled-${p.id}`} />Activée</label>
          <Button size="xs" variant="ghost" className="text-rose-600" onClick={() => window.confirm("Supprimer l'imprimante de PrintDrop ?") && del.mutate("")} data-testid={`printer-delete-${p.id}`}><Trash2 className="size-3.5" />Supprimer l'imprimante</Button>
          {cmd.running && <Loader2 className="size-4 animate-spin text-azure" />}
        </div>
      )}
    </li>
  );
}

function RulesEditor({ shopId, printers }: { shopId: string; printers: PrinterOut[] }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["printer-rules", shopId], queryFn: () => apiGet<PrinterRulesIO>(`/shops/${shopId}/printer-rules`) });
  const [draft, setDraft] = useState<PrinterRule[] | null>(null);
  const rules = draft ?? q.data?.rules ?? [];
  const save = useMutation({ mutationFn: () => apiPut<PrinterRulesIO>(`/shops/${shopId}/printer-rules`, { rules }), onSuccess: () => { setDraft(null); qc.invalidateQueries({ queryKey: ["printer-rules", shopId] }); toast.success("Affectation enregistrée"); }, onError: (e) => toast.error(errorMessage(e)) });
  const set = (i: number, patch: Partial<PrinterRule>) => setDraft(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  if (printers.length < 2) return null;
  const pname = (id: string) => printers.find((p) => p.id === id)?.display_name || printers.find((p) => p.id === id)?.name || "?";
  return (
    <section className="rounded-2xl border bg-card p-5" data-testid="printer-rules">
      <h2 className="text-lg font-semibold text-ink">Affectation automatique</h2>
      <p className="text-xs text-muted-foreground">La première règle compatible et disponible s'applique ; sinon l'imprimante par défaut. Choix manuel possible sur chaque commande.</p>
      <div className="mt-3 space-y-2">
        {rules.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 text-sm" data-testid={`printer-rule-${i}`}>
            Format
            <Select value={r.paper_size} onValueChange={(v: string) => set(i, { paper_size: v })}><SelectTrigger size="sm" className="w-24"><SelectValue>{(v) => (v === "any" ? "Tous" : (v as string))}</SelectValue></SelectTrigger>
              <SelectContent>{["any", "A4", "A3", "A5", "Letter", "Legal"].map((s) => <SelectItem key={s} value={s}>{s === "any" ? "Tous" : s}</SelectItem>)}</SelectContent></Select>
            mode
            <Select value={r.color} onValueChange={(v: string) => set(i, { color: v as PrinterRule["color"] })}><SelectTrigger size="sm" className="w-28"><SelectValue>{(v) => ({ any: "Tous", bw: "N&B", color: "Couleur" })[v as string]}</SelectValue></SelectTrigger>
              <SelectContent><SelectItem value="any">Tous</SelectItem><SelectItem value="bw">N&B</SelectItem><SelectItem value="color">Couleur</SelectItem></SelectContent></Select>
            →
            <Select value={r.printer_id} onValueChange={(v: string) => set(i, { printer_id: v })}><SelectTrigger size="sm" className="w-48"><SelectValue>{(v) => pname(v as string)}</SelectValue></SelectTrigger>
              <SelectContent>{printers.map((p) => <SelectItem key={p.id} value={p.id}>{p.display_name || p.name}</SelectItem>)}</SelectContent></Select>
            <button type="button" aria-label="Supprimer" onClick={() => setDraft(rules.filter((_, j) => j !== i))}><Trash2 className="size-4 text-rose-600" /></button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <Button size="sm" variant="outline" onClick={() => setDraft([...rules, { id: "", service: "print", paper_size: "any", color: "any", printer_id: printers[0].id }])} data-testid="printer-rule-add"><Plus className="size-4" />Ajouter une règle</Button>
        {draft && <Button size="sm" onClick={() => save.mutate()} data-testid="printer-rules-save">Enregistrer</Button>}
      </div>
    </section>
  );
}

export function PrinterManager({ shopId, agents, printers, manage }: { shopId: string; agents: AgentOut[]; printers: PrinterOut[]; manage: boolean }) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  return (
    <>
      <section className="rounded-2xl border bg-card">
        <div className="flex flex-wrap items-center gap-3 border-b p-5">
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-ink">Imprimantes</h2>
            <p className="text-xs text-muted-foreground">Uniquement les imprimantes réellement détectées par vos agents Windows (actualisé toutes les 5 s).</p>
          </div>
          <Button variant="outline" onClick={() => qc.invalidateQueries({ queryKey: ["printers", shopId] })} data-testid="printers-refresh"><RefreshCw className="size-4" /> Actualiser</Button>
          {manage && <Button className="h-11 px-5 font-bold" onClick={() => setOpen(true)} data-testid="add-printer-button"><Plus className="size-4" /> Ajouter une imprimante</Button>}
        </div>
        {printers.length === 0 ? <p className="p-6 text-sm text-muted-foreground" data-testid="printers-empty">Aucune imprimante remontée pour l'instant.</p>
          : <ul className="divide-y" data-testid="printers-list">{printers.map((p) => <PrinterCard key={p.id} p={p} manage={manage} shopId={shopId} />)}</ul>}
      </section>
      {manage && <RulesEditor shopId={shopId} printers={printers.filter((p) => p.enabled)} />}
      <AddPrinterDialog shopId={shopId} agents={agents} printers={printers} open={open} onOpenChange={setOpen} />
    </>
  );
}
