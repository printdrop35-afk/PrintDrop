import { useRef } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BRAND } from "@/lib/brand";
import { printElement } from "@/lib/printElement";
import { formatDateTime, formatEUR } from "@/i18n";
import type { OrderPublicOut } from "@/lib/types";

/**
 * Pickup ticket: official logo on top, order number / pickup code, QR (encodes the pickup code — a counter scanner
 * types it into the « Marquer retirée » confirmation). Prints alone on the page (.pd-print-area, see index.css).
 */
export function PickupTicket({ order }: { order: OrderPublicOut }) {
  const ref = useRef<HTMLElement>(null);
  return (
    <section ref={ref} className="pd-print-area rounded-2xl border bg-white p-5 shadow-sm" data-testid="pickup-ticket">
      <div className="flex items-center justify-between gap-3 border-b pb-4">
        <img src={BRAND.logo.light} alt="PrintDrop" width={180} height={60} className="h-10 w-auto" data-testid="pickup-ticket-logo" />
        <span className="text-right text-xs text-muted-foreground">Ticket de retrait</span>
      </div>
      <div className="mt-4 grid items-center gap-5 sm:grid-cols-[auto_1fr]">
        <div className="mx-auto rounded-xl border bg-white p-3">
          <QRCodeSVG value={order.code} size={148} level="M" marginSize={2} fgColor="#000000" bgColor="#FFFFFF" data-testid="pickup-ticket-qr" />
        </div>
        <div className="text-center sm:text-left">
          <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Code de retrait</p>
          <p className="font-mono text-5xl font-bold tracking-[0.2em] text-ink" data-testid="pickup-ticket-code">{order.code}</p>
          <p className="mt-2 text-sm text-ink" data-testid="pickup-ticket-shop">{order.shop_name}</p>
          <p className="text-xs text-muted-foreground">Commande du {formatDateTime(order.created_at)} · {formatEUR(order.total_cents)} TTC
            {order.payment_status === "unpaid" ? " · à régler au comptoir" : " · réglée"}</p>
          <p className="mt-2 text-xs text-muted-foreground">Présentez ce code ou ce QR code au comptoir pour retirer vos impressions.</p>
        </div>
      </div>
      <div className="mt-4 flex justify-end print:hidden">
        <Button variant="outline" size="sm" onClick={() => printElement(ref.current, { pageWidth: "12cm", title: `Ticket ${order.code}` })} data-testid="pickup-ticket-print"><Printer className="size-3.5" /> Imprimer le ticket</Button>
      </div>
    </section>
  );
}
