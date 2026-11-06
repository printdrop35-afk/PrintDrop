import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiGet } from "@/lib/api";
import { formatDateTime } from "@/i18n";
import { cn } from "@/lib/utils";
import type { AuditOut } from "@/lib/types";

const ACTIONS: Record<string, string> = {
  "org.register": "Création de l'entreprise",
  "auth.login": "Connexion",
  "order.create": "Nouvelle commande client",
  "order.status": "Changement de statut",
  "payment.counter": "Encaissement comptoir",
  "document.link": "Ouverture d'un document",
  "pricing.update": "Modification des tarifs",
  "shop.create": "Création de boutique",
  "shop.update": "Modification de boutique",
  "staff.create": "Ajout d'un membre",
  "staff.update": "Modification d'un membre",
  "authz.denied": "Accès refusé",
  "platform.org_update": "Action PrintDrop (plateforme)",
};

function summary(a: AuditOut): string {
  const d = a.details;
  if (typeof d.code === "string") return [d.code, d.from && d.to ? `${d.from} → ${d.to}` : "", typeof d.amount_cents === "number" ? `${(d.amount_cents / 100).toFixed(2)} €` : ""].filter(Boolean).join(" · ");
  if (typeof d.email === "string") return `${d.email}${d.role ? ` (${d.role})` : ""}`;
  if (typeof d.perm === "string") return `permission ${d.perm}`;
  return "";
}

export default function Audit() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => apiGet<AuditOut[]>("/audit") });
  const rows = q.isError ? [] : q.data ?? [];
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Sécurité</p>
        <h1 className="mt-1 text-3xl font-bold text-ink">Journal d'audit</h1>
        <p className="mt-2 text-sm text-muted-foreground">Les 200 dernières actions sensibles de votre entreprise (30 jours).</p>
      </div>
      <div className="rounded-2xl border bg-card">
        <Table data-testid="audit-table">
          <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Action</TableHead><TableHead>Par</TableHead><TableHead className="hidden md:table-cell">Détails</TableHead></TableRow></TableHeader>
          <TableBody>
            {rows.map((a) => (
              <TableRow key={a.id} data-testid="audit-row">
                <TableCell className="text-sm whitespace-nowrap text-muted-foreground">{formatDateTime(a.at)}</TableCell>
                <TableCell><span className={cn("text-sm font-medium", a.outcome === "deny" ? "text-rose-700" : "text-ink")}>{ACTIONS[a.action] ?? a.action}</span></TableCell>
                <TableCell className="text-sm">{a.actor_email}</TableCell>
                <TableCell className="hidden font-mono text-xs text-muted-foreground md:table-cell">{summary(a)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {rows.length === 0 && <p className="py-10 text-center text-sm text-muted-foreground">{q.isLoading ? "Chargement…" : "Aucune entrée"}</p>}
      </div>
    </div>
  );
}
