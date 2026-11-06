import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiGet, apiPatch, apiPut, errorMessage } from "@/lib/api";
import { formatEUR, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import type { AdminOrgOut, AdminSubscriptionIn, PlanIn, PlanOut, PlatformSettingsIn, PlatformSettingsOut, SubscriptionOut } from "@/lib/types";

const euros = (c: number | null) => (c === null ? "" : (c / 100).toFixed(2).replace(".", ","));
const cents = (s: string) => (s.trim() === "" ? null : Math.round(parseFloat(s.replace(",", ".")) * 100));

function PlanEditor({ plan }: { plan: PlanOut }) {
  const qc = useQueryClient();
  const [d, setD] = useState({ ...plan, monthly: euros(plan.prices_ht.monthly), yearly: euros(plan.prices_ht.yearly), feats: plan.features.join("\n") });
  const save = useMutation({
    mutationFn: () => {
      const body: PlanIn = { name: d.name, description: d.description, features: d.feats.split("\n"), max_shops: d.max_shops, max_staff: d.max_staff,
        active: d.active, sort: d.sort, prices_ht: { monthly: cents(d.monthly), yearly: cents(d.yearly) } };
      return apiPut<PlanOut>(`/admin/plans/${plan.code}`, body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-plans"] }); toast.success(`Offre ${d.name} enregistrée`); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="space-y-2 rounded-2xl border bg-card p-4" data-testid={`admin-plan-${plan.code}`}>
      <div className="flex items-center gap-2">
        <Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} className="h-9 font-semibold" data-testid={`admin-plan-name-${plan.code}`} />
        <label className="flex items-center gap-1.5 text-xs"><Checkbox checked={d.active} onCheckedChange={(v: boolean) => setD({ ...d, active: v })} data-testid={`admin-plan-active-${plan.code}`} />Active</label>
      </div>
      <Input value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} className="h-8 text-xs" />
      <div className="grid grid-cols-2 gap-2 text-xs">
        <label>Mensuel HT (€)<Input value={d.monthly} placeholder="non proposé" onChange={(e) => setD({ ...d, monthly: e.target.value })} className="h-9 font-mono" data-testid={`admin-plan-monthly-${plan.code}`} /></label>
        <label>Annuel HT (€)<Input value={d.yearly} placeholder="non proposé" onChange={(e) => setD({ ...d, yearly: e.target.value })} className="h-9 font-mono" data-testid={`admin-plan-yearly-${plan.code}`} /></label>
        <label>Boutiques max<Input inputMode="numeric" value={d.max_shops} onChange={(e) => setD({ ...d, max_shops: parseInt(e.target.value || "1", 10) })} className="h-9" /></label>
        <label>Comptes max<Input inputMode="numeric" value={d.max_staff} onChange={(e) => setD({ ...d, max_staff: parseInt(e.target.value || "1", 10) })} className="h-9" /></label>
      </div>
      <label className="block text-xs">Fonctionnalités (une par ligne)<Textarea value={d.feats} onChange={(e) => setD({ ...d, feats: e.target.value })} rows={4} className="text-xs" data-testid={`admin-plan-features-${plan.code}`} /></label>
      <p className="text-[11px] text-muted-foreground">TTC actuel : {plan.prices_ttc.monthly !== null ? `${formatEUR(plan.prices_ttc.monthly)}/mois` : "—"} · {plan.prices_ttc.yearly !== null ? `${formatEUR(plan.prices_ttc.yearly)}/an` : "—"}</p>
      <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending} data-testid={`admin-plan-save-${plan.code}`}><Save className="size-4" /> Enregistrer</Button>
    </div>
  );
}

function SettingsEditor({ s }: { s: PlatformSettingsOut }) {
  const qc = useQueryClient();
  const [d, setD] = useState({ ...s, shopVat: String(s.shop_vat_rate_bp / 100), subVat: String(s.subscription_vat_rate_bp / 100) });
  const save = useMutation({
    mutationFn: () => {
      const body: PlatformSettingsIn = {
        shop_vat_rate_bp: Math.round(parseFloat(d.shopVat.replace(",", ".")) * 100), subscription_vat_rate_bp: Math.round(parseFloat(d.subVat.replace(",", ".")) * 100),
        trial_days: d.trial_days, grace_days: d.grace_days, company_name: d.company_name, company_address: d.company_address,
        company_siret: d.company_siret, company_vat_number: d.company_vat_number, company_email: d.company_email,
      };
      return apiPut<PlatformSettingsOut>("/admin/settings", body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-settings"] }); qc.invalidateQueries({ queryKey: ["admin-plans"] }); toast.success("Paramètres enregistrés"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const field = (k: "company_name" | "company_siret" | "company_vat_number" | "company_email", label: string) => (
    <label className="text-xs">{label}<Input value={d[k]} onChange={(e) => setD({ ...d, [k]: e.target.value })} className="h-9" data-testid={`admin-settings-${k}`} /></label>
  );
  return (
    <div className="space-y-4 rounded-2xl border bg-card p-5" data-testid="admin-settings">
      <div className={cn("rounded-xl p-3 text-sm", s.payment_configured ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-900")} data-testid="admin-payment-status">
        Prestataire : {s.payment_provider} — {s.payment_configured ? `configuré (mode ${s.payment_mode === "live" ? "réel" : "test"})` : "non configuré : aucun paiement possible"}
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        <label className="text-xs">TVA prix boutiques (%)<Input value={d.shopVat} onChange={(e) => setD({ ...d, shopVat: e.target.value })} className="h-9 font-mono" data-testid="admin-settings-shop-vat" /></label>
        <label className="text-xs">TVA abonnements (%)<Input value={d.subVat} onChange={(e) => setD({ ...d, subVat: e.target.value })} className="h-9 font-mono" data-testid="admin-settings-sub-vat" /></label>
        <label className="text-xs">Essai gratuit (jours)<Input inputMode="numeric" value={d.trial_days} onChange={(e) => setD({ ...d, trial_days: parseInt(e.target.value || "0", 10) })} className="h-9" /></label>
        <label className="text-xs">Délai de grâce (jours)<Input inputMode="numeric" value={d.grace_days} onChange={(e) => setD({ ...d, grace_days: parseInt(e.target.value || "0", 10) })} className="h-9" /></label>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {field("company_name", "Raison sociale (factures)")}{field("company_email", "E-mail facturation")}
        {field("company_siret", "SIRET")}{field("company_vat_number", "N° TVA intracommunautaire")}
        <label className="text-xs sm:col-span-2">Adresse<Textarea value={d.company_address} onChange={(e) => setD({ ...d, company_address: e.target.value })} rows={2} /></label>
      </div>
      <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending} data-testid="admin-settings-save"><Save className="size-4" /> Enregistrer</Button>
    </div>
  );
}

export function AdminBilling() {
  const plans = useQuery({ queryKey: ["admin-plans"], queryFn: () => apiGet<PlanOut[]>("/admin/plans") });
  const settings = useQuery({ queryKey: ["admin-settings"], queryFn: () => apiGet<PlatformSettingsOut>("/admin/settings") });
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-ink">Offres d'abonnement (prix HT)</h2>
      <div className="grid gap-4 lg:grid-cols-3">
        {(plans.isError ? [] : plans.data ?? []).map((p) => <PlanEditor key={`${p.code}-${JSON.stringify(p.prices_ht)}`} plan={p} />)}
      </div>
      <h2 className="pt-2 text-lg font-semibold text-ink">TVA, essai & facturation</h2>
      {settings.data && !settings.isError && <SettingsEditor key={JSON.stringify(settings.data)} s={settings.data} />}
    </div>
  );
}

export function SubscriptionCell({ org }: { org: AdminOrgOut }) {
  const qc = useQueryClient();
  const sub = org.subscription;
  const upd = useMutation({
    mutationFn: (body: AdminSubscriptionIn) => apiPatch<SubscriptionOut>(`/admin/organizations/${org.id}/subscription`, body),
    onSuccess: (s) => { qc.invalidateQueries({ queryKey: ["admin-orgs"] }); toast.success(`${org.name} : ${s.plan_name} · ${tk("sub", s.status)}`); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const plus30 = () => new Date(Date.now() + 30 * 86400000).toISOString();
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select value={sub?.plan_code ?? "pro"} onValueChange={(v: string) => upd.mutate({ plan_code: v })}>
        <SelectTrigger size="sm" className="w-32" data-testid={`admin-sub-plan-${org.owner_email}`}><SelectValue>{(v) => tk("plan", v as string)}</SelectValue></SelectTrigger>
        <SelectContent>{(["starter", "pro", "business"] as const).map((p) => <SelectItem key={p} value={p}>{tk("plan", p)}</SelectItem>)}</SelectContent>
      </Select>
      <Select value="" onValueChange={(v: string) => upd.mutate(v === "active" ? { status: "active", period_end: plus30() } : { status: v as "trialing" | "canceled" })}>
        <SelectTrigger size="sm" className="w-40" data-testid={`admin-sub-status-${org.owner_email}`}>
          <SelectValue>{() => (sub ? `${tk("sub", sub.status)}${sub.granted_by_admin ? " (offert)" : ""}` : "—")}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="trialing">Relancer un essai</SelectItem>
          <SelectItem value="active">Offrir 30 jours (sans paiement)</SelectItem>
          <SelectItem value="canceled">Résilier</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
