import { fr, type MessageKey } from "./fr";

// Locale registry — French is the default. Add `en: en` here once an en.ts dictionary exists.
const dictionaries: Record<string, Record<MessageKey, string>> = { fr };
let locale = "fr";

export function setLocale(next: string): void {
  if (dictionaries[next]) locale = next;
}

export function t(key: MessageKey): string {
  return dictionaries[locale]?.[key] ?? fr[key] ?? key;
}

/** Look up a dynamic key such as `status.${order.status}`. */
export function tk(prefix: string, value: string): string {
  return t(`${prefix}.${value}` as MessageKey);
}

const money = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
export const formatEUR = (cents: number): string => money.format(cents / 100);
/** HT amount derived from a TTC price (VAT rate in basis points, 2000 = 20 %). */
export const htFromTtc = (ttc: number, vatBp: number): number => Math.round((ttc * 10000) / (10000 + vatBp));
export const formatVat = (bp: number): string => `${(bp / 100).toLocaleString("fr-FR")} %`;
const dateOnly = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" });
export const formatDate = (iso: string): string => dateOnly.format(new Date(iso));

const dateTime = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });
export const formatDateTime = (iso: string): string => dateTime.format(new Date(iso));
