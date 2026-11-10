import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, Download, Eye, Plus, Save, Trash2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useDashboard } from "@/hooks/useDashboard";
import { useMe, ME_KEY } from "@/hooks/useMe";
import { apiPost, apiPut, errorMessage } from "@/lib/api";
import { formatEUR, htFromTtc, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import type { Discount, PaperSize, Pricing, PricingRule, ServiceItem, ShopOut } from "@/lib/types";

const SIZES: PaperSize[] = ["A4", "A3", "A5", "Letter", "Legal"];
const VAT_BP = 2000; // display hint only; the server applies the administrator's rate

function EuroInput({ cents, onChange, testId, className }: { cents: number; onChange: (c: number) => void; testId: string; className?: string }) {
  const [text, setText] = useState((cents / 100).toFixed(2).replace(".", ","));
  const [last, setLast] = useState(cents);
  if (cents !== last) {
    setLast(cents);
    setText((cents / 100).toFixed(2).replace(".", ","));
  }
  return (
    <div className={cn("relative", className)}>
      <Input inputMode="decimal" value={text} className="h-9 pr-6 text-right font-mono" data-testid={testId}
        onChange={(e) => {
          const v = e.target.value.replace(/[^\d,.]/g, "");
          setText(v);
          const n = Math.round(parseFloat(v.replace(",", ".")) * 100);
          if (!Number.isNaN(n)) { setLast(n); onChange(n); }
        }} />
      <span className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-xs text-muted-foreground">€</span>
    </div>
  );
}

const NumInput = ({ value, onChange, testId, className }: { value: number; onChange: (n: number) => void; testId: string; className?: string }) => (
  <Input inputMode="numeric" value={String(value)} className={cn("h-9 text-right font-mono", className)} data-testid={testId}
    onChange={(e) => onChange(parseInt(e.target.value.replace(/\D/g, "") || "0", 10))} />
);

const Ht = ({ cents }: { cents: number }) => <span className="text-[11px] text-muted-foreground">HT {formatEUR(htFromTtc(cents, VAT_BP))}</span>;

function PricingEditor({ shop, shops, canEdit }: { shop: ShopOut; shops: ShopOut[]; canEdit: boolean }) {
  const qc = useQueryClient();
  const [p, setP] = useState<Pricing>(structuredClone(shop.pricing));
  const [copyFrom, setCopyFrom] = useState("");
  const dirty = JSON.stringify(p) !== JSON.stringify(shop.pricing);
  const set = (patch: Partial<Pricing>) => setP({ ...p, ...patch });
  const done = () => qc.invalidateQueries({ queryKey: ME_KEY });

  const save = useMutation({
    mutationFn: () => apiPut<ShopOut>(`/shops/${shop.id}/pricing`, p),
    onSuccess: (s) => { setP(structuredClone(s.pricing)); done(); toast.success("Tarifs enregistrés — appliqués immédiatement aux nouveaux devis"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const copy = useMutation({
    mutationFn: () => apiPost<ShopOut>(`/shops/${shop.id}/pricing/copy-from/${copyFrom}`, {}),
    onSuccess: (s) => { setP(structuredClone(s.pricing)); done(); toast.success("Tarifs copiés"); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const svc = (i: number, patch: Partial<ServiceItem>) => set({ services: p.services.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  const rule = (i: number, patch: Partial<PricingRule>) => set({ rules: p.rules.map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  const disc = (i: number, patch: Partial<Discount>) => set({ discounts: p.discounts.map((d, j) => (j === i ? { ...d, ...patch } : d)) });
  const others = shops.filter((s) => s.id !== shop.id);

  return (
    <fieldset disabled={!canEdit} className="space-y-5">
      <Tabs defaultValue="print">
        <TabsList className="flex-wrap" data-testid="pricing-tabs">
          <TabsTrigger value="print" data-testid="pricing-tab-print">Impression & copies</TabsTrigger>
          <TabsTrigger value="services" data-testid="pricing-tab-services">Services</TabsTrigger>
          <TabsTrigger value="rules" data-testid="pricing-tab-rules">Règles & remises</TabsTrigger>
          <TabsTrigger value="preview" data-testid="pricing-tab-preview">Aperçu client & export</TabsTrigger>
        </TabsList>

        <TabsContent value="print" className="mt-4 space-y-4">
          <section className="rounded-2xl border bg-card p-5">
            <h2 className="font-heading text-lg font-semibold text-ink">Impression par page (TTC)</h2>
            <p className="text-xs text-muted-foreground">Prix par face imprimée. Décochez un format pour ne plus le proposer.</p>
            <div className="mt-4 space-y-2">
              <div className="grid grid-cols-[100px_1fr_1fr] gap-3 px-1 text-xs font-semibold text-slate-500 uppercase"><span>Format</span><span>Noir & blanc</span><span>Couleur</span></div>
              {SIZES.map((s) => {
                const c = p.print[s];
                const upd = (patch: Partial<typeof c>) => set({ print: { ...p.print, [s]: { ...c, ...patch } } });
                return (
                  <div key={s} className={cn("grid grid-cols-[100px_1fr_1fr] items-start gap-3 rounded-xl p-1", !c.active && "opacity-50")} data-testid={`pricing-row-${s}`}>
                    <label className="flex h-9 items-center gap-2 text-sm font-medium"><Checkbox checked={c.active} onCheckedChange={(v: boolean) => upd({ active: v })} data-testid={`pricing-active-${s}`} />{tk("paper", s)}</label>
                    <div><EuroInput cents={c.bw} onChange={(bw) => upd({ bw })} testId={`pricing-${s}-bw`} /><Ht cents={c.bw} /></div>
                    <div><EuroInput cents={c.color} onChange={(color) => upd({ color })} testId={`pricing-${s}-color`} /><Ht cents={c.color} /></div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 flex items-center gap-3 border-t pt-4 text-sm">
              <span className="flex-1">Remise recto-verso</span>
              <NumInput value={p.duplex_discount_pct} onChange={(n) => set({ duplex_discount_pct: Math.min(50, n) })} testId="pricing-duplex-pct" className="w-20" /> %
            </div>
          </section>
          <section className="grid gap-4 rounded-2xl border bg-card p-5 sm:grid-cols-4">
            <label className="flex items-center gap-2 text-sm font-medium sm:col-span-4"><Checkbox checked={p.photocopy.active} onCheckedChange={(v: boolean) => set({ photocopy: { ...p.photocopy, active: v } })} data-testid="pricing-photocopy-active" />Photocopie proposée</label>
            <div><p className="mb-1 text-xs text-muted-foreground">Photocopie N&B / page</p><EuroInput cents={p.photocopy.bw} onChange={(bw) => set({ photocopy: { ...p.photocopy, bw } })} testId="pricing-photocopy-bw" /><Ht cents={p.photocopy.bw} /></div>
            <div><p className="mb-1 text-xs text-muted-foreground">Photocopie couleur / page</p><EuroInput cents={p.photocopy.color} onChange={(color) => set({ photocopy: { ...p.photocopy, color } })} testId="pricing-photocopy-color" /><Ht cents={p.photocopy.color} /></div>
            <div><p className="mb-1 text-xs text-muted-foreground">Scan N&B / page</p><EuroInput cents={p.scan_cents} onChange={(scan_cents) => set({ scan_cents })} testId="pricing-scan" /><Ht cents={p.scan_cents} /></div>
            <div><p className="mb-1 text-xs text-muted-foreground">Scan couleur / page</p><EuroInput cents={p.scan_color_cents ?? p.scan_cents} onChange={(scan_color_cents) => set({ scan_color_cents })} testId="pricing-scan-color" /><Ht cents={p.scan_color_cents ?? p.scan_cents} /></div>
          </section>
        </TabsContent>

        <TabsContent value="services" className="mt-4 space-y-3">
          {p.services.map((s, i) => (
            <div key={s.id || i} className={cn("grid gap-3 rounded-2xl border bg-card p-4 md:grid-cols-[1.4fr_1fr_1fr_120px_auto]", !s.active && "opacity-60")} data-testid={`service-row-${i}`}>
              <div className="space-y-1.5">
                <Input value={s.name} onChange={(e) => svc(i, { name: e.target.value })} placeholder="Nom du service" className="h-9" data-testid={`service-name-${i}`} />
                <Input value={s.description} onChange={(e) => svc(i, { description: e.target.value })} placeholder="Description (facultatif)" className="h-8 text-xs" data-testid={`service-desc-${i}`} />
              </div>
              <Select value={s.category} onValueChange={(v: string) => svc(i, { category: v as ServiceItem["category"] })}>
                <SelectTrigger className="h-9 w-full" data-testid={`service-category-${i}`}><SelectValue>{(v) => tk("svc", v as string)}</SelectValue></SelectTrigger>
                <SelectContent>{(["typing", "binding", "lamination", "custom"] as const).map((c) => <SelectItem key={c} value={c}>{tk("svc", c)}</SelectItem>)}</SelectContent>
              </Select>
              <Select value={s.unit} onValueChange={(v: string) => svc(i, { unit: v as ServiceItem["unit"] })}>
                <SelectTrigger className="h-9 w-full" data-testid={`service-unit-${i}`}><SelectValue>{(v) => tk("unit", v as string)}</SelectValue></SelectTrigger>
                <SelectContent>{(["page", "unit", "document"] as const).map((u) => <SelectItem key={u} value={u}>{tk("unit", u)}</SelectItem>)}</SelectContent>
              </Select>
              <div><EuroInput cents={s.price_cents} onChange={(price_cents) => svc(i, { price_cents })} testId={`service-price-${i}`} /><Ht cents={s.price_cents} /></div>
              <div className="flex flex-wrap items-center gap-3 text-xs md:flex-col md:items-start">
                <label className="flex items-center gap-1.5"><Checkbox checked={s.price_from} onCheckedChange={(v: boolean) => svc(i, { price_from: v })} data-testid={`service-from-${i}`} />« À partir de »</label>
                <label className="flex items-center gap-1.5"><Checkbox checked={s.active} onCheckedChange={(v: boolean) => svc(i, { active: v })} data-testid={`service-active-${i}`} />Actif</label>
                <button type="button" className="inline-flex items-center gap-1 text-rose-600 hover:underline" onClick={() => set({ services: p.services.filter((_, j) => j !== i) })} data-testid={`service-delete-${i}`}><Trash2 className="size-3.5" />Supprimer</button>
              </div>
            </div>
          ))}
          <Button variant="outline" data-testid="service-add-button"
            onClick={() => set({ services: [...p.services, { id: "", name: "", category: "custom", unit: "unit", price_cents: 100, price_from: false, description: "", active: true }] })}>
            <Plus className="size-4" /> Ajouter un service
          </Button>
        </TabsContent>

        <TabsContent value="rules" className="mt-4 space-y-4">
          <section className="flex flex-wrap items-center gap-3 rounded-2xl border bg-card p-5">
            <div className="flex-1"><h2 className="font-heading font-semibold text-ink">Minimum de commande</h2><p className="text-xs text-muted-foreground">Si le total est inférieur, un complément est ajouté automatiquement. 0 € = aucun minimum.</p></div>
            <EuroInput cents={p.min_order_cents} onChange={(min_order_cents) => set({ min_order_cents })} testId="pricing-min-order" className="w-32" />
          </section>
          <section className="rounded-2xl border bg-card p-5">
            <h2 className="font-heading font-semibold text-ink">Règles de prix dégressifs</h2>
            <p className="text-xs text-muted-foreground">Remise sur l'impression dès un nombre de pages (pages × exemplaires). La règle la plus avantageuse s'applique.</p>
            <div className="mt-3 space-y-2">
              {p.rules.map((r, i) => (
                <div key={r.id || i} className="grid grid-cols-[1fr_110px_90px_auto_auto] items-center gap-2" data-testid={`rule-row-${i}`}>
                  <Input value={r.name} onChange={(e) => rule(i, { name: e.target.value })} placeholder="Nom" className="h-9" data-testid={`rule-name-${i}`} />
                  <div className="flex items-center gap-1 text-xs">dès <NumInput value={r.min_pages} onChange={(min_pages) => rule(i, { min_pages })} testId={`rule-min-${i}`} /></div>
                  <div className="flex items-center gap-1 text-xs">−<NumInput value={r.discount_pct} onChange={(discount_pct) => rule(i, { discount_pct: Math.min(90, discount_pct) })} testId={`rule-pct-${i}`} />%</div>
                  <Checkbox checked={r.active} onCheckedChange={(v: boolean) => rule(i, { active: v })} data-testid={`rule-active-${i}`} />
                  <button type="button" aria-label="Supprimer" onClick={() => set({ rules: p.rules.filter((_, j) => j !== i) })} data-testid={`rule-delete-${i}`}><Trash2 className="size-4 text-rose-600" /></button>
                </div>
              ))}
            </div>
            <Button size="sm" variant="outline" className="mt-3" data-testid="rule-add-button"
              onClick={() => set({ rules: [...p.rules, { id: "", name: "Gros volume", min_pages: 100, discount_pct: 10, active: true }] })}><Plus className="size-4" /> Ajouter une règle</Button>
          </section>
          <section className="rounded-2xl border bg-card p-5">
            <h2 className="font-heading font-semibold text-ink">Remises de la boutique</h2>
            <p className="text-xs text-muted-foreground">Sans code : appliquée automatiquement. Avec code : le client le saisit (jamais affiché publiquement). Une seule remise par commande — la plus avantageuse.</p>
            <div className="mt-3 space-y-2">
              {p.discounts.map((d, i) => (
                <div key={d.id || i} className="grid grid-cols-2 items-center gap-2 rounded-xl border p-2 md:grid-cols-[1.2fr_1fr_120px_110px_130px_auto_auto]" data-testid={`discount-row-${i}`}>
                  <Input value={d.name} onChange={(e) => disc(i, { name: e.target.value })} placeholder="Nom" className="h-9" data-testid={`discount-name-${i}`} />
                  <Input value={d.code ?? ""} onChange={(e) => disc(i, { code: e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, "") || null })} placeholder="Code (facultatif)" className="h-9 font-mono" data-testid={`discount-code-${i}`} />
                  <Select value={d.kind} onValueChange={(v: string) => disc(i, { kind: v as Discount["kind"], value: v === "percent" ? 10 : 100 })}>
                    <SelectTrigger className="h-9 w-full" data-testid={`discount-kind-${i}`}><SelectValue>{(v) => (v === "percent" ? "Pourcentage" : "Montant fixe")}</SelectValue></SelectTrigger>
                    <SelectContent><SelectItem value="percent">Pourcentage</SelectItem><SelectItem value="fixed">Montant fixe</SelectItem></SelectContent>
                  </Select>
                  {d.kind === "percent"
                    ? <div className="flex items-center gap-1 text-xs"><NumInput value={d.value} onChange={(value) => disc(i, { value: Math.min(90, value) })} testId={`discount-value-${i}`} />%</div>
                    : <EuroInput cents={d.value} onChange={(value) => disc(i, { value })} testId={`discount-value-${i}`} />}
                  <div className="text-xs"><span className="text-muted-foreground">dès</span><EuroInput cents={d.min_order_cents} onChange={(min_order_cents) => disc(i, { min_order_cents })} testId={`discount-min-${i}`} /></div>
                  <Checkbox checked={d.active} onCheckedChange={(v: boolean) => disc(i, { active: v })} data-testid={`discount-active-${i}`} />
                  <button type="button" aria-label="Supprimer" onClick={() => set({ discounts: p.discounts.filter((_, j) => j !== i) })} data-testid={`discount-delete-${i}`}><Trash2 className="size-4 text-rose-600" /></button>
                </div>
              ))}
            </div>
            <Button size="sm" variant="outline" className="mt-3" data-testid="discount-add-button"
              onClick={() => set({ discounts: [...p.discounts, { id: "", name: "Fidélité", code: null, kind: "percent", value: 10, min_order_cents: 0, active: true }] })}><Plus className="size-4" /> Ajouter une remise</Button>
          </section>
        </TabsContent>

        <TabsContent value="preview" className="mt-4 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
          <section className="rounded-2xl border bg-card p-5" data-testid="pricing-preview">
            <p className="flex items-center gap-2 text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase"><Eye className="size-4" /> Ce que voient vos clients</p>
            <h3 className="mt-2 font-heading text-xl font-bold text-ink">{shop.name}</h3>
            <ul className="mt-3 divide-y text-sm">
              {SIZES.filter((s) => p.print[s].active).map((s) => (
                <li key={s} className="flex justify-between py-2"><span>Impression {tk("paper", s)}</span><span className="font-mono">N&B {formatEUR(p.print[s].bw)} · Couleur {formatEUR(p.print[s].color)}</span></li>
              ))}
              {p.photocopy.active && <li className="flex justify-between py-2"><span>Photocopie</span><span className="font-mono">N&B {formatEUR(p.photocopy.bw)} · Couleur {formatEUR(p.photocopy.color)}</span></li>}
              <li className="flex justify-between py-2"><span>Scan N&B</span><span className="font-mono">{formatEUR(p.scan_cents)} / page</span></li>
              <li className="flex justify-between py-2"><span>Scan couleur</span><span className="font-mono">{formatEUR(p.scan_color_cents ?? p.scan_cents)} / page</span></li>
              {p.services.filter((s) => s.active).map((s, i) => (
                <li key={i} className="flex justify-between py-2"><span>{s.name}</span><span className="font-mono">{s.price_from ? "à partir de " : ""}{formatEUR(s.price_cents)} {tk("unit", s.unit)}</span></li>
              ))}
            </ul>
            {p.duplex_discount_pct > 0 && <p className="mt-2 text-xs text-emerald-700">Recto-verso : −{p.duplex_discount_pct} %</p>}
            {p.rules.filter((r) => r.active).map((r, i) => <p key={i} className="text-xs text-emerald-700">{r.name} : −{r.discount_pct} % dès {r.min_pages} pages</p>)}
            {p.min_order_cents > 0 && <p className="text-xs text-muted-foreground">Minimum de commande : {formatEUR(p.min_order_cents)}</p>}
            <p className="mt-3 text-[11px] text-muted-foreground">Prix TTC. Le détail HT / TVA est affiché au client avant validation.</p>
            <a href={`/s/${shop.slug}`} target="_blank" rel="noreferrer" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-4")} data-testid="pricing-open-portal">Ouvrir le portail client</a>
          </section>
          <div className="space-y-4">
            <section className="rounded-2xl border bg-card p-5">
              <h3 className="font-semibold text-ink">Exporter la grille tarifaire</h3>
              <p className="text-xs text-muted-foreground">Fichier CSV (Excel) avec prix TTC, HT et TVA — version enregistrée.</p>
              <a href={`/api/shops/${shop.id}/pricing/export`} className={cn(buttonVariants({ size: "sm" }), "mt-3")} data-testid="pricing-export-button"><Download className="size-4" /> Télécharger (CSV)</a>
            </section>
            {others.length > 0 && (
              <section className="rounded-2xl border bg-card p-5">
                <h3 className="font-semibold text-ink">Copier depuis une autre boutique</h3>
                <p className="text-xs text-muted-foreground">Chaque boutique a ses propres prix. Remplace les tarifs de « {shop.name} ».</p>
                <div className="mt-3 flex gap-2">
                  <Select value={copyFrom} onValueChange={setCopyFrom}>
                    <SelectTrigger className="h-9 flex-1" data-testid="pricing-copy-select"><SelectValue>{(v) => others.find((o) => o.id === v)?.name ?? "Choisir…"}</SelectValue></SelectTrigger>
                    <SelectContent>{others.map((o) => <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>)}</SelectContent>
                  </Select>
                  <Button size="sm" variant="outline" disabled={!copyFrom || copy.isPending} onClick={() => copy.mutate()} data-testid="pricing-copy-button"><Copy className="size-4" /> Copier</Button>
                </div>
              </section>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {canEdit && (
        <div className="sticky bottom-4 z-10 flex items-center justify-end gap-3 rounded-2xl border bg-white/90 p-3 shadow-lg backdrop-blur">
          <span className="mr-auto text-sm text-muted-foreground" data-testid="pricing-dirty-state">{dirty ? "Modifications non enregistrées" : "Tarifs à jour"}</span>
          <Button variant="ghost" disabled={!dirty} onClick={() => setP(structuredClone(shop.pricing))} data-testid="pricing-reset-button">Annuler</Button>
          <Button disabled={!dirty || save.isPending} onClick={() => save.mutate()} data-testid="pricing-save-button"><Save className="size-4" /> Enregistrer</Button>
        </div>
      )}
    </fieldset>
  );
}

export default function PricingPage() {
  const { shop, can } = useDashboard();
  const meQ = useMe();
  const shops = meQ.data?.shops ?? [shop];
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">{shop.name}</p>
        <h1 className="text-3xl font-bold text-ink">Tarifs & services</h1>
        <p className="mt-1 text-sm text-muted-foreground">Prix TTC saisis par vous, propres à cette boutique. Le calcul est toujours refait par le serveur ; l'équivalent HT est indicatif (TVA fixée par PrintDrop).</p>
      </div>
      <PricingEditor key={shop.id} shop={shop} shops={shops} canEdit={can("pricing:edit")} />
    </div>
  );
}
