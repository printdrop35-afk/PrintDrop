import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiGet } from "@/lib/api";
import { formatDate, formatEUR, formatVat, tk } from "@/i18n";
import type { InvoiceOut } from "@/lib/types";

export default function InvoicePage() {
  const { id = "" } = useParams();
  const q = useQuery({ queryKey: ["invoice", id], queryFn: () => apiGet<InvoiceOut>(`/billing/invoices/${id}`) });
  const inv = q.isError ? undefined : q.data;
  return (
    <div className="space-y-4">
      <div className="no-print flex items-center gap-3">
        <Link to="/dashboard/abonnement" className="inline-flex items-center gap-1 text-sm text-azure hover:underline" data-testid="invoice-back-link"><ArrowLeft className="size-4" /> Abonnement</Link>
        {inv?.status === "paid" && <Button size="sm" variant="outline" className="ml-auto" onClick={() => window.print()} data-testid="invoice-print-button"><Printer className="size-4" /> Imprimer / PDF</Button>}
      </div>
      {q.isError && <p className="text-sm text-muted-foreground">Facture introuvable.</p>}
      {inv && (
        <article className="print-area mx-auto max-w-3xl rounded-2xl border bg-white p-8 text-sm text-slate-800" data-testid="invoice-document">
          <header className="flex flex-wrap justify-between gap-6">
            <div>
              <p className="font-heading text-2xl font-bold text-ink">{inv.status === "paid" ? "FACTURE" : "Récapitulatif (non payé)"}</p>
              {inv.number && <p className="font-mono" data-testid="invoice-number">N° {inv.number}</p>}
              {inv.paid_at && <p>Date : {formatDate(inv.paid_at)}</p>}
            </div>
            <div className="text-right">
              <p className="font-semibold">{inv.seller.company_name}</p>
              {inv.seller.company_address && <p className="whitespace-pre-line">{inv.seller.company_address}</p>}
              {inv.seller.company_siret && <p>SIRET : {inv.seller.company_siret}</p>}
              {inv.seller.company_vat_number && <p>TVA intracom. : {inv.seller.company_vat_number}</p>}
              {inv.seller.company_email && <p>{inv.seller.company_email}</p>}
            </div>
          </header>
          <p className="mt-6"><span className="text-muted-foreground">Client :</span> <span className="font-semibold">{inv.buyer_name}</span></p>
          <table className="mt-6 w-full">
            <thead><tr className="border-b text-left text-xs text-slate-500 uppercase"><th className="py-2">Désignation</th><th className="py-2 text-right">Montant HT</th></tr></thead>
            <tbody>
              <tr className="border-b">
                <td className="py-3">Abonnement PrintDrop {inv.plan_name} — {tk("period", inv.period).toLowerCase()}
                  {inv.period_start && inv.period_end && <span className="block text-xs text-muted-foreground">Période du {formatDate(inv.period_start)} au {formatDate(inv.period_end)}</span>}
                </td>
                <td className="py-3 text-right font-mono">{formatEUR(inv.amount_ht_cents)}</td>
              </tr>
            </tbody>
          </table>
          <dl className="mt-4 ml-auto w-64 space-y-1">
            <div className="flex justify-between"><dt>Total HT</dt><dd className="font-mono">{formatEUR(inv.amount_ht_cents)}</dd></div>
            <div className="flex justify-between"><dt>TVA {formatVat(inv.vat_rate_bp)}</dt><dd className="font-mono">{formatEUR(inv.vat_cents)}</dd></div>
            <div className="flex justify-between border-t pt-1 text-base font-bold"><dt>Total TTC</dt><dd className="font-mono" data-testid="invoice-total-ttc">{formatEUR(inv.amount_ttc_cents)}</dd></div>
          </dl>
          <p className="mt-8 text-xs text-muted-foreground">Statut : {tk("invoice", inv.status)} · Paiement par carte via Mollie{inv.paid_at ? ` le ${formatDate(inv.paid_at)}` : ""}.</p>
        </article>
      )}
    </div>
  );
}
