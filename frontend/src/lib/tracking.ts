import { apiGet } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";
import type { TrackingConfigOut } from "@/lib/types";

export const TRACKING_KEY = ["tracking"] as const;

/** Sends a Google Ads conversion once per id (localStorage guard). Silently skipped when the « AW-…/label »
 * target is not configured or the Google tag is blocked (ad blocker) — never breaks the page. */
export async function reportConversion(kind: "purchase" | "signup", id: string, params: Record<string, unknown> = {}): Promise<void> {
  try {
    const cfg = await queryClient.fetchQuery({ queryKey: TRACKING_KEY, queryFn: () => apiGet<TrackingConfigOut>("/public/tracking"), staleTime: Infinity });
    const sendTo = kind === "purchase" ? cfg.ads_purchase_send_to : cfg.ads_signup_send_to;
    const w = window as unknown as { gtag?: (...a: unknown[]) => void };
    const key = `ads-conv-${kind}-${id}`;
    if (!sendTo || !sendTo.includes("/") || typeof w.gtag !== "function" || localStorage.getItem(key)) return;
    w.gtag("event", "conversion", { send_to: sendTo, transaction_id: id, ...params });
    localStorage.setItem(key, "1");
  } catch {
    /* tracking must never block the user */
  }
}
