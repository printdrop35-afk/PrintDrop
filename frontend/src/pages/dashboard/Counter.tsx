import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import { Banknote, Copy, CreditCard, FileUp, Loader2, Printer, RotateCw, ScanLine, Smartphone, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDashboard } from "@/hooks/useDashboard";
import { apiGet, apiPatch, apiPost, apiUpload, apiDelete, errorMessage } from "@/lib/api";
import { formatEUR, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import type { AgentOut, CopyIn, OrderOut, OrderStatus, QuoteOut, ScanSessionIn, ScanSessionOut } from "@/lib/types";

type Tab = "phone" | "copy" | "scan";

function Seg<T extends string | number>({ value, options, onChange, testid }: { value: T; options: [T, string][]; onChange: (v: T) => void; testid: string }) {
  return (
    <div className="inline-flex rounded-lg border bg-white p-0.5" role="radiogroup" data-testid={testid}>
      {options.map(([v, label]) => (
        <button key={String(v)} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
          className={cn("rounded-md px-3 py-1.5 text-sm font-medium transition-colors", value === v ? "bg-azure text-white" : "text-slate-600 hover:bg-slate-100")}
          data-testid={`${testid}-${v}`}>{label}</button>
      ))}
    </div>
  );
}

/** Steps after creation, for copy & scan orders: status → payment (Espèce / Carte) → completion. Idempotent on the server. */
function CounterOrder({ order: initial, onDone }: { order: OrderOut; onDone: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["order", initial.id], queryFn: () => apiGet<OrderOut>(`/orders/${initial.id}`), initialData: initial, refetchInterval: 5000 });
  const o = q.data;
  const [email, setEmail] = useState(o.customer_email ?? "");
  const refresh = (res: OrderOut) => { qc.setQueryData(["order", res.id], res); qc.invalidateQueries({ queryKey: ["orders"] }); };
  const status = useMutation({ mutationFn: (to: OrderStatus) => apiPost<OrderOut>(`/orders/${o.id}/status`, { status: to }), onSuccess: refresh, onError: (e) => toast.error(errorMessage(e)) });
  const pay = useMutation({ mutationFn: (method: "cash" | "card_terminal") => apiPost<OrderOut>(`/orders/${o.id}/pay`, { method }), onSuccess: refresh, onError: (e) => toast.error(errorMessage(e)) });
  const mail = useMutation({ mutationFn: () => apiPost(`/orders/${o.id}/scan-email`, { email }), onSuccess: () => toast.success("Lien envoyé par e-mail"), onError: (e) => toast.error(errorMessage(e)) });
  const link = o.delivery_token ? `${window.location.origin}/scan/${o.delivery_token}` : "";
  const paid = o.payment_status !== "unpaid";
  const finished = ["picked_up", "delivered", "cancelled"].includes(o.status);
  return (
    <section className="space-y-4 rounded-2xl border bg-card p-5" data-testid="counter-order">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-heading text-lg font-bold">Commande {o.code} · {o.service === "scan" ? "Scan" : "Photocopie"}</h3>
        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold" data-testid="counter-order-status">{tk("status", o.status)}</span>
      </div>
      <p className="text-sm text-muted-foreground">{o.lines.map((l) => `${l.label} · ${l.pages} p.`).join(" · ")} — <strong className="text-ink" data-testid="counter-order-total">{formatEUR(o.total_cents)}</strong></p>

      <div className="space-y-2">
        <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Étape 1 — Statut</p>
        {o.service === "copy" && o.status === "printing" && (
          <>
            <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950" data-testid="copy-instructions">
              Faites la copie avec le bouton <strong>Copie</strong> du copieur ({o.lines[0]?.label}, {o.lines[0]?.copies} exemplaire(s)).
              PrintDrop ne pilote pas la fonction copie : confirmez seulement quand les copies sont sorties.
            </p>
            <Button disabled={status.isPending} onClick={() => status.mutate("ready")} data-testid="copy-done-button"><Printer className="size-4" /> Copies sorties du copieur</Button>
          </>
        )}
        {(o.status === "ready" || finished) && <p className="text-sm text-emerald-700" data-testid="counter-step1-done">{o.service === "scan" ? "Document numérisé." : "Copies réalisées."}</p>}
      </div>

      <div className="space-y-2" data-testid="counter-step-payment">
        <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Étape 2 — Mode de paiement</p>
        {paid ? <p className="text-sm text-emerald-700" data-testid="counter-paid">Payé · {tk("method", o.payment_method ?? "cash")}</p> : (
          <div className="grid max-w-sm grid-cols-2 gap-2">
            <Button variant="outline" className="h-11" disabled={pay.isPending || o.status === "printing"} onClick={() => pay.mutate("cash")} data-testid="counter-pay-cash"><Banknote className="size-4" /> Espèce</Button>
            <Button variant="outline" className="h-11" disabled={pay.isPending || o.status === "printing"} onClick={() => pay.mutate("card_terminal")} data-testid="counter-pay-card"><CreditCard className="size-4" /> Carte</Button>
          </div>
        )}
      </div>

      {o.service === "scan" && paid && link && (
        <div className="grid gap-4 rounded-xl border bg-white p-4 sm:grid-cols-[auto_1fr]" data-testid="scan-delivery">
          <QRCodeSVG value={link} size={148} level="M" marginSize={2} data-testid="scan-delivery-qr" />
          <div className="space-y-2 text-sm">
            <p className="font-semibold">Le client scanne ce QR code avec son téléphone pour télécharger le fichier.</p>
            <p className="break-all font-mono text-xs text-muted-foreground" data-testid="scan-delivery-link">{link}</p>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); mail.mutate(); }}>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="E-mail du client (facultatif)" className="h-9" data-testid="scan-delivery-email" />
              <Button type="submit" size="sm" disabled={!email.includes("@") || mail.isPending} data-testid="scan-delivery-send">Envoyer</Button>
            </form>
            <p className="text-xs text-muted-foreground">Fichier supprimé 24 h après le premier téléchargement du client.</p>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {o.service === "copy" && paid && o.status === "ready" && (
          <Button onClick={() => status.mutate("picked_up")} disabled={status.isPending} data-testid="counter-complete">Terminer la commande</Button>
        )}
        {(finished || (o.service === "scan" && paid)) && <Button variant="outline" onClick={onDone} data-testid="counter-next">Client suivant</Button>}
      </div>
    </section>
  );
}

function CopyPanel({ onOrder }: { onOrder: (o: OrderOut) => void }) {
  const { shop } = useDashboard();
  const [f, setF] = useState<CopyIn>({ color: "bw", paper_size: "A4", duplex: false, originals: 1, copies: 1, customer_name: "" });
  const set = (p: Partial<CopyIn>) => setF((x) => ({ ...x, ...p }));
  const quote = useQuery({ queryKey: ["copy-quote", shop.id, f], queryFn: () => apiPost<QuoteOut>(`/shops/${shop.id}/counter/copy/quote`, f), retry: false });
  const start = useMutation({ mutationFn: () => apiPost<OrderOut>(`/shops/${shop.id}/counter/copy`, f), onSuccess: onOrder, onError: (e) => toast.error(errorMessage(e)) });
  const a3 = shop.pricing.print.A3?.active;
  return (
    <section className="space-y-4 rounded-2xl border bg-card p-5" data-testid="copy-panel">
      <div className="flex flex-wrap gap-4">
        <div className="space-y-1.5"><Label>Couleur</Label><Seg value={f.color} options={[["bw", "N&B"], ["color", "Couleur"]]} onChange={(v) => set({ color: v })} testid="copy-color" /></div>
        <div className="space-y-1.5"><Label>Format</Label><Seg value={f.paper_size} options={a3 ? [["A4", "A4"], ["A3", "A3"]] : [["A4", "A4"]]} onChange={(v) => set({ paper_size: v })} testid="copy-paper" /></div>
        <div className="space-y-1.5"><Label>Impression</Label><Seg value={f.duplex ? "rv" : "r"} options={[["r", "Recto"], ["rv", "Recto-verso"]]} onChange={(v) => set({ duplex: v === "rv" })} testid="copy-duplex" /></div>
      </div>
      <div className="flex flex-wrap gap-4">
        <div className="space-y-1.5"><Label htmlFor="orig">Pages de l'original</Label><Input id="orig" type="number" min={1} max={500} value={f.originals} onChange={(e) => set({ originals: Math.max(1, Number(e.target.value) || 1) })} className="h-10 w-28" data-testid="copy-originals" /></div>
        <div className="space-y-1.5"><Label htmlFor="copies">Nombre de copies</Label><Input id="copies" type="number" min={1} max={500} value={f.copies} onChange={(e) => set({ copies: Math.max(1, Number(e.target.value) || 1) })} className="h-10 w-28" data-testid="copy-copies" /></div>
        <div className="space-y-1.5"><Label htmlFor="cname">Client (facultatif)</Label><Input id="cname" value={f.customer_name} onChange={(e) => set({ customer_name: e.target.value })} className="h-10 w-56" data-testid="copy-customer" /></div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 p-4">
        <p className="text-sm" data-testid="copy-total">
          {quote.isError ? <span className="text-rose-700">{errorMessage(quote.error)}</span> : <>Total : <strong className="font-heading text-xl text-ink">{quote.data ? formatEUR(quote.data.total_cents) : "…"}</strong> TTC · {f.originals * f.copies} page(s)</>}
        </p>
        <Button className="h-11 px-6 font-bold" disabled={!quote.data || start.isPending} onClick={() => start.mutate()} data-testid="copy-start"><Copy className="size-4" /> Démarrer la copie</Button>
      </div>
    </section>
  );
}

function ScanPanel({ onOrder }: { onOrder: (o: OrderOut) => void }) {
  const { shop } = useDashboard();
  const qc = useQueryClient();
  const agents = useQuery({ queryKey: ["agents", shop.id], queryFn: () => apiGet<AgentOut[]>(`/shops/${shop.id}/agents`) });
  const online = (agents.data ?? []).filter((a) => a.status === "active" && a.online);
  const [opt, setOpt] = useState<Omit<ScanSessionIn, "agent_id">>({ format: "pdf", color: "color", dpi: 300, source: "flatbed" });
  const [sid, setSid] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const sess = useQuery({ queryKey: ["scan-session", sid], queryFn: () => apiGet<ScanSessionOut>(`/scan-sessions/${sid}`), enabled: !!sid,
    refetchInterval: (q) => (q.state.data?.status === "scanning" ? 2000 : false) });
  const s = sess.data;
  const put = (res: ScanSessionOut) => qc.setQueryData(["scan-session", res.id], res);
  const create = useMutation({ mutationFn: () => apiPost<ScanSessionOut>(`/shops/${shop.id}/scan-sessions`, { ...opt, agent_id: online[0]?.id ?? null }),
    onSuccess: (res) => { put(res); setSid(res.id); }, onError: (e) => toast.error(errorMessage(e)) });
  const scan = useMutation({ mutationFn: () => apiPost<ScanSessionOut>(`/scan-sessions/${sid}/scan`), onSuccess: put, onError: (e) => toast.error(errorMessage(e)) });
  const rotate = useMutation({ mutationFn: (p: { id: string; rotation: number }) => apiPatch<ScanSessionOut>(`/scan-sessions/${sid}/pages/${p.id}`, { rotation: (p.rotation + 90) % 360 }), onSuccess: put });
  const remove = useMutation({ mutationFn: (id: string) => apiDelete<ScanSessionOut>(`/scan-sessions/${sid}/pages/${id}`), onSuccess: put });
  const finalize = useMutation({ mutationFn: () => apiPost<OrderOut>(`/scan-sessions/${sid}/finalize`, { customer_name: name, customer_email: email.trim() || null }),
    onSuccess: (o) => { onOrder(o); setSid(null); }, onError: (e) => toast.error(errorMessage(e)) });
  const importFiles = async (files: FileList | null) => {
    for (const f of Array.from(files ?? [])) {
      try { put(await apiUpload<ScanSessionOut>(`/scan-sessions/${sid}/upload`, f)); } catch (e) { toast.error(`${f.name} : ${errorMessage(e)}`); }
    }
  };
  const pages = s?.pages ?? [];
  return (
    <section className="space-y-4 rounded-2xl border bg-card p-5" data-testid="scan-panel">
      <p className={cn("rounded-lg px-3 py-2 text-sm", online.length ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-950")} data-testid="scan-connection">
        {online.length ? `Scanner via le poste « ${online[0].name} » (en ligne)${s?.scanners?.length ? ` · ${s.scanners.join(", ")}` : ""}.`
          : "Aucun poste PrintDrop en ligne : le scan direct est indisponible. Scannez avec le logiciel du scanner puis importez les fichiers ci-dessous."}
      </p>
      {!s && (
        <>
          <div className="flex flex-wrap gap-4">
            <div className="space-y-1.5"><Label>Fichier</Label><Seg value={opt.format} options={[["pdf", "PDF"], ["jpg", "JPG"]]} onChange={(v) => setOpt({ ...opt, format: v })} testid="scan-format" /></div>
            <div className="space-y-1.5"><Label>Couleur</Label><Seg value={opt.color} options={[["bw", "N&B"], ["color", "Couleur"]]} onChange={(v) => setOpt({ ...opt, color: v })} testid="scan-color" /></div>
            <div className="space-y-1.5"><Label>Résolution</Label><Seg value={opt.dpi} options={[[150, "150"], [200, "200"], [300, "300"], [600, "600 ppp"]]} onChange={(v) => setOpt({ ...opt, dpi: v })} testid="scan-dpi" /></div>
            <div className="space-y-1.5"><Label>Pages</Label><Seg value={opt.source} options={[["flatbed", "Une page (vitre)"], ["feeder", "Plusieurs pages (chargeur)"]]} onChange={(v) => setOpt({ ...opt, source: v })} testid="scan-source" /></div>
          </div>
          <Button className="h-11 px-6 font-bold" disabled={create.isPending} onClick={() => create.mutate()} data-testid="scan-new"><ScanLine className="size-4" /> Scan document</Button>
        </>
      )}
      {s && (
        <>
          <p className="text-sm text-muted-foreground">Placez le document {s.source === "feeder" ? "dans le chargeur" : "sur la vitre"}, puis lancez le scan. Les pages s'ajoutent à la suite.</p>
          <div className="flex flex-wrap gap-2">
            <Button disabled={!s.agent_online || s.status === "scanning" || scan.isPending} onClick={() => scan.mutate()} data-testid="scan-start">
              {s.status === "scanning" ? <Loader2 className="size-4 animate-spin" /> : <ScanLine className="size-4" />} {pages.length ? "Scanner d'autres pages" : "Lancer le scan"}
            </Button>
            <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg border bg-white px-3 text-sm font-medium hover:bg-slate-50" data-testid="scan-import">
              <Upload className="size-4" /> Importer des fichiers (JPG, PNG)
              <input type="file" accept="image/jpeg,image/png" multiple className="hidden" onChange={(e) => importFiles(e.target.files)} data-testid="scan-import-input" />
            </label>
          </div>
          {s.error && <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900" data-testid="scan-error">{s.error} — les pages déjà scannées sont conservées, vous pouvez réessayer.</p>}
          <ol className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="scan-pages">
            {pages.map((pg) => (
              <li key={pg.id} className="space-y-1 rounded-lg border bg-white p-2" data-testid={`scan-page-${pg.index}`}>
                <img src={`/api/scan-sessions/${s.id}/pages/${pg.id}/image?r=${pg.rotation}`} alt={`Page ${pg.index + 1}`} className="mx-auto h-36 w-auto object-contain" />
                <div className="flex items-center justify-between text-xs">
                  <span>Page {pg.index + 1}</span>
                  <span className="flex gap-1">
                    <Button size="icon" variant="ghost" className="size-7" aria-label="Pivoter" onClick={() => rotate.mutate(pg)} data-testid={`scan-page-${pg.index}-rotate`}><RotateCw className="size-3.5" /></Button>
                    <Button size="icon" variant="ghost" className="size-7 text-rose-600" aria-label="Supprimer" onClick={() => remove.mutate(pg.id)} data-testid={`scan-page-${pg.index}-delete`}><Trash2 className="size-3.5" /></Button>
                  </span>
                </div>
              </li>
            ))}
          </ol>
          {pages.length > 0 && (
            <div className="flex flex-wrap items-end gap-3 rounded-xl bg-slate-50 p-4">
              <div className="space-y-1.5"><Label htmlFor="sname">Client (facultatif)</Label><Input id="sname" value={name} onChange={(e) => setName(e.target.value)} className="h-10 w-48" data-testid="scan-customer" /></div>
              <div className="space-y-1.5"><Label htmlFor="semail">E-mail (facultatif)</Label><Input id="semail" type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="h-10 w-56" data-testid="scan-email" /></div>
              <p className="flex-1 text-sm" data-testid="scan-total">{pages.length} page(s) · <strong className="font-heading text-xl text-ink">{formatEUR(pages.length * shop.pricing.scan_cents)}</strong> TTC</p>
              <Button className="h-11 font-bold" disabled={finalize.isPending || s.status === "scanning"} onClick={() => finalize.mutate()} data-testid="scan-finalize">
                <FileUp className="size-4" /> {s.format === "pdf" ? `Créer le PDF (${pages.length} page${pages.length > 1 ? "s" : ""})` : "Créer le JPG"}
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default function Counter() {
  const [tab, setTab] = useState<Tab>("copy");
  const [order, setOrder] = useState<OrderOut | null>(null);
  const tabs: [Tab, string, typeof Copy][] = [["phone", "Impression depuis le téléphone", Smartphone], ["copy", "Photocopie", Copy], ["scan", "Scan document", ScanLine]];
  return (
    <div className="space-y-5" data-testid="counter-page">
      <div>
        <h1 className="font-heading text-2xl font-bold text-ink">Comptoir</h1>
        <p className="text-sm text-muted-foreground">Servez un client sans compte ni code : impression, photocopie ou scan.</p>
      </div>
      <div className="flex flex-wrap gap-2" role="tablist">
        {tabs.map(([t, label, Icon]) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => { setTab(t); setOrder(null); }}
            className={cn("inline-flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold transition-colors", tab === t ? "border-azure bg-azure text-white" : "bg-white hover:border-azure/50")}
            data-testid={`counter-tab-${t}`}><Icon className="size-4" /> {label}</button>
        ))}
      </div>
      {order ? <CounterOrder order={order} onDone={() => setOrder(null)} /> : tab === "phone" ? (
        <section className="rounded-2xl border bg-card p-5 text-sm" data-testid="counter-phone">
          <p>Les commandes envoyées depuis le téléphone des clients arrivent dans <Link to="/dashboard" className="font-semibold text-azure underline">Commandes</Link>.
            Scannez le QR code du client ou saisissez son code à 4 chiffres en haut de la page pour ouvrir sa commande.</p>
        </section>
      ) : tab === "copy" ? <CopyPanel onOrder={setOrder} /> : <ScanPanel onOrder={setOrder} />}
    </div>
  );
}
