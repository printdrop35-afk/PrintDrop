import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Layers, Mail, MessageSquare, Printer, RotateCcw, TriangleAlert, WifiOff } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { apiGet, apiPost, errorMessage } from "@/lib/api";
import { formatDateTime, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import type { AlertOut, NotificationOut, OrderOut, PrintJobOut, ReprintIn } from "@/lib/types";

const JOB_TONE: Record<string, string> = {
  queued: "bg-amber-100 text-amber-800", claimed: "bg-blue-50 text-blue-700", printing: "bg-blue-100 text-blue-800",
  printed: "bg-emerald-100 text-emerald-800", failed: "bg-rose-100 text-rose-800", cancelled: "bg-slate-200 text-slate-600",
};
const NOTIF_TONE: Record<string, string> = {
  queued: "text-amber-700", sending: "text-blue-700", sent: "text-emerald-700", failed: "text-rose-700", skipped: "text-slate-500",
};

export function PrintJobsPanel({ order, canReprint }: { order: OrderOut; canReprint: boolean }) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<PrintJobOut | null>(null);
  const [reason, setReason] = useState("");
  const jobs = useQuery({
    queryKey: ["print-jobs", order.id],
    queryFn: () => apiGet<PrintJobOut[]>(`/orders/${order.id}/print-jobs`),
    refetchInterval: 4000,
  });
  const reprint = useMutation({
    mutationFn: (body: ReprintIn) => apiPost<PrintJobOut>(`/print-jobs/${target?.id}/reprint`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["print-jobs", order.id] });
      qc.invalidateQueries({ queryKey: ["order", order.id] });
      qc.invalidateQueries({ queryKey: ["orders", order.shop_id] });
      toast.success("Réimpression envoyée à l'agent");
      setTarget(null);
      setReason("");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const list = jobs.isError ? [] : jobs.data ?? [];
  const lastPerLine = new Map<number, string>();
  list.forEach((j) => lastPerLine.set(j.line_index, j.id));

  return (
    <div data-testid="print-jobs-panel">
      <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Impression automatique (agent local)</p>
      {list.length === 0 ? (
        <p className="mt-2 rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900" data-testid="print-jobs-empty">
          Aucun travail envoyé à l'agent. Les travaux sont créés quand vous cliquez « IMPRIMER DIRECTEMENT » et qu'un agent Windows est associé à la boutique.
          Sinon, ouvrez le document et imprimez-le depuis ce poste.
        </p>
      ) : (
        <ul className="mt-2 space-y-2">
          {list.map((j) => (
            <li key={j.id} className="rounded-xl border p-3 text-sm" data-testid={`print-job-${j.id}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2">
                  <Printer className="size-4 shrink-0 text-slate-400" />
                  <span className="truncate font-medium text-ink">{j.filename}</span>
                  {j.kind === "reprint" && <span className="rounded bg-violet-50 px-1.5 text-[10px] font-semibold text-violet-700 uppercase">Réimpression</span>}
                </span>
                <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold", JOB_TONE[j.status])} data-testid={`print-job-status-${j.id}`}>{tk("job", j.status)}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {j.printer_name ?? "Imprimante non attribuée"} · {formatDateTime(j.updated_at)} · par {j.requested_by}{j.reason ? ` · « ${j.reason} »` : ""}
              </p>
              {j.error && <p className="mt-1 text-xs text-rose-700" data-testid={`print-job-error-${j.id}`}>{j.error}</p>}
              {canReprint && lastPerLine.get(j.line_index) === j.id && ["printed", "failed", "cancelled"].includes(j.status) && !["picked_up", "cancelled"].includes(order.status) && (
                <Button size="sm" variant="outline" className="mt-2" onClick={() => setTarget(j)} data-testid={`print-job-reprint-${j.id}`}>
                  <RotateCcw className="size-3.5" /> Réimprimer
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <Dialog open={!!target} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent data-testid="reprint-dialog">
          <DialogHeader>
            <DialogTitle>Réimpression contrôlée</DialogTitle>
            <DialogDescription>Un nouveau travail sera envoyé à l'agent. Le motif est enregistré dans le journal d'audit.</DialogDescription>
          </DialogHeader>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ex : bourrage papier, pages blanches…" data-testid="reprint-reason-input" />
          <DialogFooter>
            <Button disabled={reason.trim().length < 3 || reprint.isPending} onClick={() => reprint.mutate({ reason })} data-testid="reprint-confirm-button">Confirmer la réimpression</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function NotificationsPanel({ order }: { order: OrderOut }) {
  const q = useQuery({
    queryKey: ["notifications", order.id],
    queryFn: () => apiGet<NotificationOut[]>(`/orders/${order.id}/notifications`),
    refetchInterval: 5000,
  });
  const list = q.isError ? [] : q.data ?? [];
  return (
    <div data-testid="notifications-panel">
      <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Notifications client</p>
      {!order.notify ? (
        <p className="mt-2 text-xs text-muted-foreground">Le client a refusé d'être prévenu.</p>
      ) : list.length === 0 ? (
        <p className="mt-2 text-xs text-muted-foreground" data-testid="notifications-empty">
          Envoi automatique par SMS{order.customer_email ? " et e-mail" : ""} dès que la commande passe à « Prête ».
        </p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {list.map((n) => (
            <li key={n.id} className="flex items-start gap-2 text-sm" data-testid={`notification-${n.channel}`}>
              {n.channel === "email" ? <Mail className="mt-0.5 size-4 text-slate-400" /> : <MessageSquare className="mt-0.5 size-4 text-slate-400" />}
              <span className="min-w-0 flex-1">
                <span className="font-medium text-ink">{tk("channel", n.channel)}</span> <span className="text-muted-foreground">· {n.recipient}</span>
                {n.last_error && n.status !== "sent" && <span className="block text-xs text-muted-foreground">{n.last_error}</span>}
              </span>
              <span className={cn("text-xs font-semibold", NOTIF_TONE[n.status])} data-testid={`notification-${n.channel}-status`}>{tk("notif", n.status)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AlertsBanner({ shopId, onOpenOrder, onPaper }: { shopId: string; onOpenOrder: (orderId: string) => void; onPaper: () => void }) {
  const q = useQuery({ queryKey: ["alerts", shopId], queryFn: () => apiGet<AlertOut[]>(`/shops/${shopId}/alerts`), refetchInterval: 10_000 });
  const alerts = q.isError ? [] : q.data ?? [];
  if (alerts.length === 0) return null;
  return (
    <div className="animate-rise rounded-2xl border border-rose-300 bg-rose-50 p-4 shadow-[0_8px_30px_-12px_rgba(225,29,72,0.45)]" role="alert" data-testid="printer-alerts-banner">
      <p className="flex items-center gap-2 font-heading font-semibold text-rose-800">
        <TriangleAlert className="size-5" /> {alerts.length} alerte{alerts.length > 1 ? "s" : ""} à traiter
      </p>
      <ul className="mt-2 space-y-1.5">
        {alerts.map((a, i) => (
          <li key={i} className="flex flex-wrap items-center gap-2 text-sm text-rose-900" data-testid={`printer-alert-${a.kind}`}>
            {a.kind === "job_failed" ? <Printer className="size-4 shrink-0" /> : a.kind === "low_paper" ? <Layers className="size-4 shrink-0" /> : <WifiOff className="size-4 shrink-0" />}
            <span className="min-w-0 flex-1">{a.message} <span className="text-xs text-rose-700">· depuis {formatDateTime(a.since)}</span></span>
            {a.kind === "low_paper" ? (
              <button type="button" onClick={onPaper} className="text-xs font-semibold text-rose-800 underline" data-testid="printer-alert-paper-refill">Mettre à jour le stock</button>
            ) : a.kind === "job_failed" && a.order_id ? (
              <button type="button" onClick={() => onOpenOrder(a.order_id as string)} className="text-xs font-semibold text-rose-800 underline" data-testid={`printer-alert-open-${a.order_code}`}>Ouvrir la commande</button>
            ) : (
              <Link to="/dashboard/imprimantes" className="text-xs font-semibold text-rose-800 underline" data-testid="printer-alert-devices-link">Voir les imprimantes</Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
