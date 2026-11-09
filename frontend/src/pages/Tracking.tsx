import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check, CircleX, RefreshCw, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/Logo";
import { PickupTicket } from "@/components/PickupTicket";
import { PaymentBadge, StatusBadge } from "@/components/StatusBadge";
import { apiPost, errorMessage } from "@/lib/api";
import { formatDateTime, formatEUR, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import type { OrderPublicOut, OrderStatus, TrackIn } from "@/lib/types";

const STEPS: OrderStatus[] = ["pending", "printing", "ready", "picked_up"];

export default function Tracking() {
  const { code: codeParam = "" } = useParams();
  const navigate = useNavigate();
  const [code, setCode] = useState(codeParam);
  const [phone, setPhone] = useState(() => (codeParam ? sessionStorage.getItem(`pd_track_${codeParam}`) ?? "" : ""));
  const [query, setQuery] = useState<TrackIn | null>(() => (codeParam ? { code: codeParam, phone } : null));

  const q = useQuery({
    queryKey: ["track", query],
    queryFn: () => apiPost<OrderPublicOut>("/public/orders/track", query),
    enabled: !!query,
    retry: false,
    refetchInterval: 15_000,
  });
  const order = q.isError ? undefined : q.data;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const c = code.trim().toUpperCase();
    sessionStorage.setItem(`pd_track_${c}`, phone);
    setQuery({ code: c, phone });
    if (c !== codeParam) navigate(`/suivi/${c}`, { replace: true });
  };

  const current = order ? STEPS.indexOf(order.status) : -1;

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-ink px-5 py-5"><div className="mx-auto max-w-[560px]"><Logo inverse /></div></header>
      <main className="mx-auto max-w-[560px] space-y-5 px-4 py-8">
        <div>
          <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Suivi de commande</p>
          <h1 className="mt-1 text-3xl font-bold text-ink">Où en est mon impression ?</h1>
        </div>

        <form onSubmit={submit} className="grid gap-3 rounded-2xl border bg-white p-4 shadow-sm sm:grid-cols-[1fr_1fr_auto] sm:items-end print:hidden" data-testid="track-form">
          <div className="space-y-1.5">
            <Label htmlFor="tcode">Code de commande</Label>
            <Input id="tcode" value={code} onChange={(e) => setCode(e.target.value)} placeholder="1234" inputMode="numeric" required className="h-11 font-mono uppercase" data-testid="track-code-input" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tphone">Téléphone <span className="text-xs text-muted-foreground">(si vous l'avez donné)</span></Label>
            <Input id="tphone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} className="h-11" data-testid="track-phone-input" />
          </div>
          <Button type="submit" className="h-11" data-testid="track-submit-button">Suivre</Button>
        </form>

        {q.isError && <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" data-testid="track-error">{errorMessage(q.error)}</p>}

        {order && (
          <div className="animate-rise space-y-4" data-testid="track-result">
            <div className="rounded-2xl border bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-2xl font-bold text-ink" data-testid="track-order-code">{order.code}</p>
                  <p className="text-sm text-muted-foreground">
                    <Link to={`/s/${order.shop_slug}`} className="hover:underline">{order.shop_name}</Link> · {formatDateTime(order.created_at)}
                  </p>
                </div>
                <StatusBadge status={order.status} testId="track-status-badge" />
              </div>

              {order.status === "cancelled" ? (
                <div className="mt-6 flex items-center gap-3 rounded-xl bg-rose-50 p-4 text-rose-800"><CircleX className="size-5" /> Cette commande a été annulée par la boutique.</div>
              ) : (
                <ol className="mt-6 grid grid-cols-4 gap-2" data-testid="track-steps">
                  {STEPS.map((s, i) => (
                    <li key={s} className="flex flex-col items-center gap-2 text-center">
                      <span className={cn("grid size-9 place-items-center rounded-full border-2 text-sm font-bold transition-colors",
                        i < current ? "border-emerald-500 bg-emerald-500 text-white" : i === current ? "border-azure bg-azure text-white" : "border-slate-200 text-slate-400")}>
                        {i < current ? <Check className="size-4" /> : i + 1}
                      </span>
                      <span className={cn("text-xs", i <= current ? "font-semibold text-ink" : "text-slate-400")}>{tk("status", s)}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            {order.status !== "cancelled" && order.status !== "picked_up" && <PickupTicket order={order} />}

            <div className="flex gap-3 rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950 print:hidden" data-testid="track-retention">
              <Clock className="mt-0.5 size-5 shrink-0 text-azure" />
              <p data-testid="track-retention-text">
                {order.documents_deleted
                  ? "Vos documents ont été supprimés de nos serveurs à la fin de la commande."
                  : "Vos documents seront supprimés automatiquement de nos serveurs dès le retrait (ou l'annulation) de votre commande."}
              </p>
            </div>

            <div className={cn("flex items-center justify-between rounded-2xl p-5", order.payment_status === "unpaid" ? "bg-ink text-white" : "border bg-emerald-50 text-emerald-900")} data-testid="track-payment-banner">
              <div>
                <p className="text-sm opacity-80">{order.payment_status === "unpaid" ? "À régler au comptoir" : "Commande réglée"}</p>
                <p className="font-mono text-2xl font-bold" data-testid="track-total">{formatEUR(order.total_cents)} <span className="font-sans text-xs font-normal opacity-70">TTC</span></p>
                {order.vat_cents !== null && order.total_ht_cents !== null && <p className="text-xs opacity-70" data-testid="track-vat">HT {formatEUR(order.total_ht_cents)} · TVA {formatEUR(order.vat_cents)}</p>}
              </div>
              <PaymentBadge status={order.payment_status} testId="track-payment-badge" />
            </div>

            <div className="rounded-2xl border bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Détail</p>
              <ul className="mt-3 divide-y">
                {order.lines.map((l, i) => (
                  <li key={i} className="flex justify-between gap-3 py-2.5 text-sm" data-testid={`track-line-${i}`}>
                    <span><span className="font-medium text-ink">{l.filename ?? l.label}</span>{l.filename && <span className="block text-xs text-muted-foreground">{l.label} · {l.pages} p. × {l.copies}</span>}</span>
                    <span className="font-mono">{formatEUR(l.subtotal_cents)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <p className="flex items-center gap-2 text-xs text-muted-foreground"><RefreshCw className="size-3.5" /> Cette page se met à jour automatiquement.</p>
          </div>
        )}
      </main>
    </div>
  );
}
