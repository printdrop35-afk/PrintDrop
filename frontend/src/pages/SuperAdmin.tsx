import { Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Building2, Euro, Loader2, LogOut, Receipt, Store, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Logo } from "@/components/Logo";
import { AdminBilling, SubscriptionCell } from "@/components/AdminBilling";
import { AgentReleaseAdmin } from "@/components/AgentReleaseAdmin";
import { ContactInbox, NewMessagesBadge } from "@/components/ContactInbox";
import { useMe } from "@/hooks/useMe";
import { apiGet, apiPatch, errorMessage } from "@/lib/api";
import { endSession } from "@/lib/session";
import { formatDateTime, formatEUR, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import type { AdminOrgOut, AdminOrgUpdateIn, AdminStatsOut, AuditOut } from "@/lib/types";

export default function SuperAdmin() {
  const meQ = useMe();
  const qc = useQueryClient();
  const isAdmin = !meQ.isError && meQ.data?.platform_role === "superadmin";
  const stats = useQuery({ queryKey: ["admin-stats"], queryFn: () => apiGet<AdminStatsOut>("/admin/stats"), enabled: isAdmin });
  const orgs = useQuery({ queryKey: ["admin-orgs"], queryFn: () => apiGet<AdminOrgOut[]>("/admin/organizations"), enabled: isAdmin });
  const audit = useQuery({ queryKey: ["admin-audit"], queryFn: () => apiGet<AuditOut[]>("/admin/audit"), enabled: isAdmin });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdminOrgUpdateIn }) => apiPatch<AdminOrgOut>(`/admin/organizations/${id}`, body),
    onSuccess: (o) => {
      qc.invalidateQueries({ queryKey: ["admin-orgs"] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
      qc.invalidateQueries({ queryKey: ["admin-audit"] });
      toast.success(`${o.name} : ${tk("org", o.status)}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (meQ.isLoading) return <div className="grid min-h-screen place-items-center"><Loader2 className="size-6 animate-spin text-azure" /></div>;
  if (!isAdmin) return <Navigate to="/login" replace />;

  const s = stats.isError ? undefined : stats.data;
  const kpis = [
    { label: "Entreprises", value: s ? `${s.active_organizations} / ${s.organizations}` : "—", hint: "actives / total", icon: Building2, id: "admin-kpi-orgs" },
    { label: "Boutiques", value: s?.shops ?? "—", icon: Store, id: "admin-kpi-shops" },
    { label: "Utilisateurs pro", value: s?.users ?? "—", icon: Users, id: "admin-kpi-users" },
    { label: "Commandes", value: s?.orders ?? "—", icon: Receipt, id: "admin-kpi-orders" },
    { label: "Volume encaissé", value: s ? formatEUR(s.revenue_cents) : "—", icon: Euro, id: "admin-kpi-revenue" },
  ];
  const rows = orgs.isError ? [] : orgs.data ?? [];

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-ink text-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
          <div className="flex items-center gap-3"><Logo inverse /><span className="rounded-full bg-amber-400/15 px-2.5 py-0.5 text-xs font-semibold text-amber-300">Super-admin</span></div>
          <div className="flex items-center gap-4">
          <NewMessagesBadge />
          <button type="button" onClick={() => endSession("/login")} className="inline-flex items-center gap-2 text-sm text-slate-300 transition-colors hover:text-white" data-testid="admin-logout-button"><LogOut className="size-4" /> Déconnexion</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl space-y-8 px-5 py-8 sm:px-8">
        <div>
          <h1 className="text-3xl font-bold text-ink">Administration de la plateforme</h1>
          <p className="mt-2 text-sm text-muted-foreground">Vue agrégée uniquement : le super-admin n'a pas accès aux documents ni aux données clients des boutiques.</p>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {kpis.map((k) => (
            <div key={k.id} className="rounded-2xl border bg-card p-4" data-testid={k.id}>
              <k.icon className="size-5 text-azure" />
              <p className="mt-3 font-heading text-2xl font-bold text-ink">{k.value}</p>
              <p className="text-xs text-muted-foreground">{k.label}{k.hint ? ` (${k.hint})` : ""}</p>
            </div>
          ))}
        </div>

        <section className="rounded-2xl border bg-card">
          <div className="border-b p-5"><h2 className="text-lg font-semibold text-ink">Entreprises clientes</h2>
            <p className="text-xs text-muted-foreground">Abonnement : offre et statut. « Offrir » prolonge sans paiement ni facture (tracé dans le journal).</p></div>
          <Table data-testid="admin-orgs-table">
            <TableHeader><TableRow><TableHead>Entreprise</TableHead><TableHead className="hidden md:table-cell">Boutiques</TableHead><TableHead className="hidden md:table-cell">Commandes</TableHead><TableHead className="hidden sm:table-cell">Encaissé</TableHead><TableHead>Abonnement</TableHead><TableHead>Compte</TableHead><TableHead className="text-right">Action</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.map((o) => (
                <TableRow key={o.id} data-testid={`admin-org-row-${o.owner_email}`}>
                  <TableCell><p className="font-medium text-ink">{o.name}</p><p className="text-xs text-muted-foreground">{o.owner_email} · {formatDateTime(o.created_at)}</p></TableCell>
                  <TableCell className="hidden md:table-cell">{o.shops_count}</TableCell>
                  <TableCell className="hidden md:table-cell">{o.orders_count}</TableCell>
                  <TableCell className="hidden font-mono sm:table-cell">{formatEUR(o.revenue_cents)}</TableCell>
                  <TableCell>
                    <SubscriptionCell org={o} />
                  </TableCell>
                  <TableCell>
                    <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-semibold", o.status === "active" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800")} data-testid={`admin-org-status-${o.owner_email}`}>{tk("org", o.status)}</span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant={o.status === "active" ? "destructive" : "outline"} disabled={update.isPending}
                      onClick={() => update.mutate({ id: o.id, body: { status: o.status === "active" ? "suspended" : "active" } })} data-testid={`admin-org-toggle-${o.owner_email}`}>
                      {o.status === "active" ? "Suspendre" : "Réactiver"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>

        <ContactInbox />
        <AdminBilling />
        <AgentReleaseAdmin />

        <section className="rounded-2xl border bg-card p-5">
          <h2 className="text-lg font-semibold text-ink">Journal plateforme</h2>
          <ul className="mt-3 divide-y text-sm" data-testid="admin-audit-list">
            {(audit.isError ? [] : audit.data ?? []).slice(0, 30).map((a) => (
              <li key={a.id} className="flex flex-wrap justify-between gap-2 py-2">
                <span><span className={cn("font-mono text-xs", a.outcome === "deny" ? "text-rose-700" : "text-azure")}>{a.action}</span> <span className="text-muted-foreground">· {a.actor_email}</span></span>
                <span className="text-xs text-muted-foreground">{formatDateTime(a.at)}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
