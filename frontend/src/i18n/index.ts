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

const dateTime = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" });
export const formatDateTime = (iso: string): string => dateTime.format(new Date(iso));
