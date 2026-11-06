import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Cable, Loader2, Plus, Printer, Star, Trash2, Wifi } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut, errorMessage, ApiError } from "@/lib/api";
import { formatDateTime } from "@/i18n";
import { cn } from "@/lib/utils";
import type { AgentOut, CommandOut, ManualPrinterIn, PrinterOut, PrinterRule, PrinterRulesIO, PrinterUpdateIn } from "@/lib/types";

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

function AddPrinterDialog({ shopId, agents, open, onOpenChange }: { shopId: string; agents: AgentOut[]; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const online = agents.filter((a) => a.online && a.status === "active");
  const [mode, setMode] = useState<"" | "network" | "usb">("");
  const [agentId, setAgentId] = useState("");
  const [result, setResult] = useState<CommandOut | null>(null);
  const [manual, setManual] = useState<ManualPrinterIn>({ agent_id: "", name: "", host: "", protocol: "ipp", port: null, queue: "", driver_name: "", connection_type: "wifi" });
  const agent = agentId || online[0]?.id || "";
  const cmd = useAgentCommand((c) => {
    setResult(c);
    qc.invalidateQueries({ queryKey: ["printers", shopId] });
    if (c.status !== "done") toast.error(c.error || "L'agent n'a pas répondu");
  });
  const send = useMutation({
    mutationFn: (kind: "discover" | "manual") => kind === "discover"
      ? apiPost<CommandOut>(`/shops/${shopId}/printers/discover`, { agent_id: agent, kind: mode })
      : apiPost<CommandOut>(`/shops/${shopId}/printers/manual`, { ...manual, agent_id: agent, port: manual.port || null }),
    onSuccess: (c) => { setResult(null); cmd.start(c); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const devices = (result?.result.devices as { ip_address: string; hostname: string; protocols: string[]; already_installed: boolean }[] | undefined) ?? [];
  const usb = (result?.result.printers as PrinterOut[] | undefined) ?? [];
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { setMode(""); setResult(null); } }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl" data-testid="add-printer-dialog">
        <DialogHeader>
          <DialogTitle>Ajouter une imprimante</DialogTitle>
          <DialogDescription>L'imprimante est pilotée par l'agent PrintDrop installé sur le PC du comptoir — elle ne se connecte pas directement au cloud.</DialogDescription>
        </DialogHeader>
        {online.length === 0 ? (
          <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900" data-testid="add-printer-no-agent">Aucun agent Windows en ligne. Installez et associez PrintDrop pour Windows d'abord.</p>
        ) : (
          <>
            {online.length > 1 && (
              <Select value={agent} onValueChange={setAgentId}>
                <SelectTrigger className="w-full" data-testid="add-printer-agent"><SelectValue>{(v) => online.find((a) => a.id === v)?.name ?? "PC"}</SelectValue></SelectTrigger>
                <SelectContent>{online.map((a) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent>
              </Select>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              {([["network", Wifi, "Connexion Wi-Fi / Réseau", "Imprimante reliée au réseau de la boutique (Wi-Fi ou câble Ethernet). L'agent la recherche sur le réseau local ; sinon, saisissez son adresse IP."],
                ["usb", Cable, "Connexion par câble USB", "Imprimante branchée en USB sur le PC où tourne l'agent, avec son pilote installé dans Windows."]] as const).map(([k, Icon, title, text]) => (
                <button key={k} type="button" onClick={() => { setMode(k); setResult(null); }} data-testid={`add-printer-mode-${k}`}
                  className={cn("rounded-2xl border p-4 text-left transition-[border-color,box-shadow]", mode === k ? "border-azure shadow-md" : "hover:border-slate-400")}>
                  <Icon className="size-6 text-azure" /><p className="mt-2 font-semibold text-ink">{title}</p><p className="mt-1 text-xs text-muted-foreground">{text}</p>
                </button>
              ))}
            </div>
            {mode && (
              <Button onClick={() => send.mutate("discover")} disabled={cmd.running || send.isPending} data-testid="add-printer-discover">
                {cmd.running ? <Loader2 className="size-4 animate-spin" /> : <Printer className="size-4" />}
                {cmd.running ? "Recherche par l'agent…" : mode === "usb" ? "Détecter les imprimantes USB" : "Rechercher sur le réseau local"}
              </Button>
            )}
            {result?.status === "done" && mode === "usb" && (
              <div data-testid="usb-results">{usb.length === 0 ? <p className="text-sm text-muted-foreground">Aucune imprimante USB installée dans Windows. Branchez-la, installez son pilote, puis relancez.</p>
                : usb.map((p) => <p key={p.name} className="text-sm">✓ {p.name} — {p.driver_name || "pilote ?"} — {p.status === "online" ? "prête" : p.status}. <span className="text-muted-foreground">Ajoutée à la liste ci-dessous.</span></p>)}</div>
            )}
            {result?.status === "done" && mode === "network" && (
              <div className="space-y-1" data-testid="network-results">
                {devices.length === 0 ? <p className="text-sm text-muted-foreground">Aucun appareil d'impression n'a répondu sur le réseau local. Utilisez la configuration manuelle.</p>
                  : devices.map((d) => (
                    <div key={d.ip_address} className="flex flex-wrap items-center gap-2 rounded-lg border p-2 text-sm">
                      <span className="font-mono">{d.ip_address}</span><span className="text-muted-foreground">{d.hostname}</span><span className="text-xs">{d.protocols.join(", ")}</span>
                      {d.already_installed ? <span className="text-xs text-emerald-700">déjà installée</span>
                        : <Button size="xs" variant="outline" onClick={() => setManual({ ...manual, host: d.ip_address, protocol: d.protocols.includes("ipp") ? "ipp" : "raw9100", name: manual.name || `Imprimante ${d.ip_address}` })}>Configurer</Button>}
                    </div>
                  ))}
              </div>
            )}
            {mode === "network" && (
              <div className="space-y-2 rounded-2xl border p-4" data-testid="manual-printer-form">
                <p className="text-sm font-semibold text-ink">Configuration manuelle</p>
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
                <Button size="sm" onClick={() => send.mutate("manual")} disabled={!manual.name || !manual.host || cmd.running} data-testid="manual-submit">Tester et installer</Button>
                {result?.status === "done" && result.type === "add_network_printer" && <p className="text-sm text-emerald-700" data-testid="manual-success">Installée dans Windows : {String(result.result.installed)} — elle apparaîtra ci-dessous au prochain signal de l'agent.</p>}
              </div>
            )}
            {result && result.status !== "done" && <p className="text-sm text-rose-700" data-testid="add-printer-error">{result.error || "Échec"}</p>}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PrinterCard({ p, manage, shopId }: { p: PrinterOut; manage: boolean; shopId: string }) {
  const qc = useQueryClient();
  const [name, setName] = useState(p.display_name || p.name);
  const refresh = () => qc.invalidateQueries({ queryKey: ["printers", shopId] });
  const upd = useMutation({ mutationFn: (b: PrinterUpdateIn) => apiPatch<PrinterOut>(`/printers/${p.id}`, b), onSuccess: () => { refresh(); toast.success("Imprimante mise à jour"); }, onError: (e) => toast.error(errorMessage(e)) });
  const cmd = useAgentCommand((c) => (c.status === "done" ? toast.success(c.type === "test_page" ? String(c.result.note ?? "Page de test envoyée") : "Connexion vérifiée par l'agent") : toast.error(c.error || "Échec")));
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
            {p.online ? "Prête" : p.status === "error" ? "En erreur" : "Hors ligne"}{p.status_detail ? ` · ${p.status_detail}` : ""}
          </p>
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
          <Button size="xs" variant="outline" onClick={() => upd.mutate({ display_name: name })} data-testid={`printer-save-${p.id}`}>Modifier les paramètres</Button>
          <Button size="xs" variant="outline" disabled={cmd.running} onClick={() => run.mutate("test-connection")} data-testid={`printer-test-conn-${p.id}`}>Tester la connexion</Button>
          <Button size="xs" variant="outline" disabled={cmd.running} onClick={() => run.mutate("test-page")} data-testid={`printer-test-page-${p.id}`}>Imprimer une page de test</Button>
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
  return (
    <>
      <section className="rounded-2xl border bg-card">
        <div className="flex flex-wrap items-center gap-3 border-b p-5">
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-ink">Imprimantes</h2>
            <p className="text-xs text-muted-foreground">Uniquement les imprimantes réellement détectées par vos agents Windows (actualisé toutes les 5 s).</p>
          </div>
          {manage && <Button onClick={() => setOpen(true)} data-testid="add-printer-button"><Plus className="size-4" /> Ajouter une imprimante</Button>}
        </div>
        {printers.length === 0 ? <p className="p-6 text-sm text-muted-foreground" data-testid="printers-empty">Aucune imprimante remontée pour l'instant.</p>
          : <ul className="divide-y" data-testid="printers-list">{printers.map((p) => <PrinterCard key={p.id} p={p} manage={manage} shopId={shopId} />)}</ul>}
      </section>
      {manage && <RulesEditor shopId={shopId} printers={printers.filter((p) => p.enabled)} />}
      <AddPrinterDialog shopId={shopId} agents={agents} open={open} onOpenChange={setOpen} />
    </>
  );
}
