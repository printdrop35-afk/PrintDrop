import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiGet, apiPatch, errorMessage } from "@/lib/api";
import type { AiDocUsageOut, OrgProfileIn, OrgProfileOut } from "@/lib/types";

/** Company phone + SIREN/SIRET, shown on the Agent's page in the super-admin. Editable by the owner only. */
export function OrgProfileCard({ editable }: { editable: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["org-profile"], queryFn: () => apiGet<OrgProfileOut>("/org/profile") });
  const [form, setForm] = useState<OrgProfileIn | null>(null);
  const data = q.isError ? undefined : q.data;
  const f = form ?? data ?? { phone: "", siret: "" };
  const save = useMutation({
    mutationFn: () => apiPatch<OrgProfileOut>("/org/profile", f),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["org-profile"] }); setForm(null); toast.success("Coordonnées de l'entreprise enregistrées"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <section className="space-y-4 rounded-2xl border bg-card p-5" data-testid="org-profile-card">
      <div>
        <h2 className="text-lg font-semibold text-ink">Entreprise</h2>
        <p className="text-xs text-muted-foreground">Téléphone et immatriculation de votre entreprise (visibles par l'équipe PrintDrop).</p>
      </div>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="space-y-1.5"><Label htmlFor="org-phone">Téléphone</Label>
          <Input id="org-phone" type="tel" maxLength={30} disabled={!editable} value={f.phone} onChange={(e) => setForm({ ...f, phone: e.target.value })} placeholder="01 23 45 67 89" data-testid="org-profile-phone" /></div>
        <div className="space-y-1.5"><Label htmlFor="org-siret">SIREN ou SIRET</Label>
          <Input id="org-siret" inputMode="numeric" maxLength={20} disabled={!editable} value={f.siret} onChange={(e) => setForm({ ...f, siret: e.target.value })} placeholder="9 ou 14 chiffres" className="font-mono" data-testid="org-profile-siret" /></div>
        {editable
          ? <Button type="submit" disabled={save.isPending || !form} className="w-fit" data-testid="org-profile-save">{save.isPending ? "Enregistrement…" : "Enregistrer"}</Button>
          : <p className="text-xs text-muted-foreground sm:col-span-2">Seul le propriétaire du compte peut modifier ces informations.</p>}
      </form>
    </section>
  );
}

/** AI documents created by this Agent's customers this month, and how many were printed. */
export function AiDocUsageCard() {
  const q = useQuery({ queryKey: ["ai-doc-usage"], queryFn: () => apiGet<AiDocUsageOut>("/org/ai-docs/usage"), refetchInterval: 60_000 });
  const d = q.isError ? undefined : q.data;
  const month = d ? new Date(d.since).toLocaleDateString("fr-FR", { month: "long", year: "numeric", timeZone: "Europe/Paris" }) : "ce mois-ci";
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border bg-card px-4 py-3" data-testid="ai-usage-card">
      <span className="inline-flex items-center gap-2 text-sm font-semibold text-ink"><Sparkles className="size-4 text-azure" /> Documents IA · {month}</span>
      <span className="text-sm"><span className="font-heading text-lg font-bold text-ink" data-testid="ai-usage-created">{d?.created ?? "—"}</span> créés par vos clients</span>
      <span className="text-sm"><span className="font-heading text-lg font-bold text-ink" data-testid="ai-usage-in-orders">{d?.in_orders ?? "—"}</span> commandés</span>
      <span className="text-sm"><span className="font-heading text-lg font-bold text-emerald-600" data-testid="ai-usage-printed">{d?.printed ?? "—"}</span> imprimés</span>
    </div>
  );
}
