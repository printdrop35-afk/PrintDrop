import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDashboard } from "@/hooks/useDashboard";
import { apiGet, apiPatch, apiPost, errorMessage } from "@/lib/api";
import { formatDateTime, tk } from "@/i18n";
import type { StaffCreateIn, StaffOut, StaffUpdateIn } from "@/lib/types";

const EMPTY: StaffCreateIn = { name: "", email: "", password: "", role: "operator" };

export default function Team() {
  const { can, me } = useDashboard();
  const qc = useQueryClient();
  const manage = can("staff:manage");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<StaffCreateIn>(EMPTY);

  const staff = useQuery({ queryKey: ["staff"], queryFn: () => apiGet<StaffOut[]>("/staff") });
  const create = useMutation({
    mutationFn: () => apiPost<StaffOut>("/staff", form),
    onSuccess: (s) => { qc.invalidateQueries({ queryKey: ["staff"] }); toast.success(`${s.name} ajouté(e) à l'équipe`); setOpen(false); setForm(EMPTY); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: StaffUpdateIn }) => apiPatch<StaffOut>(`/staff/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["staff"] }); toast.success("Membre mis à jour"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const rows = staff.isError ? [] : staff.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">{me.org?.name}</p>
          <h1 className="mt-1 text-3xl font-bold text-ink">Équipe</h1>
          <p className="mt-2 text-sm text-muted-foreground">Gérants : commandes, tarifs, boutique. Opérateurs : commandes et encaissement uniquement.</p>
        </div>
        {manage && <Button onClick={() => setOpen(true)} data-testid="add-staff-button"><UserPlus className="size-4" /> Ajouter un membre</Button>}
      </div>

      <div className="rounded-2xl border bg-card">
        <Table data-testid="staff-table">
          <TableHeader><TableRow><TableHead>Nom</TableHead><TableHead>Rôle</TableHead><TableHead className="hidden sm:table-cell">Ajouté le</TableHead><TableHead>Statut</TableHead>{manage && <TableHead className="text-right">Actions</TableHead>}</TableRow></TableHeader>
          <TableBody>
            {rows.map((m) => (
              <TableRow key={m.membership_id} data-testid={`staff-row-${m.email}`}>
                <TableCell><p className="font-medium text-ink">{m.name}</p><p className="text-xs text-muted-foreground">{m.email}</p></TableCell>
                <TableCell>
                  {manage && m.role !== "owner" ? (
                    <Select value={m.role} onValueChange={(v: string) => update.mutate({ id: m.membership_id, body: { role: v as "manager" | "operator" } })}>
                      <SelectTrigger size="sm" className="w-36" data-testid={`staff-role-select-${m.email}`}><SelectValue>{(v) => tk("role", v as string)}</SelectValue></SelectTrigger>
                      <SelectContent><SelectItem value="manager">{tk("role", "manager")}</SelectItem><SelectItem value="operator">{tk("role", "operator")}</SelectItem></SelectContent>
                    </Select>
                  ) : <Badge variant="secondary">{tk("role", m.role)}</Badge>}
                </TableCell>
                <TableCell className="hidden text-sm text-muted-foreground sm:table-cell">{formatDateTime(m.created_at)}</TableCell>
                <TableCell><Badge variant={m.active ? "default" : "outline"} data-testid={`staff-status-${m.email}`}>{m.active ? "Actif" : "Désactivé"}</Badge></TableCell>
                {manage && (
                  <TableCell className="text-right">
                    {m.role !== "owner" && (
                      <Button size="sm" variant="ghost" onClick={() => update.mutate({ id: m.membership_id, body: { active: !m.active } })} data-testid={`staff-toggle-${m.email}`}>
                        {m.active ? "Désactiver" : "Réactiver"}
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="add-staff-dialog">
          <DialogHeader><DialogTitle>Nouveau membre</DialogTitle><DialogDescription>Communiquez-lui le mot de passe provisoire en main propre.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5"><Label htmlFor="st-name">Nom complet</Label><Input id="st-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="staff-name-input" /></div>
            <div className="space-y-1.5"><Label htmlFor="st-email">E-mail</Label><Input id="st-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="staff-email-input" /></div>
            <div className="space-y-1.5"><Label htmlFor="st-pw">Mot de passe provisoire (8 car. min.)</Label><Input id="st-pw" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="staff-password-input" /></div>
            <div className="space-y-1.5">
              <Label>Rôle</Label>
              <Select value={form.role} onValueChange={(v: string) => setForm({ ...form, role: v as "manager" | "operator" })}>
                <SelectTrigger className="w-full" data-testid="staff-role-input"><SelectValue>{(v) => tk("role", v as string)}</SelectValue></SelectTrigger>
                <SelectContent><SelectItem value="operator">{tk("role", "operator")}</SelectItem><SelectItem value="manager">{tk("role", "manager")}</SelectItem></SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter><Button disabled={create.isPending} onClick={() => create.mutate()} data-testid="staff-submit-button">Ajouter</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
