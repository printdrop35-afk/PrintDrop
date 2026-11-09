import { useRef, useState, type ChangeEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, ImageIcon, Loader2, MapPin, Minus, Plus, Trash2, UploadCloud, Copy, ScanLine, Sparkles, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Logo } from "@/components/Logo";
import { apiGet, apiPost, apiUpload, errorMessage } from "@/lib/api";
import { formatEUR, formatVat, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import type {
  DocumentUploadOut, OrderCreateIn, OrderPublicOut, PaperSize, PrintOptions, PublicShopOut, QuoteIn, QuoteOut, ServicesIn,
} from "@/lib/types";

const PAPER_SIZES: PaperSize[] = ["A4", "A3", "A5", "Letter", "Legal"];
const DEFAULT_OPTIONS: PrintOptions = { paper_size: "A4", color: "bw", duplex: false, copies: 1, page_range: "" };

interface CartDoc { upload: DocumentUploadOut; options: PrintOptions }

function Stepper({ value, onChange, min = 0, max = 1000, testId }: { value: number; onChange: (v: number) => void; min?: number; max?: number; testId: string }) {
  return (
    <div className="inline-flex items-center rounded-xl border bg-white">
      <button type="button" aria-label="Moins" className="grid size-10 place-items-center text-slate-600 transition-colors hover:text-azure disabled:opacity-30"
        disabled={value <= min} onClick={() => onChange(Math.max(min, value - 1))} data-testid={`${testId}-decrement`}>
        <Minus className="size-4" />
      </button>
      <span className="w-10 text-center font-mono text-sm font-semibold" data-testid={`${testId}-value`}>{value}</span>
      <button type="button" aria-label="Plus" className="grid size-10 place-items-center text-slate-600 transition-colors hover:text-azure disabled:opacity-30"
        disabled={value >= max} onClick={() => onChange(Math.min(max, value + 1))} data-testid={`${testId}-increment`}>
        <Plus className="size-4" />
      </button>
    </div>
  );
}

function Segmented<T extends string>({ value, options, onChange, testId }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; testId: string }) {
  return (
    <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
      {options.map((o) => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)} data-testid={`${testId}-${o.value}`}
          className={cn("h-9 rounded-lg text-sm font-medium transition-[background-color,color,box-shadow]",
            value === o.value ? "bg-white text-ink shadow-sm" : "text-slate-500 hover:text-ink")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function DocCard({ doc, index, onChange, onRemove, lineCents, selected, sizes }: { doc: CartDoc; index: number; onChange: (o: PrintOptions) => void; onRemove: () => void; lineCents?: number; selected?: number[] | null; sizes: PaperSize[] }) {
  const o = doc.options;
  const set = (patch: Partial<PrintOptions>) => onChange({ ...o, ...patch });
  const isPdf = doc.upload.kind === "pdf";
  return (
    <div className="animate-rise rounded-2xl border bg-white p-4 shadow-sm" data-testid={`doc-card-${index}`}>
      <div className="flex items-start gap-3">
        <span className={cn("grid size-11 shrink-0 place-items-center rounded-xl", isPdf ? "bg-rose-50 text-rose-600" : "bg-sky-50 text-sky-600")}>
          {isPdf ? <FileText className="size-5" /> : <ImageIcon className="size-5" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-ink" data-testid={`doc-card-${index}-filename`}>{doc.upload.filename}</p>
          <p className="text-xs text-muted-foreground" data-testid={`doc-card-${index}-pages`}>
            {doc.upload.page_count} page{doc.upload.page_count > 1 ? "s" : ""} · {(doc.upload.size_bytes / 1024 / 1024).toFixed(2)} Mo
          </p>
          {isPdf && selected && (
            <p className="mt-0.5 text-xs font-semibold text-azure" data-testid={`doc-card-${index}-selected`}>
              {selected.length} page{selected.length > 1 ? "s" : ""} sélectionnée{selected.length > 1 ? "s" : ""} sur {doc.upload.page_count}
              {o.page_range ? ` (${selected.join(", ")})` : ""}
            </p>
          )}
        </div>
        <div className="text-right">
          <p className="font-mono text-sm font-semibold text-ink" data-testid={`doc-card-${index}-price`}>{lineCents !== undefined ? formatEUR(lineCents) : "—"}</p>
          <button type="button" onClick={onRemove} className="mt-1 inline-flex items-center gap-1 text-xs text-slate-500 transition-colors hover:text-rose-600" data-testid={`doc-card-${index}-remove`}>
            <Trash2 className="size-3.5" /> Retirer
          </button>
        </div>
      </div>
      <div className="dot-grid mt-4 grid gap-3 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="text-xs text-slate-500">Format du papier</Label>
          <Select value={o.paper_size} onValueChange={(v: string) => set({ paper_size: v as PaperSize })}>
            <SelectTrigger className="h-10 w-full bg-white" data-testid={`doc-card-${index}-paper-select`}>
              <SelectValue>{(v) => tk("paper", v as string)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {sizes.map((s) => <SelectItem key={s} value={s} data-testid={`paper-option-${s}`}>{tk("paper", s)}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-slate-500">Couleur</Label>
          <Segmented value={o.color} onChange={(v) => set({ color: v })} testId={`doc-card-${index}-color`}
            options={[{ value: "bw", label: "N&B" }, { value: "color", label: "Couleur" }]} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-slate-500">Exemplaires</Label>
          <div><Stepper value={o.copies} min={1} max={100} onChange={(v) => set({ copies: v })} testId={`doc-card-${index}-copies`} /></div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-slate-500">Pages à imprimer</Label>
          <Input value={o.page_range} placeholder="Toutes (ex : 1-2, 4 ou 1,3)" onChange={(e) => set({ page_range: e.target.value })}
            disabled={!isPdf} className="h-10 bg-white" data-testid={`doc-card-${index}-range-input`} />
        </div>
        <label className="flex items-center gap-2.5 text-sm sm:col-span-2">
          <Checkbox checked={o.duplex} onCheckedChange={(c: boolean) => set({ duplex: c })} disabled={!isPdf || doc.upload.page_count < 2} data-testid={`doc-card-${index}-duplex-checkbox`} />
          Recto-verso <span className="text-xs text-muted-foreground">(économise du papier)</span>
        </label>
      </div>
    </div>
  );
}

export default function CustomerPortal() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);
  const [docs, setDocs] = useState<CartDoc[]>([]);
  const [uploading, setUploading] = useState(0);
  const [services, setServices] = useState<ServicesIn>({ photocopy_bw: 0, photocopy_color: 0, scan_pages: 0 });
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [email, setEmail] = useState("");
  const [notify, setNotify] = useState(true);
  const [extras, setExtras] = useState<Record<string, number>>({});
  const [promo, setPromo] = useState("");
  const [promoApplied, setPromoApplied] = useState<string | null>(null);

  const shopQ = useQuery({ queryKey: ["public-shop", slug], queryFn: () => apiGet<PublicShopOut>(`/public/shops/${slug}`), retry: false });
  const shop = shopQ.isError ? undefined : shopQ.data;

  const quoteBody: QuoteIn = {
    items: docs.map((d) => ({ document_id: d.upload.id, upload_token: d.upload.upload_token, options: d.options })),
    services,
    extras: Object.entries(extras).filter(([, q]) => q > 0).map(([service_id, quantity]) => ({ service_id, quantity })),
    promo_code: promoApplied,
  };
  const sizes = PAPER_SIZES.filter((s) => shop?.pricing.print[s]?.active ?? true);
  const hasSomething = docs.length > 0 || services.photocopy_bw + services.photocopy_color + services.scan_pages > 0 || quoteBody.extras.length > 0;
  const quoteQ = useQuery({
    queryKey: ["quote", slug, quoteBody],
    queryFn: () => apiPost<QuoteOut>(`/public/shops/${slug}/quote`, quoteBody),
    enabled: !!shop && hasSomething,
    placeholderData: keepPreviousData,
    retry: false,
  });
  const quote = hasSomething && !quoteQ.isError ? quoteQ.data : undefined;
  const lineFor = (docId: string) => quote?.lines.find((l) => l.document_id === docId)?.subtotal_cents;
  const selectedFor = (docId: string) => quote?.lines.find((l) => l.document_id === docId)?.selected_pages ?? null;

  const onFiles = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    for (const file of files) {
      setUploading((n) => n + 1);
      try {
        const upload = await apiUpload<DocumentUploadOut>(`/public/shops/${slug}/documents`, file);
        setDocs((prev) => [...prev, { upload, options: { ...DEFAULT_OPTIONS, paper_size: sizes[0] ?? "A4" } }]);
        toast.success(`${upload.filename} ajouté`);
      } catch (err) {
        toast.error(`${file.name} : ${errorMessage(err, "envoi impossible")}`);
      } finally {
        setUploading((n) => n - 1);
      }
    }
  };

  const order = useMutation({
    mutationFn: (body: OrderCreateIn) => apiPost<OrderPublicOut>(`/public/shops/${slug}/orders`, body),
    onSuccess: (o) => {
      sessionStorage.setItem(`pd_track_${o.code}`, phone);
      toast.success(`Commande ${o.code} envoyée`);
      navigate(`/suivi/${o.code}`);
    },
    onError: (err) => toast.error(errorMessage(err, "Commande impossible")),
  });

  const phoneOk = phone.trim() === "" || phone.replace(/\D/g, "").length >= 6; // phone is optional
  const canSubmit = !!quote && quote.total_cents > 0 && name.trim().length >= 2 && phoneOk && uploading === 0 && !quoteQ.isFetching;

  const svc = (key: keyof ServicesIn, label: string, unit: number | undefined, Icon: typeof Copy) => (
    <div className="flex items-center justify-between gap-3 py-3">
      <div className="flex items-center gap-3">
        <Icon className="size-5 text-slate-400" />
        <div>
          <p className="text-sm font-medium text-ink">{label}</p>
          <p className="text-xs text-muted-foreground">{unit !== undefined ? `${formatEUR(unit)} / page` : ""}</p>
        </div>
      </div>
      <Stepper value={services[key]} onChange={(v) => setServices({ ...services, [key]: v })} testId={`service-${key.replace("_", "-")}`} />
    </div>
  );

  return (
    <div className="min-h-screen bg-background pb-40">
      <header className="relative overflow-hidden bg-ink px-5 pt-6 pb-16 text-white">
        <div className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-azure/30 blur-3xl" />
        <div className="relative mx-auto max-w-[540px]">
          <Logo inverse className="scale-90 origin-left" />
          <p className="mt-6 text-xs font-semibold tracking-[0.15em] text-sky-300 uppercase">Dépôt d'impression</p>
          <h1 className="mt-1 text-3xl font-bold" data-testid="portal-shop-name">
            {shop?.name ?? (shopQ.isLoading ? "Chargement…" : "Boutique introuvable")}
          </h1>
          {shop && (
            <p className="mt-2 flex items-center gap-1.5 text-sm text-slate-300" data-testid="portal-shop-address">
              <MapPin className="size-4" /> {shop.address || shop.city}
            </p>
          )}
        </div>
      </header>

      <main className="relative mx-auto -mt-10 max-w-[540px] space-y-4 px-4">
        {shopQ.isError && (
          <div className="rounded-2xl border bg-white p-6 text-center shadow-sm" data-testid="portal-not-found">
            <p className="font-semibold text-ink">Ce QR code ne correspond à aucune boutique active.</p>
            <p className="mt-1 text-sm text-muted-foreground">Vérifiez le code affiché au comptoir ou demandez de l'aide au personnel.</p>
          </div>
        )}
        {shop && !shop.accepting_orders && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800" data-testid="portal-closed">
            Cette boutique n'accepte pas de commandes en ligne pour le moment.
          </div>
        )}
        {shop?.accepting_orders && (
          <>
            <button type="button" onClick={() => fileInput.current?.click()} data-testid="upload-dropzone"
              className="group flex w-full flex-col items-center rounded-2xl border-2 border-dashed border-slate-300 bg-white px-6 py-8 text-center shadow-sm transition-[border-color,box-shadow] hover:border-azure hover:shadow-md">
              {uploading > 0 ? <Loader2 className="size-9 animate-spin text-azure" /> : <UploadCloud className="size-9 text-azure transition-transform group-hover:-translate-y-0.5" />}
              <span className="mt-3 font-heading text-lg font-semibold text-ink">{uploading > 0 ? "Envoi en cours…" : "Ajouter des documents"}</span>
              <span className="mt-1 text-sm text-muted-foreground">PDF, Word, JPG ou PNG · 25 Mo max · fichiers privés</span>
            </button>
            <input ref={fileInput} type="file" multiple accept="application/pdf,image/png,image/jpeg,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="hidden" onChange={onFiles} data-testid="upload-file-input" />

            {docs.map((d, i) => (
              <DocCard key={d.upload.id} doc={d} index={i} lineCents={lineFor(d.upload.id)} selected={selectedFor(d.upload.id)} sizes={sizes}
                onChange={(options) => setDocs(docs.map((x, j) => (j === i ? { ...x, options } : x)))}
                onRemove={() => setDocs(docs.filter((_, j) => j !== i))} />
            ))}

            <section className="rounded-2xl border bg-white px-4 py-2 shadow-sm" data-testid="services-section">
              <p className="pt-2 text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Services au comptoir</p>
              <div className="divide-y">
                {shop.pricing.photocopy.active && svc("photocopy_bw", "Photocopies N&B", shop.pricing.photocopy.bw, Copy)}
                {shop.pricing.photocopy.active && svc("photocopy_color", "Photocopies couleur", shop.pricing.photocopy.color, Copy)}
                {svc("scan_pages", "Numérisation (scan)", shop.pricing.scan_cents, ScanLine)}
                {shop.pricing.services.map((s) => (
                  <div key={s.id} className="flex items-center justify-between gap-3 py-3" data-testid={`extra-${s.id}`}>
                    <div className="flex items-center gap-3">
                      <Sparkles className="size-5 text-slate-400" />
                      <div>
                        <p className="text-sm font-medium text-ink">{s.name}</p>
                        <p className="text-xs text-muted-foreground">{s.price_from ? "à partir de " : ""}{formatEUR(s.price_cents)} {tk("unit", s.unit)}{s.description ? ` · ${s.description}` : ""}</p>
                      </div>
                    </div>
                    <Stepper value={extras[s.id] ?? 0} onChange={(v) => setExtras({ ...extras, [s.id]: v })} testId={`extra-${s.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`} />
                  </div>
                ))}
              </div>
            </section>

            {(shop.pricing.rules.length > 0 || shop.pricing.auto_discounts.length > 0 || shop.pricing.min_order_cents > 0 || shop.pricing.has_promo_codes) && (
              <section className="space-y-2 rounded-2xl border bg-white p-4 shadow-sm" data-testid="offers-section">
                <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Remises & conditions</p>
                {shop.pricing.rules.map((r) => <p key={r.id} className="text-sm text-emerald-700">{r.name} : −{r.discount_pct} % sur l'impression dès {r.min_pages} pages</p>)}
                {shop.pricing.auto_discounts.map((d, i) => <p key={i} className="text-sm text-emerald-700">{d.name} : −{d.kind === "percent" ? `${d.value} %` : formatEUR(d.value)}{d.min_order_cents ? ` dès ${formatEUR(d.min_order_cents)}` : ""}</p>)}
                {shop.pricing.min_order_cents > 0 && <p className="text-xs text-muted-foreground">Minimum de commande : {formatEUR(shop.pricing.min_order_cents)}</p>}
                {shop.pricing.has_promo_codes && (
                  <div className="flex gap-2 pt-1">
                    <Input value={promo} onChange={(e) => setPromo(e.target.value.toUpperCase())} placeholder="Code promo" className="h-10 font-mono" data-testid="promo-code-input" />
                    <Button variant="outline" className="h-10" onClick={() => setPromoApplied(promo.trim() || null)} data-testid="promo-apply-button"><Tag className="size-4" /> Appliquer</Button>
                  </div>
                )}
                {promoApplied && quote?.promo_error && <p className="text-xs text-rose-600" data-testid="promo-error">{quote.promo_error}</p>}
                {promoApplied && quote?.promo_code_applied && <p className="text-xs text-emerald-700" data-testid="promo-success">Code {quote.promo_code_applied} appliqué</p>}
              </section>
            )}

            {quote && quote.lines.length > 0 && (
              <section className="rounded-2xl border bg-white p-4 shadow-sm" data-testid="price-breakdown">
                <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Détail du prix</p>
                <ul className="mt-2 divide-y text-sm">
                  {quote.lines.map((l, i) => (
                    <li key={i} className="flex justify-between gap-3 py-2" data-testid={`breakdown-line-${i}`}>
                      <span className="min-w-0"><span className={cn(l.kind === "discount" && "text-emerald-700")}>{l.label}</span>
                        {l.filename && <span className="block truncate text-xs text-muted-foreground">{l.filename} · {l.pages} p. × {l.copies}</span>}</span>
                      <span className={cn("shrink-0 font-mono", l.subtotal_cents < 0 && "text-emerald-700")}>{formatEUR(l.subtotal_cents)}</span>
                    </li>
                  ))}
                </ul>
                <dl className="mt-2 space-y-1 border-t pt-2 text-sm">
                  <div className="flex justify-between text-muted-foreground"><dt>Total HT</dt><dd className="font-mono" data-testid="breakdown-ht">{formatEUR(quote.total_ht_cents)}</dd></div>
                  <div className="flex justify-between text-muted-foreground"><dt>TVA {formatVat(quote.vat_rate_bp)}</dt><dd className="font-mono" data-testid="breakdown-vat">{formatEUR(quote.vat_cents)}</dd></div>
                  <div className="flex justify-between font-semibold text-ink"><dt>Total TTC</dt><dd className="font-mono" data-testid="breakdown-ttc">{formatEUR(quote.total_cents)}</dd></div>
                </dl>
              </section>
            )}

            <section className="space-y-3 rounded-2xl border bg-white p-4 shadow-sm" data-testid="customer-section">
              <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Vos coordonnées</p>
              <div className="space-y-1.5">
                <Label htmlFor="cname">Nom</Label>
                <Input id="cname" value={name} onChange={(e) => setName(e.target.value)} className="h-11" autoComplete="name" data-testid="customer-name-input" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cphone">Téléphone <span className="text-xs text-muted-foreground">(facultatif)</span></Label>
                <Input id="cphone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} className="h-11" autoComplete="tel" placeholder="06 12 34 56 78" data-testid="customer-phone-input" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cemail">Adresse e-mail <span className="text-xs text-muted-foreground">(facultatif)</span></Label>
                <Input id="cemail" type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="h-11" autoComplete="email" placeholder="vous@exemple.fr" data-testid="customer-email-input" />
              </div>
              {!phoneOk && <p className="text-xs text-rose-600" data-testid="customer-phone-error">Numéro incomplet — corrigez-le ou laissez le champ vide.</p>}
              {(phone.trim() || email.trim()) ? <label className="flex items-start gap-2.5 text-sm">
                <Checkbox checked={notify} onCheckedChange={(c: boolean) => setNotify(c)} className="mt-0.5" data-testid="customer-notify-checkbox" />
                <span>Me prévenir {phone.trim() && email.trim() ? "par SMS et e-mail" : phone.trim() ? "par SMS" : "par e-mail"} quand ma commande est prête</span>
              </label> : <p className="text-xs text-muted-foreground" data-testid="customer-no-contact-hint">Sans téléphone ni e-mail, suivez votre commande avec son code à 4 chiffres.</p>}
              <div className="space-y-1.5">
                <Label htmlFor="cnote">Remarque (facultatif)</Label>
                <Textarea id="cnote" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="Ex : agrafer chaque exemplaire" data-testid="customer-note-input" />
              </div>
              <p className="text-xs text-muted-foreground">Paiement au comptoir lors du retrait (espèces ou carte). Le paiement en ligne arrive prochainement.</p>
            </section>
          </>
        )}
      </main>

      {shop?.accepting_orders && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t bg-white/90 backdrop-blur-md">
          <div className="mx-auto flex max-w-[540px] items-center gap-4 px-4 py-3">
            <div className="flex-1">
              <p className="text-xs text-muted-foreground">
                {quoteQ.isError ? <span className="text-rose-600" data-testid="quote-error">{errorMessage(quoteQ.error)}</span> : quote ? `dont TVA ${formatEUR(quote.vat_cents)} · HT ${formatEUR(quote.total_ht_cents)}` : "Total TTC calculé par la boutique"}
              </p>
              <p className="font-mono text-2xl font-bold text-ink" data-testid="quote-total">
                {quote ? formatEUR(quote.total_cents) : formatEUR(0)}
                {quoteQ.isFetching && <Loader2 className="ml-2 inline size-4 animate-spin text-slate-400" />}
              </p>
            </div>
            <Button className="h-12 px-6 text-base" disabled={!canSubmit || order.isPending} data-testid="submit-order-button"
              onClick={() => order.mutate({ ...quoteBody, promo_code: quote?.promo_code_applied ?? null, customer_name: name, customer_phone: phone, customer_email: email.trim() || null, notify, note })}>
              {order.isPending ? "Envoi…" : "Commander"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
