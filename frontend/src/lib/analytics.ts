import { SITE_CONFIG } from "@/config/site";

type PlausibleFn = (event: string, opts?: { props?: Record<string, string> }) => void;
type W = Window & { plausible?: PlausibleFn & { q?: unknown[] } };

export type SiteEvent = "Signup CTA" | "Demo Request" | "WhatsApp Click" | "Signup Completed";

/** Loads Plausible once — only when a domain is configured in config/site.ts. */
export function initAnalytics(): void {
  const domain = SITE_CONFIG.analytics.plausibleDomain.trim();
  if (!domain || typeof document === "undefined" || document.getElementById("plausible-script")) return;
  const w = window as W;
  w.plausible = w.plausible || Object.assign((...args: unknown[]) => { (w.plausible!.q = w.plausible!.q || []).push(args); }, {});
  const s = document.createElement("script");
  s.id = "plausible-script";
  s.defer = true;
  s.dataset.domain = domain;
  s.src = SITE_CONFIG.analytics.plausibleScriptSrc;
  document.head.appendChild(s);
}

/** No-op when analytics is disabled or blocked; never throws. */
export function track(event: SiteEvent, props?: Record<string, string>): void {
  try {
    if (!SITE_CONFIG.analytics.plausibleDomain.trim()) return;
    (window as W).plausible?.(event, props ? { props } : undefined);
  } catch {
    /* analytics must never break the page */
  }
}
