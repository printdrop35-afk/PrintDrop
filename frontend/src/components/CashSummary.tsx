import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Banknote, CreditCard, Printer, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiGet, errorMessage } from "@/lib/api";
import { BRAND } from "@/lib/brand";
import { printElement } from "@/lib/printElement";
import { formatDateTime, formatEUR, tk } from "@/i18n";
import type { CashSummaryOut } from "@/lib/types";

const SERVICE: Record<string, string> = { print: "Impression", copy: "Photocopie", scan: "Scan" };

/** « Clôture de caisse » for one day: Espèce / Carte totals + every payment, printable on its own. */
export function CashSummary({ shopId, day, live }: { shopId: string; day: string; live: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const q = useQuery({
    queryKey: ["cash", shopId, day],
    queryFn: () => apiGet<CashSummaryOut>(`/shops/${shopId}/reports/cash?day=${day}`),
    refetchInterval: live ? 30_000 : false,
  });
  const c = q.data;
  const tile = (label: string, cents: number, count: number, Icon: typeof Wallet, testid: string, strong = false) => (
    <div className={strong ? "rounded-xl bg-ink p-4 text-white" : "rounded-xl border bg-white p-4"} data-testid={testid}>
      <p className={`flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase ${strong ? "text-sky-200" : "text-slate-500"}`}><Icon className="size-3.5" /> {label}</p>
      <p className="mt-1 font-heading text-2xl font-bold" data-testid={`${testid}-amount`}>{formatEUR(cents)}</p>
      <p className={`text-xs ${strong ? "text-sky-200" : "text-muted-foreground"}`}>{count} paiement{count > 1 ? "s" : ""}</p>
    </div>
  );
  return (
    <section className="rounded-2xl border bg-card p-5" data-testid="cash-summary">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-heading text-lg font-bold text-ink">Clôture de caisse</h2>
        <Button variant="outline" size="sm" disabled={!c} onClick={() => printElement(ref.current, { title: `Clôture ${day}` })} data-testid="cash-summary-print">
          <Printer className="size-4" /> Imprimer la clôture
        </Button>
      </div>
      {q.isError && <p className="text-sm text-rose-700" data-testid="cash-summary-error">{errorMessage(q.error)}</p>}
      {c && (
        <div ref={ref} className="space-y-4 bg-white">
          <div className="hidden items-center justify-between border-b pb-3 print:flex">
            <img src={BRAND.logo.light} alt="PrintDrop" className="h-8 w-auto" />
            <div className="text-right text-xs">
              <p className="font-semibold">{c.shop_name}</p>
              {c.shop_address && <p>{c.shop_address}</p>}
              <p>Clôture du {new Date(`${c.day}T12:00:00`).toLocaleDateString("fr-FR", { dateStyle: "full" })}</p>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {tile("Espèce", c.cash_cents, c.cash_count, Banknote, "cash-summary-cash")}
            {tile("Carte", c.card_cents, c.card_count, CreditCard, "cash-summary-card")}
            {tile("Total encaissé", c.total_cents, c.total_count, Wallet, "cash-summary-total", true)}
          </div>
          {c.other_count > 0 && <p className="text-xs text-muted-foreground" data-testid="cash-summary-other">Dont autres moyens (paiement en ligne) : {formatEUR(c.other_cents)} · {c.other_count} paiement(s)</p>}
          {c.payments.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="cash-summary-empty">Aucun paiement enregistré ce jour-là.</p>
          ) : (
            <table className="w-full text-sm" data-testid="cash-summary-table">
              <thead><tr className="border-b text-left text-xs text-slate-500"><th className="py-1.5">Heure</th><th>Commande</th><th>Service</th><th>Mode</th><th className="text-right">Montant</th></tr></thead>
              <tbody>
                {c.payments.map((x, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-1.5">{new Date(x.at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</td>
                    <td className="font-mono">{x.order_code}</td>
                    <td>{SERVICE[x.service] ?? x.service}</td>
                    <td>{tk("method", x.method)}</td>
                    <td className="text-right tabular-nums">{formatEUR(x.amount_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="text-[11px] text-slate-500">Montants TTC enregistrés dans PrintDrop · édité le {formatDateTime(c.generated_at)}. À rapprocher de votre caisse et de votre terminal de paiement.</p>
        </div>
      )}
    </section>
  );
}
