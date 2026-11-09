import { useEffect, useRef } from "react";
import { Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BRAND } from "@/lib/brand";
import { printElement } from "@/lib/printElement";
import { formatDateTime, formatEUR, tk } from "@/i18n";
import type { OrderOut, ShopOut } from "@/lib/types";

/** Small pickup receipt (fits 80 mm thermal paper or A4): logo, shop, order code, lines, total, payment method. */
export function PickupReceipt({ order, shop, autoPrint = false, onPrinted }: { order: OrderOut; shop: ShopOut; autoPrint?: boolean; onPrinted?: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const print = () => printElement(ref.current, { pageWidth: "72mm", title: `Reçu ${order.code}` });
  const pickedAt = [...order.history].reverse().find((h) => h.status === "picked_up")?.at ?? order.updated_at;

  useEffect(() => {
    if (!autoPrint) return;
    const t = window.setTimeout(() => { print(); onPrinted?.(); }, 300); // let the receipt render first
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPrint]);

  return (
    <div className="space-y-2" data-testid="pickup-receipt-block">
      <div ref={ref} className="pd-receipt mx-auto w-full max-w-[300px] rounded-xl border bg-white p-4 font-mono text-[12px] leading-snug text-slate-900" data-testid="pickup-receipt">
        <img src={BRAND.logo.light} alt="PrintDrop" width={150} height={50} className="mx-auto h-9 w-auto" draggable={false} data-testid="pickup-receipt-logo" />
        <p className="mt-2 text-center font-sans text-sm font-bold">{shop.name}</p>
        {(shop.address || shop.city) && <p className="text-center text-[11px] text-slate-600">{[shop.address, shop.city].filter(Boolean).join(", ")}</p>}
        <p className="mt-2 text-center font-sans text-[11px] font-semibold tracking-[0.15em] uppercase">Reçu de retrait</p>
        <div className="my-2 border-t border-dashed border-slate-400" />
        <p className="flex justify-between"><span>Commande</span><span className="font-bold" data-testid="pickup-receipt-code">{order.code}</span></p>
        <p className="flex justify-between"><span>Retirée le</span><span>{formatDateTime(pickedAt)}</span></p>
        <div className="my-2 border-t border-dashed border-slate-400" />
        <ul className="space-y-1">
          {order.lines.map((l, i) => (
            <li key={i} className="flex justify-between gap-2">
              <span className="min-w-0 break-words">{l.filename ?? l.label}{l.copies > 1 ? ` ×${l.copies}` : ""} · {l.pages} p.</span>
              <span className="shrink-0">{formatEUR(l.subtotal_cents)}</span>
            </li>
          ))}
          {order.discount_cents > 0 && <li className="flex justify-between"><span>Remise</span><span>-{formatEUR(order.discount_cents)}</span></li>}
        </ul>
        <div className="my-2 border-t border-dashed border-slate-400" />
        {order.total_ht_cents !== null && order.vat_cents !== null && (
          <>
            <p className="flex justify-between text-[11px]"><span>Total HT</span><span>{formatEUR(order.total_ht_cents)}</span></p>
            <p className="flex justify-between text-[11px]"><span>TVA</span><span>{formatEUR(order.vat_cents)}</span></p>
          </>
        )}
        <p className="flex justify-between font-sans text-sm font-bold"><span>Total TTC</span><span data-testid="pickup-receipt-total">{formatEUR(order.total_cents)}</span></p>
        <p className="mt-1 flex justify-between"><span>Paiement</span><span data-testid="pickup-receipt-method">{order.payment_method ? tk("method", order.payment_method) : "—"}</span></p>
        {order.paid_at && <p className="flex justify-between text-[11px]"><span>Payé le</span><span>{formatDateTime(order.paid_at)}</span></p>}
        <div className="my-2 border-t border-dashed border-slate-400" />
        <p className="text-center text-[11px]">Merci de votre visite · printdrop.fr</p>
      </div>
      <Button variant="outline" className="w-full" onClick={print} data-testid="pickup-receipt-print"><Printer className="size-4" /> Imprimer le reçu</Button>
    </div>
  );
}
