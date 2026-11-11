import { Link, Navigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Eye, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Logo } from "@/components/Logo";
import { useMe } from "@/hooks/useMe";
import { apiGet, apiPost, errorMessage } from "@/lib/api";
import { formatDateTime, formatEUR, tk } from "@/i18n";
import type { AdminDocLinkOut, AdminOrgDetailOut } from "@/lib/types";

const SOURCE = { upload: "Envoyé par le client", ai: "Créé avec l'IA", scan: "Numérisation" } as const;
const METHOD: Record<string, string> = { cash: "Espèces", card_terminal: "Carte (TPE)", online: "En ligne" };

function Info({ label, value, id }: { label: string; value: React.ReactNode; id: string }) {
  return <div><p className="text-xs text-muted-foreground">{label}</p><p className="font-medium text-ink" data-testid={id}>{value || "—"}</p></div>;
}

export default function SuperAdminAgent() {
  const { orgId = "" } = useParams();
  const meQ = useMe();
  const isAdmin = !meQ.isError && meQ.data?.platform_role === "superadmin";
  const q = useQuery({ queryKey: ["admin-org-details", orgId], queryFn: () => apiGet<AdminOrgDetailOut>(`/admin/organizations/${orgId}/details`), enabled: isAdmin && !!orgId });
  const view = useMutation({
    mutationFn: (docId: string) => apiPost<AdminDocLinkOut>(`/admin/organizations/${orgId}/documents/${docId}/link`),
    onSuccess: (r) => window.open(r.url, "_blank", "noopener"),
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (meQ.isLoading) return <div className="grid min-h-screen place-items-center"><Loader2 className="size-6 animate-spin text-azure" /></div>;
  if (!isAdmin) return <Navigate to="/login" replace />;
  const d = q.isError ? undefined : q.data;
  const o = d?.org;

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-ink text-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
          <div className="flex items-center gap-3"><Logo inverse /><span className="rounded-full bg-amber-400/15 px-2.5 py-0.5 text-xs font-semibold text-amber-300">Super-admin</span></div>
          <Link to="/superadmin" className="inline-flex items-center gap-2 text-sm text-slate-300 hover:text-white" data-testid="agent-back-link"><ArrowLeft className="size-4" /> Retour</Link>
        </div>
      </header>
      <main className="mx-auto max-w-7xl space-y-6 px-5 py-8 sm:px-8">
        {q.isLoading && <Loader2 className="size-6 animate-spin text-azure" />}
        {q.isError && <p className="text-rose-700" role="alert" data-testid="agent-error">{errorMessage(q.error)}</p>}
        {d && o && (
          <>
            <div>
              <h1 className="text-3xl font-bold text-ink" data-testid="agent-name">{o.owner_name || o.owner_email}</h1>
              <p className="mt-1 text-sm text-muted-foreground" data-testid="agent-company">{o.name}</p>
            </div>

            <section className="grid gap-4 rounded-2xl border bg-card p-5 sm:grid-cols-2 lg:grid-cols-4" data-testid="agent-company-info">
              <Info label="Nom de l'Agent" value={o.owner_name} id="agent-info-name" />
              <Info label="Entreprise" value={o.name} id="agent-info-company" />
              <Info label="E-mail" value={o.owner_email} id="agent-info-email" />
              <Info label="Téléphone" value={o.owner_phone || "Non renseigné par l'Agent"} id="agent-info-phone" />
              <Info label="Adresse" value={d.shops.map((s) => [s.address, s.city].filter(Boolean).join(", ")).filter(Boolean).join(" · ")} id="agent-info-address" />
              <Info label="Immatriculation (SIREN / SIRET)" value={o.siret || "Non renseignée par l'Agent"} id="agent-info-siret" />
              <Info label="Créé le" value={formatDateTime(o.created_at)} id="agent-info-created" />
              <Info label="Statut · Formule" value={`${tk("org", o.status)} · ${o.printer_plan || "—"}`} id="agent-info-status" />
              <Info label="Boutiques" value={d.shops.map((s) => s.name).join(", ")} id="agent-info-shops" />
              <Info label="Équipe" value={d.staff.map((s) => `${s.name} (${s.role}${s.active ? "" : ", inactif"})`).join(", ")} id="agent-info-staff" />
            </section>

            <Tabs defaultValue="documents">
              <TabsList className="flex-wrap">
                <TabsTrigger value="documents" data-testid="agent-tab-documents">Documents ({d.documents.length})</TabsTrigger>
                <TabsTrigger value="payments" data-testid="agent-tab-payments">Paiements ({d.payments.length})</TabsTrigger>
                <TabsTrigger value="orders" data-testid="agent-tab-orders">Commandes ({d.orders.length})</TabsTrigger>
                <TabsTrigger value="customers" data-testid="agent-tab-customers">Clients ({d.customers.length})</TabsTrigger>
                <TabsTrigger value="activity" data-testid="agent-tab-activity">Activité</TabsTrigger>
              </TabsList>

              <TabsContent value="documents" className="rounded-2xl border bg-card">
                <Table data-testid="agent-documents-table">
                  <TableHeader><TableRow><TableHead>Document</TableHead><TableHead>Type</TableHead><TableHead>Client</TableHead><TableHead>Créé le</TableHead><TableHead>Commande</TableHead><TableHead>PRINTER</TableHead><TableHead>Statut</TableHead><TableHead /></TableRow></TableHeader>
                  <TableBody>
                    {d.documents.map((x) => (
                      <TableRow key={x.id} data-testid={`agent-doc-row-${x.id}`}>
                        <TableCell className="max-w-[220px] truncate font-medium">{x.filename}</TableCell>
                        <TableCell className="text-xs">{x.kind.toUpperCase()} · {SOURCE[x.source]}</TableCell>
                        <TableCell>{x.customer}</TableCell>
                        <TableCell className="text-xs">{formatDateTime(x.created_at)}</TableCell>
                        <TableCell className="font-mono">{x.order_code ?? "—"}</TableCell>
                        <TableCell className="text-xs font-semibold">{x.printer_plan}</TableCell>
                        <TableCell className="text-xs">{x.viewable ? (x.status === "attached" ? "Dans une commande" : "Envoyé") : "Supprimé (rétention)"}</TableCell>
                        <TableCell>{x.viewable && <Button size="sm" variant="outline" onClick={() => view.mutate(x.id)} disabled={view.isPending} data-testid={`agent-doc-view-${x.id}`}><Eye className="size-4" /> Voir</Button>}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TabsContent>

              <TabsContent value="payments" className="space-y-4">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-6" data-testid="agent-payment-summary">
                  {[["Total paiements", d.payment_summary.total], ["Réussis", d.payment_summary.succeeded], ["En attente", d.payment_summary.pending], ["Échoués", d.payment_summary.failed], ["Remboursements", d.payment_summary.refunds], ["Chiffre d'affaires", formatEUR(d.payment_summary.revenue_cents)]].map(([l, v]) => (
                    <div key={l} className="rounded-2xl border bg-card p-4"><p className="font-heading text-xl font-bold text-ink">{v}</p><p className="text-xs text-muted-foreground">{l}</p></div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">« En attente » = commandes en cours non encore payées. Les paiements sont encaissés au comptoir : aucun échec ni remboursement n'est enregistré dans PrintDrop.</p>
                <div className="rounded-2xl border bg-card">
                  <Table data-testid="agent-payments-table">
                    <TableHeader><TableRow><TableHead>Référence</TableHead><TableHead>Client</TableHead><TableHead>Date</TableHead><TableHead>Montant</TableHead><TableHead>Moyen</TableHead><TableHead>Statut</TableHead><TableHead>Commande</TableHead><TableHead>PRINTER</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {d.payments.map((x) => (
                        <TableRow key={x.id} data-testid={`agent-payment-row-${x.id}`}>
                          <TableCell className="font-mono text-xs">{x.reference}</TableCell><TableCell>{x.customer}</TableCell>
                          <TableCell className="text-xs">{formatDateTime(x.created_at)}</TableCell><TableCell className="font-mono">{formatEUR(x.amount_cents)}</TableCell>
                          <TableCell>{METHOD[x.method] ?? x.method}</TableCell><TableCell className="text-xs text-emerald-700">Réussi</TableCell>
                          <TableCell className="font-mono">{x.order_code ?? "—"}</TableCell><TableCell className="text-xs font-semibold">{x.printer_plan}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>

              <TabsContent value="orders" className="rounded-2xl border bg-card">
                <Table data-testid="agent-orders-table">
                  <TableHeader><TableRow><TableHead>N°</TableHead><TableHead>Client</TableHead><TableHead>Documents</TableHead><TableHead>PRINTER</TableHead><TableHead>Date</TableHead><TableHead>Montant</TableHead><TableHead>Paiement</TableHead><TableHead>Statut</TableHead><TableHead>Terminée le</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {d.orders.map((x) => (
                      <TableRow key={x.id} data-testid={`agent-order-row-${x.code}`}>
                        <TableCell className="font-mono">{x.code}</TableCell><TableCell>{x.customer}</TableCell>
                        <TableCell className="max-w-[200px] truncate text-xs">{x.documents.join(", ") || "—"}</TableCell>
                        <TableCell className="text-xs font-semibold">{x.printer_plan}</TableCell>
                        <TableCell className="text-xs">{formatDateTime(x.created_at)}</TableCell><TableCell className="font-mono">{formatEUR(x.total_cents)}</TableCell>
                        <TableCell className="text-xs">{tk("payment", x.payment_status)}</TableCell><TableCell className="text-xs">{tk("status", x.status)}</TableCell>
                        <TableCell className="text-xs">{x.completed_at ? formatDateTime(x.completed_at) : "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TabsContent>

              <TabsContent value="customers" className="rounded-2xl border bg-card">
                <p className="px-4 pt-3 text-xs text-muted-foreground">Les clients n'ont pas de compte : ils sont regroupés à partir de leurs commandes (téléphone, e-mail ou nom).</p>
                <Table data-testid="agent-customers-table">
                  <TableHeader><TableRow><TableHead>Client</TableHead><TableHead>E-mail</TableHead><TableHead>Première commande</TableHead><TableHead>Commandes</TableHead><TableHead>Historique d'achats</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {d.customers.map((c, i) => (
                      <TableRow key={i} data-testid={`agent-customer-row-${i}`}>
                        <TableCell>{c.name}<p className="text-xs text-muted-foreground">{c.phone}</p></TableCell><TableCell className="text-xs">{c.email || "—"}</TableCell>
                        <TableCell className="text-xs">{formatDateTime(c.first_order_at)}</TableCell><TableCell>{c.orders_count}</TableCell>
                        <TableCell className="text-xs">{formatEUR(c.total_cents)} · {c.order_codes.slice(-5).join(", ")}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TabsContent>

              <TabsContent value="activity" className="rounded-2xl border bg-card p-4">
                <ul className="divide-y text-sm" data-testid="agent-activity-list">
                  {d.activity.map((a) => (
                    <li key={a.id} className="flex flex-wrap justify-between gap-2 py-2">
                      <span><span className="font-mono text-xs text-azure">{a.action}</span> <span className="text-muted-foreground">· {a.actor_email}</span></span>
                      <span className="text-xs text-muted-foreground">{formatDateTime(a.at)}</span>
                    </li>
                  ))}
                </ul>
              </TabsContent>
            </Tabs>
          </>
        )}
      </main>
    </div>
  );
}
