import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDashboard } from "@/hooks/useDashboard";
import { ME_KEY } from "@/hooks/useMe";
import { apiPut, errorMessage } from "@/lib/api";
import { tk } from "@/i18n";
import type { PaperSize, Pricing as PricingT, ShopOut } from "@/lib/types";

const SIZES: PaperSize[] = ["A4", "A3", "A5", "Letter", "Legal"];
const toEuros = (c: number) => (c / 100).toFixed(2).replace(".", ",");
const toCents = (s: string) => Math.round(parseFloat(s.replace(",", ".") || "0") * 100);

type Draft = Record<string, string>;

function draftFrom(p: PricingT): Draft {
  const d: Draft = { duplex: String(p.duplex_discount_pct), pc_bw: toEuros(p.photocopy.bw), pc_color: toEuros(p.photocopy.color), scan: toEuros(p.scan_cents) };
  SIZES.forEach((s) => { d[`${s}_bw`] = toEuros(p.print[s].bw); d[`${s}_color`] = toEuros(p.print[s].color); });
  return d;
}

function pricingFrom(d: Draft): PricingT {
  const print = {} as PricingT["print"];
  SIZES.forEach((s) => { print[s] = { bw: toCents(d[`${s}_bw`]), color: toCents(d[`${s}_color`]) }; });
  return {
    print, duplex_discount_pct: parseInt(d.duplex || "0", 10),
    photocopy: { bw: toCents(d.pc_bw), color: toCents(d.pc_color) }, scan_cents: toCents(d.scan),
  };
}

function MoneyInput({ value, onChange, disabled, testId }: { value: string; onChange: (v: string) => void; disabled: boolean; testId: string }) {
  return (
    <div className="relative">
      <Input inputMode="decimal" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value.replace(/[^\d,.]/g, ""))} className="h-10 pr-7 text-right font-mono" data-testid={testId} />
      <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-sm text-slate-400">€</span>
    </div>
  );
}

export default function Pricing() {
  const { shop, can } = useDashboard();
  const qc = useQueryClient();
  const editable = can("pricing:edit");
  const [draft, setDraft] = useState<Draft>(() => draftFrom(shop.pricing));
  const [shopId, setShopId] = useState(shop.id);
  if (shopId !== shop.id) { setShopId(shop.id); setDraft(draftFrom(shop.pricing)); }
  const set = (k: string) => (v: string) => setDraft({ ...draft, [k]: v });

  const save = useMutation({
    mutationFn: () => apiPut<ShopOut>(`/shops/${shop.id}/pricing`, pricingFrom(draft)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ME_KEY }); toast.success("Tarifs enregistrés — appliqués immédiatement aux nouvelles commandes"); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">{shop.name}</p>
        <h1 className="mt-1 text-3xl font-bold text-ink">Tarifs & services</h1>
        <p className="mt-2 text-sm text-muted-foreground">Prix TTC par page imprimée. Le serveur recalcule chaque devis — les prix affichés au client ne peuvent pas être modifiés depuis son navigateur.</p>
        {!editable && <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800" data-testid="pricing-readonly-notice">Lecture seule : seuls le propriétaire et le gérant peuvent modifier les tarifs.</p>}
      </div>

      <section className="rounded-2xl border bg-card p-5">
        <h2 className="text-lg font-semibold text-ink">Impression</h2>
        <div className="mt-4 grid grid-cols-[1fr_1fr_1fr] gap-x-4 gap-y-3 text-sm" data-testid="pricing-print-grid">
          <span className="text-xs font-semibold text-slate-500 uppercase">Format</span>
          <span className="text-xs font-semibold text-slate-500 uppercase">{tk("color", "bw")}</span>
          <span className="text-xs font-semibold text-slate-500 uppercase">{tk("color", "color")}</span>
          {SIZES.map((s) => (
            <div key={s} className="contents">
              <span className="self-center font-medium text-ink">{tk("paper", s)}</span>
              <MoneyInput value={draft[`${s}_bw`]} onChange={set(`${s}_bw`)} disabled={!editable} testId={`price-${s}-bw-input`} />
              <MoneyInput value={draft[`${s}_color`]} onChange={set(`${s}_color`)} disabled={!editable} testId={`price-${s}-color-input`} />
            </div>
          ))}
        </div>
        <div className="mt-5 flex items-center gap-3 border-t pt-4">
          <label htmlFor="duplex" className="text-sm font-medium text-ink">Remise recto-verso</label>
          <div className="relative w-24">
            <Input id="duplex" inputMode="numeric" value={draft.duplex} disabled={!editable} onChange={(e) => set("duplex")(e.target.value.replace(/\D/g, ""))} className="h-10 pr-7 text-right font-mono" data-testid="price-duplex-discount-input" />
            <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-sm text-slate-400">%</span>
          </div>
          <span className="text-xs text-muted-foreground">0 à 50 %</span>
        </div>
      </section>

      <section className="grid gap-4 rounded-2xl border bg-card p-5 sm:grid-cols-3">
        <h2 className="text-lg font-semibold text-ink sm:col-span-3">Services au comptoir</h2>
        <div className="space-y-1.5"><p className="text-sm font-medium">Photocopie N&B</p><MoneyInput value={draft.pc_bw} onChange={set("pc_bw")} disabled={!editable} testId="price-photocopy-bw-input" /></div>
        <div className="space-y-1.5"><p className="text-sm font-medium">Photocopie couleur</p><MoneyInput value={draft.pc_color} onChange={set("pc_color")} disabled={!editable} testId="price-photocopy-color-input" /></div>
        <div className="space-y-1.5"><p className="text-sm font-medium">Numérisation / page</p><MoneyInput value={draft.scan} onChange={set("scan")} disabled={!editable} testId="price-scan-input" /></div>
      </section>

      {editable && (
        <div className="flex gap-3">
          <Button className="h-11 px-6" disabled={save.isPending} onClick={() => save.mutate()} data-testid="pricing-save-button">{save.isPending ? "Enregistrement…" : "Enregistrer les tarifs"}</Button>
          <Button variant="outline" className="h-11" onClick={() => setDraft(draftFrom(shop.pricing))} data-testid="pricing-reset-button">Annuler les modifications</Button>
        </div>
      )}
    </div>
  );
}
