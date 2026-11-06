import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { apiGet, apiPut, errorMessage } from "@/lib/api";
import { formatDateTime, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import type { PaperSize, PaperStockIn, PaperStockOut } from "@/lib/types";

const SIZES: PaperSize[] = ["A4", "A3", "A5", "Letter", "Legal"];
const BAR: Record<string, string> = { ok: "bg-emerald-500", low: "bg-amber-500", out: "bg-rose-600" };

export function usePaperStock(shopId: string) {
  return useQuery({ queryKey: ["paper", shopId], queryFn: () => apiGet<PaperStockOut>(`/shops/${shopId}/paper-stock`), refetchInterval: 10_000 });
}

export function PaperStrip({ shopId, onEdit, canEdit }: { shopId: string; onEdit: () => void; canEdit: boolean }) {
  const q = usePaperStock(shopId);
  const levels = q.isError ? [] : q.data?.levels ?? [];
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border bg-card px-4 py-3" data-testid="paper-strip">
      <span className="flex items-center gap-2 text-sm font-semibold text-ink"><Layers className="size-4 text-azure" /> Stock papier</span>
      {levels.length === 0 ? (
        <span className="text-sm text-muted-foreground" data-testid="paper-strip-empty">Non suivi — indiquez vos ramettes pour être alerté avant la rupture.</span>
      ) : levels.map((l) => (
        <div key={l.paper_size} className="min-w-[150px] flex-1 sm:max-w-[220px]" data-testid={`paper-level-${l.paper_size}`}>
          <div className="flex justify-between text-xs">
            <span className="font-medium text-ink">{tk("paper", l.paper_size)}</span>
            <span className={cn(l.level === "ok" ? "text-muted-foreground" : l.level === "low" ? "font-semibold text-amber-700" : "font-semibold text-rose-700")}>
              {l.remaining_sheets} / {l.stock_sheets} f.
            </span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div className={cn("h-full rounded-full transition-[width] duration-500", BAR[l.level])} style={{ width: `${100 - l.pct_used}%` }} />
          </div>
        </div>
      ))}
      {canEdit && <Button size="sm" variant="outline" className="ml-auto" onClick={onEdit} data-testid="paper-edit-button">Mettre à jour</Button>}
    </div>
  );
}

export function PaperStockDialog({ shopId, open, onOpenChange }: { shopId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const q = usePaperStock(shopId);
  const current = q.isError ? undefined : q.data;
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [pct, setPct] = useState("");
  const [removed, setRemoved] = useState<string[]>([]);
  const [wasOpen, setWasOpen] = useState(false);
  if (open && !wasOpen) {
    setWasOpen(true);
    setDraft({});
    setRemoved([]);
    setPct(String(current?.alert_pct ?? 80));
  } else if (!open && wasOpen) {
    setWasOpen(false);
  }

  const save = useMutation({
    mutationFn: (body: PaperStockIn) => apiPut<PaperStockOut>(`/shops/${shopId}/paper-stock`, body),
    onSuccess: (res) => {
      qc.setQueryData(["paper", shopId], res);
      qc.invalidateQueries({ queryKey: ["alerts", shopId] });
      toast.success("Stock papier enregistré — le compteur repart de maintenant");
      onOpenChange(false);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const submit = () => {
    const stock: PaperStockIn["stock"] = {};
    for (const s of SIZES) {
      if (removed.includes(s)) {
        stock[s] = null;
        continue;
      }
      const v = draft[s];
      if (v === undefined) continue;
      stock[s] = v.trim() === "" ? null : parseInt(v, 10);
    }
    save.mutate({ stock, alert_pct: parseInt(pct || "80", 10) });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="paper-dialog">
        <DialogHeader>
          <DialogTitle>Stock papier</DialogTitle>
          <DialogDescription>Saisissez les feuilles disponibles après un réapprovisionnement. Laissez vide pour ne rien changer.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {SIZES.map((s) => {
            const lv = current?.levels.find((l) => l.paper_size === s);
            return (
              <div key={s} className="grid grid-cols-[90px_1fr] items-center gap-3">
                <label htmlFor={`paper-${s}`} className="text-sm font-medium">{tk("paper", s)}</label>
                <div>
                  <Input id={`paper-${s}`} inputMode="numeric" placeholder={lv ? `${lv.remaining_sheets} restantes` : "Non suivi"}
                    value={draft[s] ?? ""} disabled={removed.includes(s)} onChange={(e) => setDraft({ ...draft, [s]: e.target.value.replace(/\D/g, "") })} data-testid={`paper-input-${s}`} />
                  {lv && (
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                      {removed.includes(s) ? <span className="font-semibold text-rose-700">Ne sera plus suivi</span>
                        : <span>Saisi : {lv.stock_sheets} f. le {formatDateTime(lv.set_at)} · {lv.used_sheets} utilisées</span>}
                      <button type="button" className="font-semibold text-azure hover:underline" data-testid={`paper-untrack-${s}`}
                        onClick={() => setRemoved(removed.includes(s) ? removed.filter((x) => x !== s) : [...removed, s])}>
                        {removed.includes(s) ? "Annuler" : "Ne plus suivre"}
                      </button>
                    </p>
                  )}
                </div>
              </div>
            );
          })}
          <div className="grid grid-cols-[90px_1fr] items-center gap-3 border-t pt-3">
            <label htmlFor="paper-pct" className="text-sm font-medium">Alerte à</label>
            <div className="flex items-center gap-2">
              <Input id="paper-pct" inputMode="numeric" className="w-20" value={pct} onChange={(e) => setPct(e.target.value.replace(/\D/g, ""))} data-testid="paper-alert-pct-input" />
              <span className="text-sm text-muted-foreground">% du stock utilisé</span>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button disabled={save.isPending} onClick={submit} data-testid="paper-save-button">Enregistrer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
