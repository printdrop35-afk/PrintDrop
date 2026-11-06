import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download, Loader2, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiGet, apiPost, errorMessage } from "@/lib/api";
import { formatDateTime, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import { useDashboard } from "@/hooks/useDashboard";
import type { OrderOut, PrintCheckOut, PrintDirectIn, PrintJobOut, PrinterOut } from "@/lib/types";

/** « IMPRIMER DIRECTEMENT » — server checks everything; the browser only chooses (optionally) a printer. */
export function PrintDirect({ order, onDone }: { order: OrderOut; onDone: () => void }) {
  const qc = useQueryClient();
  const [printer, setPrinter] = useState("auto");
  const printers = useQuery({ queryKey: ["printers", order.shop_id], queryFn: () => apiGet<PrinterOut[]>(`/shops/${order.shop_id}/printers`) });
  const body = (dry: boolean): PrintDirectIn => ({ printer_id: printer === "auto" ? null : printer, dry_check: dry });
  const check = useQuery({ queryKey: ["print-check", order.id, printer], queryFn: () => apiPost<PrintCheckOut>(`/orders/${order.id}/print-direct`, body(true)) });
  const go = useMutation({
    mutationFn: () => apiPost<PrintCheckOut>(`/orders/${order.id}/print-direct`, body(false)),
    onSuccess: (r) => {
      if (!r.ok) { toast.error([...r.problems, ...r.lines.flatMap((l) => l.problems)].join(" · ")); return; }
      toast.success(`${r.jobs_created} document(s) envoyé(s) à l'imprimante`);
      qc.invalidateQueries({ queryKey: ["print-jobs", order.id] });
      onDone();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const c = check.isError ? undefined : check.data;
  const list = (printers.data ?? []).filter((p) => p.enabled);
  return (
    <div className="space-y-2 rounded-xl border border-azure/30 bg-sky-50/60 p-3" data-testid="print-direct-panel">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={printer} onValueChange={setPrinter}>
          <SelectTrigger size="sm" className="w-56" data-testid="print-direct-printer"><SelectValue>{(v) => (v === "auto" ? "Affectation automatique" : list.find((p) => p.id === v)?.display_name || list.find((p) => p.id === v)?.name)}</SelectValue></SelectTrigger>
          <SelectContent><SelectItem value="auto">Affectation automatique</SelectItem>{list.map((p) => <SelectItem key={p.id} value={p.id}>{p.display_name || p.name}</SelectItem>)}</SelectContent>
        </Select>
        <Button className="font-bold tracking-wide" disabled={!c?.ok || go.isPending} onClick={() => go.mutate()} data-testid="print-direct-button">
          {go.isPending ? <Loader2 className="size-4 animate-spin" /> : <Printer className="size-4" />} IMPRIMER DIRECTEMENT
        </Button>
      </div>
      {c && <ul className="space-y-0.5 text-xs" data-testid="print-direct-check">
        {c.problems.map((p) => <li key={p} className="text-rose-700">✕ {p}</li>)}
        {c.lines.map((l) => (
          <li key={l.line_index} className={l.problems.length ? "text-rose-700" : "text-emerald-700"}>
            {l.problems.length ? "✕" : "✓"} {l.filename} → {l.printer_name ?? "—"}{l.problems.length ? ` : ${l.problems.join(" · ")}` : ""}
            {l.warnings.map((w) => <span key={w} className="block pl-3 text-amber-700">⚠ {w}</span>)}
          </li>
        ))}
      </ul>}
      <p className="text-[11px] text-muted-foreground">L'impression directe et « Télécharger le document » sont indépendants. Le statut affiché est celui remonté par Windows et le pilote.</p>
    </div>
  );
}

export default function PrintQueue() {
  const { shop, can } = useDashboard();
  const qc = useQueryClient();
  const [scope, setScope] = useState<"active" | "today">("active");
  const q = useQuery({ queryKey: ["print-queue", shop.id, scope], queryFn: () => apiGet<PrintJobOut[]>(`/shops/${shop.id}/print-queue?scope=${scope}`), refetchInterval: 4000 });
  const printers = useQuery({ queryKey: ["printers", shop.id], queryFn: () => apiGet<PrinterOut[]>(`/shops/${shop.id}/printers`) });
  const reassign = useMutation({
    mutationFn: ({ id, printer_id }: { id: string; printer_id: string }) => apiPost<PrintJobOut>(`/print-jobs/${id}/reassign`, { printer_id }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["print-queue", shop.id] }); toast.success("Travail réaffecté"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const jobs = q.isError ? [] : q.data ?? [];
  const tone: Record<string, string> = { printed: "text-emerald-700", failed: "text-rose-700", retry_wait: "text-amber-700", cancelled: "text-slate-500" };
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1">
          <h1 className="text-3xl font-bold text-ink">File d'impression</h1>
          <p className="text-sm text-muted-foreground">Accepté par PrintDrop → reçu par l'agent → transmis au spouleur Windows → terminé selon le pilote. Aucune vérification physique de la sortie papier.</p>
        </div>
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1">
          {(["active", "today"] as const).map((s) => <button key={s} type="button" onClick={() => setScope(s)} data-testid={`queue-scope-${s}`}
            className={cn("h-8 rounded-lg px-3 text-sm", scope === s ? "bg-white shadow-sm" : "text-slate-500")}>{s === "active" ? "En cours" : "24 h"}</button>)}
        </div>
      </div>
      <div className="rounded-2xl border bg-card">
        {jobs.length === 0 ? <p className="p-8 text-center text-sm text-muted-foreground" data-testid="queue-empty">Aucun travail.</p> : (
          <Table data-testid="queue-table">
            <TableHeader><TableRow><TableHead>Commande</TableHead><TableHead>Document</TableHead><TableHead>Imprimante</TableHead><TableHead>Statut</TableHead><TableHead>Mis à jour</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {jobs.map((j) => (
                <TableRow key={j.id} data-testid={`queue-row-${j.id}`}>
                  <TableCell className="font-mono text-sm">{j.order_code}{j.kind === "reprint" && <span className="ml-1 text-xs text-amber-700">(réimpression)</span>}</TableCell>
                  <TableCell className="max-w-48 truncate text-sm">{j.filename}</TableCell>
                  <TableCell className="text-sm">{j.printer_name ?? "Auto"}</TableCell>
                  <TableCell className={cn("text-sm font-medium", tone[j.status])} data-testid={`queue-status-${j.id}`}>{tk("job", j.status)}{j.error && <span className="block text-xs font-normal">{j.error}</span>}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{formatDateTime(j.updated_at)}</TableCell>
                  <TableCell>
                    {can("orders:update") && ["queued", "retry_wait"].includes(j.status) && (
                      <Select value="" onValueChange={(v: string) => reassign.mutate({ id: j.id, printer_id: v })}>
                        <SelectTrigger size="sm" className="w-36" data-testid={`queue-reassign-${j.id}`}><SelectValue>{() => "Réaffecter…"}</SelectValue></SelectTrigger>
                        <SelectContent>{(printers.data ?? []).filter((p) => p.enabled).map((p) => <SelectItem key={p.id} value={p.id}>{p.display_name || p.name}</SelectItem>)}</SelectContent>
                      </Select>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}

export function Onboarding() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["onboarding"], queryFn: () => apiGet<{ key: string; label: string; done: boolean; auto: boolean; link: string }[]>("/onboarding") });
  const dl = useQuery({ queryKey: ["agent-download"], queryFn: () => apiGet<{ available: boolean; url: string; version: string }>("/agent-download") });
  const mark = useMutation({ mutationFn: ({ k, done }: { k: string; done: boolean }) => apiPost(`/onboarding/${k}/done?done=${done}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding"] }), onError: (e) => toast.error(errorMessage(e)) });
  const steps = q.isError ? [] : q.data ?? [];
  const done = steps.filter((s) => s.done).length;
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl font-bold text-ink">Démarrage de votre boutique</h1>
        <p className="text-sm text-muted-foreground">Progression enregistrée automatiquement — revenez quand vous voulez. {steps.length > 0 && `${done}/${steps.length} étapes terminées.`}</p>
      </div>
      <ol className="space-y-2" data-testid="onboarding-steps">
        {steps.map((s, i) => (
          <li key={s.key} className={cn("flex flex-wrap items-center gap-3 rounded-2xl border bg-card p-4", s.done && "border-emerald-200 bg-emerald-50/50")} data-testid={`onboarding-${s.key}`}>
            <span className={cn("grid size-8 place-items-center rounded-full text-sm font-bold", s.done ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-600")}>{s.done ? "✓" : i + 1}</span>
            <span className="flex-1 font-medium text-ink">{s.label}{s.auto && !s.done && <span className="block text-xs font-normal text-muted-foreground">Validée automatiquement dès que c'est fait</span>}</span>
            {s.key === "agent" && !s.done && (dl.data?.available
              ? <a href={dl.data.url} className="inline-flex items-center gap-1 text-sm font-semibold text-azure" data-testid="download-agent-link"><Download className="size-4" />Télécharger PrintDrop pour Windows</a>
              : <span className="text-xs text-amber-700" data-testid="download-agent-unavailable">Installateur pas encore publié</span>)}
            <Link to={s.link} className="text-sm text-azure hover:underline">Ouvrir</Link>
            {!s.auto && <Button size="xs" variant={s.done ? "ghost" : "outline"} onClick={() => mark.mutate({ k: s.key, done: !s.done })} data-testid={`onboarding-mark-${s.key}`}>{s.done ? "Annuler" : "Marquer comme fait"}</Button>}
          </li>
        ))}
      </ol>
    </div>
  );
}
