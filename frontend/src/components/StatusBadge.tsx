import { cn } from "@/lib/utils";
import { tk } from "@/i18n";
import type { OrderStatus, PaymentStatus } from "@/lib/types";

const STATUS_STYLE: Record<OrderStatus, string> = {
  pending: "bg-amber-100 text-amber-800 ring-amber-200",
  printing: "bg-blue-100 text-blue-800 ring-blue-200",
  ready: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  picked_up: "bg-slate-200 text-slate-700 ring-slate-300",
  cancelled: "bg-rose-100 text-rose-800 ring-rose-200",
};

export function StatusBadge({ status, testId }: { status: OrderStatus; testId?: string }) {
  return (
    <span
      data-testid={testId ?? "order-status-badge"}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset",
        STATUS_STYLE[status],
      )}
    >
      <span className={cn("size-1.5 rounded-full bg-current", status === "printing" && "animate-pulse-soft")} />
      {tk("status", status)}
    </span>
  );
}

export function PaymentBadge({ status, testId }: { status: PaymentStatus; testId?: string }) {
  const paid = status !== "unpaid";
  return (
    <span
      data-testid={testId ?? "payment-status-badge"}
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset",
        paid ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-white text-slate-600 ring-slate-300",
      )}
    >
      {tk("payment", status)}
    </span>
  );
}
