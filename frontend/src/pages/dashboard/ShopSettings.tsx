import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import { Copy, ExternalLink, Plus, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useDashboard } from "@/hooks/useDashboard";
import { BRAND } from "@/lib/brand";
import { ME_KEY } from "@/hooks/useMe";
import { apiPatch, apiPost, errorMessage } from "@/lib/api";
import type { ShopCreateIn, ShopOut, ShopUpdateIn } from "@/lib/types";
import { OrgProfileCard } from "@/components/OrgProfile";

function NewShopDialog() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<ShopCreateIn>({ name: "", city: "", address: "" });
  const create = useMutation({
    mutationFn: () => apiPost<ShopOut>("/shops", form),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ME_KEY });
      localStorage.setItem("pd_shop", s.id);
      toast.success(`Boutique « ${s.name} » créée`);
      setOpen(false);
      setForm({ name: "", city: "", address: "" });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} data-testid="new-shop-button"><Plus className="size-4" /> Nouvelle boutique</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="new-shop-dialog">
          <DialogHeader><DialogTitle>Ajouter une boutique</DialogTitle><DialogDescription>Chaque boutique a son propre QR code, ses tarifs et ses commandes.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            {(["name", "city", "address"] as const).map((k) => (
              <div key={k} className="space-y-1.5">
                <Label htmlFor={`ns-${k}`}>{{ name: "Nom", city: "Ville", address: "Adresse" }[k]}</Label>
                <Input id={`ns-${k}`} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} data-testid={`new-shop-${k}-input`} />
              </div>
            ))}
          </div>
          <DialogFooter><Button disabled={create.isPending} onClick={() => create.mutate()} data-testid="new-shop-submit-button">Créer</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function ShopSettings() {
  const { shop, can } = useDashboard();
  const qc = useQueryClient();
  const portalUrl = `${window.location.origin}/s/${shop.slug}`;
  const [form, setForm] = useState({ name: shop.name, city: shop.city, address: shop.address, accepting_orders: shop.accepting_orders });
  const [shopId, setShopId] = useState(shop.id);
  if (shopId !== shop.id) { setShopId(shop.id); setForm({ name: shop.name, city: shop.city, address: shop.address, accepting_orders: shop.accepting_orders }); }
  const editable = can("shop:edit");

  const save = useMutation({
    mutationFn: (body: ShopUpdateIn) => apiPatch<ShopOut>(`/shops/${shop.id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ME_KEY }); toast.success("Boutique mise à jour"); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Boutique</p>
          <h1 className="mt-1 text-3xl font-bold text-ink">Boutique & QR code</h1>
        </div>
        {can("shop:create") && <NewShopDialog />}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        <section className="space-y-4 rounded-2xl border bg-card p-5">
          <h2 className="text-lg font-semibold text-ink">Informations</h2>
          {(["name", "city", "address"] as const).map((k) => (
            <div key={k} className="space-y-1.5">
              <Label htmlFor={`shop-${k}`}>{{ name: "Nom affiché aux clients", city: "Ville", address: "Adresse" }[k]}</Label>
              <Input id={`shop-${k}`} value={form[k]} disabled={!editable} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className="h-10" data-testid={`shop-${k}-input`} />
            </div>
          ))}
          <label className="flex items-center gap-2.5 text-sm">
            <Checkbox checked={form.accepting_orders} disabled={!editable} onCheckedChange={(c: boolean) => setForm({ ...form, accepting_orders: c })} data-testid="shop-accepting-checkbox" />
            Accepter les commandes en ligne
          </label>
          {editable && <Button disabled={save.isPending} onClick={() => save.mutate(form)} data-testid="shop-save-button">Enregistrer</Button>}

          <div className="mt-2 rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-semibold text-slate-500 uppercase">Lien du portail client</p>
            <p className="mt-1 font-mono text-sm break-all text-ink" data-testid="portal-url">{portalUrl}</p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" variant="outline" onClick={() => { navigator.clipboard?.writeText(portalUrl); toast.success("Lien copié"); }} data-testid="copy-portal-url-button"><Copy className="size-3.5" /> Copier</Button>
              <a href={portalUrl} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-lg border bg-white px-3 text-sm font-medium transition-colors hover:bg-muted" data-testid="open-portal-link"><ExternalLink className="size-3.5" /> Ouvrir</a>
            </div>
          </div>
        </section>

        <section>
          <div className="print-area rounded-3xl border-2 border-ink bg-white p-8 text-center shadow-xl" data-testid="qr-poster">
            <img src={BRAND.logo.light} alt="PrintDrop" width={180} height={60} className="mx-auto mb-5 h-12 w-auto select-none" draggable={false} data-testid="qr-poster-logo" />
            <p className="text-xs font-semibold tracking-[0.2em] text-azure uppercase">Impression sans contact</p>
            <h2 className="mt-2 text-3xl font-bold text-ink">{form.name}</h2>
            <div className="mx-auto mt-6 w-fit rounded-2xl border bg-white p-4">
              <QRCodeSVG value={portalUrl} size={220} level="M" fgColor="#0B132B" data-testid="qr-code-svg" />
            </div>
            <ol className="mt-6 grid grid-cols-3 gap-2 text-sm">
              {["Scannez", "Déposez vos fichiers", "Récupérez au comptoir"].map((s, i) => (
                <li key={s}><span className="mx-auto grid size-7 place-items-center rounded-full bg-ink font-mono text-xs text-white">{i + 1}</span><span className="mt-1.5 block font-medium text-ink">{s}</span></li>
              ))}
            </ol>
            <p className="mt-6 text-xs text-slate-500">printdrop.fr</p>
          </div>
          <Button className="mt-4 w-full" onClick={() => window.print()} data-testid="print-qr-poster-button"><Printer className="size-4" /> Imprimer l'affiche</Button>
        </section>
      </div>
      <OrgProfileCard editable={can("billing:manage")} />
    </div>
  );
}
