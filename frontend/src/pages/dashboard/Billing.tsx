import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, CreditCard, FileText, Loader2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiGet, apiPost, errorMessage } from "@/lib/api";
import { formatDate, formatDateTime, formatEUR, formatVat, tk } from "@/i18n";
import { ME_KEY } from "@/hooks/useMe";
import { cn } from "@/lib/utils";
import type { BillingOverviewOut, BillingPeriod, CheckoutIn, CheckoutOut, InvoiceOut } from "@/lib/types";

const SUB_TONE: Record<string, string> = {
  trialing: "bg-sky-100 text-sky-800", active: "bg-emerald-100 text-emerald-800", past_due: "bg-amber-100 text-amber-800",
  expired: "bg-rose-100 text-rose-800", canceled: "bg-slate-200 text-slate-700",
};
const INV_TONE: Record<string, string> = { paid: "text-emerald-700", pending: "text-amber-700", failed: "text-rose-700", canceled: "text-slate-500", expired: "text-slate-500" };

function ReturnStatus({ invoiceId }: { invoiceId: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["invoice", invoiceId], queryFn: () => apiGet<InvoiceOut>(`/billing/invoices/${invoiceId}`),
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 4000 : false),
  });
  const inv = q.isError ? undefined : q.data;
  if (inv && inv.status !== "pending") {
    qc.invalidateQueries({ queryKey: ["billing"] });
    qc.invalidateQueries({ queryKey: ME_KEY });
  }
  return (
    <div className={cn("rounded-2xl border p-4 text-sm", inv?.status === "paid" ? "border-emerald-300 bg-emerald-50 text-emerald-900" : inv && inv.status !== "pending" ? "border-rose-300 bg-rose-50 text-rose-900" : "border-sky-200 bg-sky-50 text-sky-900")} data-testid="billing-return-status">
      {!inv ? "Vérification du paiement…" : inv.status === "pending"
        ? <span className="flex items-center gap-2"><Loader2 className="size-4 animate-spin" /> Paiement en cours de confirmation par Mollie. Cette page se met à jour toute seule.</span>
        : inv.status === "paid" ? `Paiement confirmé par Mollie — facture ${inv.number} émise, abonnement prolongé.`
        : `Paiement ${tk("invoice", inv.status).toLowerCase()} — aucun montant n'a été débité. Vous pouvez réessayer.`}
    </div>
  );
}

export default function Billing() {
  const [params] = useSearchParams();
  const returned = params.get("facture");
  const [period, setPeriod] = useState<BillingPeriod>("monthly");
  const q = useQuery({ queryKey: ["billing"], queryFn: () => apiGet<BillingOverviewOut>("/billing") });
  const data = q.isError ? undefined : q.data;
  const checkout = useMutation({
    mutationFn: (body: CheckoutIn) => apiPost<CheckoutOut>("/billing/checkout", body),
    onSuccess: (r) => { window.location.assign(r.checkout_url); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const sub = data?.subscription;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-ink">Abonnement PrintDrop</h1>
        <p className="mt-1 text-sm text-muted-foreground">Renouvellement manuel : vous réglez chaque période vous-même. Prix des offres en HT, TVA ajoutée au paiement.</p>
      </div>
      {returned && <ReturnStatus invoiceId={returned} />}

      {sub && (
        <section className="flex flex-wrap items-center gap-4 rounded-2xl border bg-card p-5" data-testid="billing-current">
          <div className="flex-1">
            <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Offre actuelle</p>
            <p className="mt-1 font-heading text-2xl font-bold text-ink">{sub.plan_name} <span className={cn("ml-2 rounded-full px-2.5 py-0.5 align-middle text-xs font-semibold", SUB_TONE[sub.status])} data-testid="billing-status">{tk("sub", sub.status)}</span></p>
            <p className="mt-1 text-sm text-muted-foreground" data-testid="billing-period-info">
              {sub.status === "trialing" && sub.trial_ends_at ? `Essai gratuit jusqu'au ${formatDate(sub.trial_ends_at)} (${sub.days_left} j restants)` : null}
              {sub.status === "active" && sub.current_period_end ? `Payé jusqu'au ${formatDate(sub.current_period_end)}${sub.granted_by_admin ? " (attribué par PrintDrop)" : ""}` : null}
              {sub.status === "past_due" ? "Période terminée — réglez la suivante pour éviter l'interruption." : null}
              {sub.status === "expired" || sub.status === "canceled" ? "Vos boutiques n'acceptent plus de nouvelles commandes." : null}
            </p>
          </div>
          <p className="text-sm text-muted-foreground">Utilisation : {data.usage_shops} boutique(s) · {data.usage_staff} compte(s)</p>
        </section>
      )}

      {data && !data.payment_configured && (
        <div className="flex gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900" data-testid="billing-not-configured">
          <ShieldAlert className="size-5 shrink-0" />
          Paiement en ligne pas encore activé par PrintDrop (clé Mollie manquante). Aucun paiement ne peut être effectué pour l'instant — votre essai ou abonnement continue normalement.
        </div>
      )}
      {data?.payment_mode === "test" && <p className="text-xs text-amber-700" data-testid="billing-test-mode">Mode test Mollie : aucun argent réel n'est débité.</p>}

      <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 sm:w-fit" data-testid="billing-period-toggle">
        {(["monthly", "yearly"] as const).map((pp) => (
          <button key={pp} type="button" onClick={() => setPeriod(pp)} data-testid={`billing-period-${pp}`}
            className={cn("h-9 flex-1 rounded-lg px-5 text-sm font-medium transition-[background-color,color]", period === pp ? "bg-white text-ink shadow-sm" : "text-slate-500")}>{tk("period", pp)}</button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {(data?.plans ?? []).map((pl) => {
          const ht = pl.prices_ht[period];
          const ttc = pl.prices_ttc[period];
          const current = sub?.plan_code === pl.code && sub.status === "active";
          return (
            <article key={pl.code} className={cn("flex flex-col rounded-2xl border bg-card p-6", pl.code === "pro" && "border-azure shadow-[0_12px_40px_-16px_rgba(37,99,235,0.5)]")} data-testid={`plan-card-${pl.code}`}>
              <p className="font-heading text-xl font-bold text-ink">{pl.name}</p>
              <p className="text-sm text-muted-foreground">{pl.description}</p>
              {ht === null || ttc === null ? <p className="mt-4 text-sm text-muted-foreground">Non proposé en {tk("period", period).toLowerCase()}</p> : (
                <div className="mt-4">
                  <p className="font-mono text-3xl font-bold text-ink" data-testid={`plan-price-ht-${pl.code}`}>{formatEUR(ht)} <span className="font-sans text-sm font-medium text-muted-foreground">HT / {period === "monthly" ? "mois" : "an"}</span></p>
                  <p className="text-xs text-muted-foreground" data-testid={`plan-price-ttc-${pl.code}`}>soit {formatEUR(ttc)} TTC (TVA {formatVat(pl.vat_rate_bp)})</p>
                </div>
              )}
              <ul className="mt-4 flex-1 space-y-1.5 text-sm">
                {pl.features.map((f) => <li key={f} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-emerald-600" />{f}</li>)}
              </ul>
              <Button className="mt-5" variant={pl.code === "pro" ? "default" : "outline"} data-testid={`plan-pay-${pl.code}`}
                disabled={!data?.payment_configured || ht === null || checkout.isPending}
                onClick={() => checkout.mutate({ plan_code: pl.code, period })}>
                {checkout.isPending && checkout.variables?.plan_code === pl.code ? <Loader2 className="size-4 animate-spin" /> : <CreditCard className="size-4" />}
                {current ? "Renouveler" : "Payer cette offre"}
              </Button>
            </article>
          );
        })}
      </div>

      <section className="rounded-2xl border bg-card">
        <div className="border-b p-5"><h2 className="text-lg font-semibold text-ink">Historique des paiements & factures</h2></div>
        {(data?.invoices.length ?? 0) === 0 ? <p className="p-6 text-sm text-muted-foreground" data-testid="billing-no-invoices">Aucun paiement pour l'instant.</p> : (
          <Table data-testid="billing-invoices-table">
            <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Offre</TableHead><TableHead>Statut</TableHead><TableHead className="text-right">HT</TableHead><TableHead className="text-right">TTC</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {data?.invoices.map((i) => (
                <TableRow key={i.id} data-testid={`invoice-row-${i.id}`}>
                  <TableCell className="text-sm">{formatDateTime(i.created_at)}</TableCell>
                  <TableCell className="text-sm">{i.plan_name} · {tk("period", i.period)}</TableCell>
                  <TableCell className={cn("text-sm font-medium", INV_TONE[i.status])}>{tk("invoice", i.status)}</TableCell>
                  <TableCell className="text-right font-mono text-sm">{formatEUR(i.amount_ht_cents)}</TableCell>
                  <TableCell className="text-right font-mono text-sm">{formatEUR(i.amount_ttc_cents)}</TableCell>
                  <TableCell className="text-right">{i.status === "paid" && <Link to={`/dashboard/abonnement/facture/${i.id}`} className="inline-flex items-center gap-1 text-sm text-azure hover:underline" data-testid={`invoice-open-${i.id}`}><FileText className="size-4" />{i.number}</Link>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}
