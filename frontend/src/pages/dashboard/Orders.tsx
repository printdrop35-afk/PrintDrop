import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Banknote, CreditCard, FileText, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PaymentBadge, StatusBadge } from "@/components/StatusBadge";
import { AlertsBanner, NotificationsPanel, PrintJobsPanel } from "@/components/OrderExtras";
import { OrderLineDetails } from "@/components/OrderPrintTools";
import { PickupReceipt } from "@/components/PickupReceipt";
import { PrintDirect } from "@/pages/dashboard/PrintQueue";
import { PaperStockDialog, PaperStrip } from "@/components/PaperStock";
import { useDashboard } from "@/hooks/useDashboard";
import { apiGet, apiPost, errorMessage } from "@/lib/api";
import { formatDateTime, formatEUR, tk } from "@/i18n";
import type { OrderOut, OrderPayIn, OrderStatus, ShopStatsOut } from "@/lib/types";

const FILTERS = [
  { value: "active", label: "En cours" },
  { value: "pending", label: "En attente" },
  { value: "printing", label: "En impression" },
  { value: "ready", label: "Prêtes" },
  { value: "picked_up", label: "Retirées" },
  { value: "cancelled", label: "Annulées" },
  { value: "all", label: "Toutes" },
];

const NEXT: Record<OrderStatus, { to: OrderStatus; label: string; variant?: "outline" | "destructive" }[]> = {
  pending: [{ to: "printing", label: "Marquer en cours (sans imprimer)" }, { to: "ready", label: "Marquer prête", variant: "outline" }, { to: "cancelled", label: "Annuler", variant: "destructive" }],
  printing: [{ to: "ready", label: "Marquer prête" }, { to: "pending", label: "Remettre en attente", variant: "outline" }, { to: "cancelled", label: "Annuler", variant: "destructive" }],
  ready: [{ to: "picked_up", label: "Marquer retirée" }, { to: "printing", label: "Repasser en impression", variant: "outline" }, { to: "cancelled", label: "Annuler", variant: "destructive" }],
  picked_up: [],
  cancelled: [],
};

function Kpi({ label, value, tone, testId }: { label: string; value: string | number; tone: string; testId: string }) {
  return (
    <div className="rounded-2xl border bg-card p-4" data-testid={testId}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={`mt-1 font-heading text-2xl font-bold ${tone}`}>{value}</p>
    </div>
  );
}

function OrderSheet({ order, onClose, verifiedCode, onVerified }: { order: OrderOut | null; onClose: () => void; verifiedCode: string | null; onVerified: (orderId: string, code: string) => void }) {
  const { can, shop } = useDashboard();
  const qc = useQueryClient();
  const refresh = (o: OrderOut) => {
    qc.invalidateQueries({ queryKey: ["orders", shop.id] });
    qc.invalidateQueries({ queryKey: ["stats", shop.id] });
    qc.invalidateQueries({ queryKey: ["paper", shop.id] });
    qc.invalidateQueries({ queryKey: ["alerts", shop.id] });
    qc.setQueryData(["order", o.id], o);
    qc.invalidateQueries({ queryKey: ["print-jobs", o.id] });
    qc.invalidateQueries({ queryKey: ["notifications", o.id] });
  };
  const [pickup, setPickup] = useState(false);
  const [pickupCode, setPickupCode] = useState("");
  const [printReceipt, setPrintReceipt] = useState(false); // opens the print window once, right after pickup
  const live = useQuery({ queryKey: ["order", order?.id], queryFn: () => apiGet<OrderOut>(`/orders/${order?.id}`), enabled: !!order, initialData: order ?? undefined, refetchInterval: 5000 });
  const o = live.data ?? order;

  const status = useMutation({
    mutationFn: ({ to, confirm_code = "" }: { to: OrderStatus; confirm_code?: string }) => apiPost<OrderOut>(`/orders/${o?.id}/status`, { status: to, confirm_code }),
    onSuccess: (res, vars) => {
      refresh(res);
      if (vars.confirm_code) onVerified(res.id, vars.confirm_code); // verified once for this transaction
      setPickup(false); setPickupCode("");
      if (res.status === "picked_up") setPrintReceipt(true);
      toast.success(`Commande ${res.code} : ${tk("status", res.status)}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const pay = useMutation({
    mutationFn: (body: OrderPayIn) => apiPost<OrderOut>(`/orders/${o?.id}/pay`, body),
    onSuccess: (res) => { refresh(res); toast.success(`Paiement de ${formatEUR(res.total_cents)} enregistré`); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Sheet open={!!order} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg" data-testid="order-detail-sheet">
        {o && (
          <>
            <SheetHeader>
              <SheetTitle className="font-mono text-2xl" data-testid="order-detail-code">{o.code}</SheetTitle>
              <SheetDescription data-testid="order-detail-contact">
                {o.customer_name || "Nom non renseigné"} · Tél. : {o.customer_phone || "Non renseigné"} · E-mail : {o.customer_email || "Non renseigné"} · {formatDateTime(o.created_at)}
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-5 px-4 pb-8">
              <div className="flex flex-wrap gap-2"><StatusBadge status={o.status} testId="order-detail-status" /><PaymentBadge status={o.payment_status} testId="order-detail-payment" /></div>
              {o.note && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900" data-testid="order-detail-note">« {o.note} »</p>}

              <ul className="divide-y rounded-xl border">
                {o.lines.map((l, i) => (
                  <li key={i} className="flex items-start gap-3 p-3" data-testid={`order-line-${i}`}>
                    <FileText className="mt-0.5 size-4 shrink-0 text-slate-400" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-ink">{l.filename ?? l.label}</p>
                      <p className="text-xs text-muted-foreground">
                        {l.filename ? `${l.label} · ` : ""}{l.pages} p.{l.copies > 1 ? ` × ${l.copies} ex.` : ""}
                        {l.options?.page_range ? ` · pages ${l.options.page_range}` : ""}{l.sheets ? ` · ${l.sheets} feuille(s)` : ""}
                      </p>
                    </div>
                    <span className="font-mono text-sm">{formatEUR(l.subtotal_cents)}</span>
                  </li>
                ))}
                {o.vat_cents !== null && o.total_ht_cents !== null && <li className="flex justify-between px-3 py-1.5 text-xs text-muted-foreground"><span>HT {formatEUR(o.total_ht_cents)}</span><span>TVA {formatEUR(o.vat_cents)}</span></li>}
                <li className="flex justify-between bg-slate-50 p-3 font-semibold"><span>Total TTC</span><span className="font-mono" data-testid="order-detail-total">{formatEUR(o.total_cents)}</span></li>
              </ul>

              <OrderLineDetails order={o} canDownload={can("documents:read")} />
              {o.purged_at && (
                <p className="rounded-lg border bg-slate-50 p-3 text-xs text-muted-foreground" data-testid="order-purged-notice">
                  Fichiers supprimés le {formatDateTime(o.purged_at)} (commande terminée). La commande, le paiement, les coordonnées et l'historique restent consultables.
                </p>
              )}
              {can("orders:update") && o.status === "pending" && !o.purged_at && <PrintDirect order={o} onDone={() => refresh({ ...o, status: "printing" })} />}
              <PrintJobsPanel order={o} canReprint={can("jobs:reprint")} />
              <NotificationsPanel order={o} />

              {can("orders:update") && NEXT[o.status].length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase" data-testid="step-status-title">Étape 1 — Statut de la commande</p>
                  <div className="flex flex-wrap gap-2">
                    {NEXT[o.status].map((n) => (
                      <Button key={n.to} variant={n.variant ?? "default"} disabled={status.isPending} onClick={() => (n.to !== "picked_up" ? status.mutate({ to: n.to }) : verifiedCode ? status.mutate({ to: "picked_up", confirm_code: verifiedCode }) : setPickup(true))} data-testid={`order-status-${n.to}-button`}>{n.label}</Button>
                    ))}
                  </div>
                </div>
              )}

              {o.payment_status === "unpaid" && o.status !== "cancelled" && can("orders:pay") && (
                <div className="space-y-2" data-testid="step-payment">
                  <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase" data-testid="step-payment-title">Étape 2 — Mode de paiement</p>
                  {o.status === "pending" && <p className="text-xs text-muted-foreground" data-testid="step-payment-hint">Choisissez d'abord le statut de la commande (étape 1).</p>}
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="outline" className="h-11" disabled={pay.isPending || o.status === "pending"} onClick={() => pay.mutate({ method: "cash" })} data-testid="mark-paid-cash-button"><Banknote className="size-4" /> Espèce</Button>
                    <Button variant="outline" className="h-11" disabled={pay.isPending || o.status === "pending"} onClick={() => pay.mutate({ method: "card_terminal" })} data-testid="mark-paid-card-button"><CreditCard className="size-4" /> Carte</Button>
                  </div>
                </div>
              )}
              {o.paid_at && <p className="text-sm text-emerald-700" data-testid="order-paid-info">Payé le {formatDateTime(o.paid_at)} · {tk("method", o.payment_method ?? "cash")}</p>}
              {verifiedCode && o.status === "ready" && <p className="text-xs text-emerald-700" data-testid="order-code-verified">Code client {verifiedCode} déjà vérifié pour cette transaction : le retrait ne le redemandera pas.</p>}

              {pickup && (
                <form className="space-y-2 rounded-xl border border-emerald-300 bg-emerald-50 p-3" data-testid="pickup-confirm"
                  onSubmit={(e) => { e.preventDefault(); status.mutate({ to: "picked_up", confirm_code: pickupCode }); }}>
                  <p className="text-sm font-semibold text-emerald-900">Vérifier le retrait : scannez le QR code du client ou saisissez son code</p>
                  <div className="flex gap-2">
                    <Input autoFocus value={pickupCode} onChange={(e) => setPickupCode(e.target.value)} placeholder="Code de retrait" inputMode="numeric"
                      className="h-10 bg-white font-mono" data-testid="pickup-confirm-input" />
                    <Button type="submit" disabled={!pickupCode.trim() || status.isPending} data-testid="pickup-confirm-submit">Confirmer</Button>
                    <Button type="button" variant="ghost" onClick={() => { setPickup(false); setPickupCode(""); }} data-testid="pickup-confirm-cancel">Annuler</Button>
                  </div>
                  <p className="text-xs text-emerald-800">Les fichiers de la commande seront supprimés automatiquement après le retrait.</p>
                </form>
              )}

              {o.status === "picked_up" && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Reçu de retrait</p>
                  <PickupReceipt order={o} shop={shop} autoPrint={printReceipt} onPrinted={() => setPrintReceipt(false)} />
                </div>
              )}

              <div>
                <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Historique</p>
                <ol className="mt-2 space-y-2 border-l-2 border-slate-200 pl-4" data-testid="order-history">
                  {o.history.map((h, i) => (
                    <li key={i} className="text-sm"><span className="font-medium text-ink">{tk("status", h.status)}</span> <span className="text-muted-foreground">· {formatDateTime(h.at)} · {h.by}</span></li>
                  ))}
                </ol>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default function Orders() {
  const { shop, can } = useDashboard();
  const [paperOpen, setPaperOpen] = useState(false);
  const [filter, setFilter] = useState("active");
  const [selected, setSelected] = useState<OrderOut | null>(null);
  // code scanned/typed at the counter: kept for the current transaction only, replaced by the next scan
  const [verified, setVerified] = useState<{ orderId: string; code: string } | null>(null);
  const [scan, setScan] = useState("");
  const lookup = useMutation({
    mutationFn: (code: string) => apiGet<OrderOut>(`/shops/${shop.id}/orders/by-code/${encodeURIComponent(code)}`),
    onSuccess: (o, code) => { setVerified({ orderId: o.id, code: code.trim() }); setSelected(o); setScan(""); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const stats = useQuery({ queryKey: ["stats", shop.id], queryFn: () => apiGet<ShopStatsOut>(`/shops/${shop.id}/stats`), refetchInterval: 15_000 });
  const orders = useQuery({
    queryKey: ["orders", shop.id, filter],
    queryFn: () => apiGet<OrderOut[]>(`/shops/${shop.id}/orders${filter === "all" ? "" : `?status=${filter}`}`),
    refetchInterval: 10_000,
  });
  const s = stats.isError ? undefined : stats.data;
  const list = orders.isError ? [] : orders.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">{shop.name}</p>
          <h1 className="mt-1 text-3xl font-bold text-ink">Commandes</h1>
        </div>
        <p className="text-xs text-muted-foreground">Actualisation automatique toutes les 10 s</p>
      </div>

      <form className="flex flex-wrap items-center gap-2 rounded-2xl border bg-card p-3" data-testid="order-scan-form"
        onSubmit={(e) => { e.preventDefault(); if (scan.trim()) lookup.mutate(scan.trim()); }}>
        <Input value={scan} onChange={(e) => setScan(e.target.value)} placeholder="Code client — scannez le QR code ou saisissez les 4 chiffres"
          inputMode="numeric" className="h-10 max-w-md flex-1 font-mono" data-testid="order-scan-input" aria-label="Code client" />
        <Button type="submit" disabled={!scan.trim() || lookup.isPending} data-testid="order-scan-submit">Ouvrir la commande</Button>
        <span className="text-xs text-muted-foreground">Le code n'est demandé qu'une fois par transaction.</span>
      </form>

      <AlertsBanner shopId={shop.id} onPaper={() => setPaperOpen(true)} onOpenOrder={async (id) => setSelected(await apiGet<OrderOut>(`/orders/${id}`))} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Commandes du jour" value={s?.orders_today ?? "—"} tone="text-ink" testId="kpi-orders-today" />
        <Kpi label="En attente" value={s?.pending ?? "—"} tone="text-amber-600" testId="kpi-pending" />
        <Kpi label="En impression" value={s?.printing ?? "—"} tone="text-blue-600" testId="kpi-printing" />
        <Kpi label="Prêtes" value={s?.ready ?? "—"} tone="text-emerald-600" testId="kpi-ready" />
        <Kpi label="Encaissé aujourd'hui" value={s ? formatEUR(s.revenue_today_cents) : "—"} tone="text-ink" testId="kpi-revenue-today" />
        <Kpi label="Reste à encaisser" value={s ? formatEUR(s.unpaid_cents) : "—"} tone="text-rose-600" testId="kpi-unpaid" />
      </div>

      <PaperStrip shopId={shop.id} canEdit={can("paper:manage")} onEdit={() => setPaperOpen(true)} />
      <PaperStockDialog shopId={shop.id} open={paperOpen} onOpenChange={setPaperOpen} />

      <Tabs value={filter} onValueChange={(v) => setFilter(String(v))}>
        <TabsList variant="line" className="flex-wrap" data-testid="orders-filter-tabs">
          {FILTERS.map((f) => <TabsTrigger key={f.value} value={f.value} data-testid={`orders-filter-${f.value}`}>{f.label}</TabsTrigger>)}
        </TabsList>
      </Tabs>

      <div className="rounded-2xl border bg-card">
        {list.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-center" data-testid="orders-empty">
            <Inbox className="size-10 text-slate-300" />
            <p className="mt-3 font-semibold text-ink">{orders.isLoading ? "Chargement…" : "Aucune commande ici"}</p>
            <p className="mt-1 text-sm text-muted-foreground">Les commandes envoyées via votre QR code apparaîtront automatiquement.</p>
          </div>
        ) : (
          <Table data-testid="orders-table">
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead><TableHead>Client</TableHead><TableHead className="hidden md:table-cell">Contenu</TableHead>
                <TableHead>Statut</TableHead><TableHead className="hidden sm:table-cell">Paiement</TableHead><TableHead className="text-right">Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((o) => (
                <TableRow key={o.id} onClick={() => setSelected(o)} className="cursor-pointer transition-colors hover:bg-accent/60" data-testid={`order-row-${o.code}`}>
                  <TableCell><span className="font-mono font-semibold text-ink">{o.code}</span><span className="block text-xs text-muted-foreground">{formatDateTime(o.created_at)}</span></TableCell>
                  <TableCell>{o.customer_name || "Non renseigné"}</TableCell>
                  <TableCell className="hidden max-w-[240px] truncate text-sm text-muted-foreground md:table-cell">{o.lines.map((l) => l.filename ?? l.label).join(", ")}</TableCell>
                  <TableCell><StatusBadge status={o.status} /></TableCell>
                  <TableCell className="hidden sm:table-cell"><PaymentBadge status={o.payment_status} /></TableCell>
                  <TableCell className="text-right font-mono font-semibold">{formatEUR(o.total_cents)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
      <OrderSheet order={selected} onClose={() => setSelected(null)}
        verifiedCode={selected && verified?.orderId === selected.id ? verified.code : null}
        onVerified={(orderId, code) => setVerified({ orderId, code })} />
    </div>
  );
}
