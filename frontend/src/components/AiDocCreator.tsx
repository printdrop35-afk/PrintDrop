import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Loader2, Printer, Sparkles } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPost, errorMessage } from "@/lib/api";
import type { AiDocCatalogOut, AiDocDraftOut, AiDocFinalizeIn, AiDocGenerateIn, AiDocTemplateOut, DocumentUploadOut } from "@/lib/types";

type Step = "pick" | "form" | "edit";

/** A4-like preview using the same simple rules as the server PDF ('## ' heading, '- ' bullet, blank line = paragraph). */
function Preview({ title, body }: { title: string; body: string }) {
  const blocks = body.replace(/\r/g, "").split(/\n\s*\n/);
  return (
    <div className="mx-auto aspect-[210/297] w-full max-w-[420px] overflow-y-auto rounded-md border bg-white p-6 text-[11px] leading-relaxed text-slate-800 shadow-sm" data-testid="aidoc-preview">
      <p className="mb-3 text-base font-bold text-ink">{title}</p>
      {blocks.map((b, i) => {
        const lines = b.split("\n").filter((l) => l.trim());
        if (lines.length && lines.every((l) => l.trim().startsWith("- ")))
          return <ul key={i} className="mb-2 list-disc pl-4">{lines.map((l, j) => <li key={j}>{l.trim().slice(2)}</li>)}</ul>;
        if (lines.length === 1 && lines[0].trim().startsWith("## "))
          return <p key={i} className="mt-2 mb-1 text-xs font-bold">{lines[0].trim().slice(3)}</p>;
        return <p key={i} className="mb-2 whitespace-pre-line">{b.trim()}</p>;
      })}
    </div>
  );
}

export function AiDocCreator({ slug, open, onOpenChange, onDone }: {
  slug: string; open: boolean; onOpenChange: (o: boolean) => void; onDone: (doc: DocumentUploadOut) => void;
}) {
  const [step, setStep] = useState<Step>("pick");
  const [tpl, setTpl] = useState<AiDocTemplateOut | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const catalog = useQuery({ queryKey: ["aidoc-templates", slug], queryFn: () => apiGet<AiDocCatalogOut>(`/public/shops/${slug}/ai-docs/templates`), enabled: open, staleTime: 600_000 });
  const gen = useMutation({
    mutationFn: () => apiPost<AiDocDraftOut>(`/public/shops/${slug}/ai-docs/generate`, { template: tpl?.code ?? "", values } satisfies AiDocGenerateIn),
    onSuccess: (d) => { setTitle(d.title); setBody(d.body); setStep("edit"); },
  });
  const fin = useMutation({
    mutationFn: () => apiPost<DocumentUploadOut>(`/public/shops/${slug}/ai-docs/finalize`, { template: tpl?.code ?? "", title, body } satisfies AiDocFinalizeIn),
    onSuccess: (doc) => { onDone(doc); reset(); onOpenChange(false); },
  });
  const reset = () => { setStep("pick"); setTpl(null); setValues({}); setTitle(""); setBody(""); gen.reset(); fin.reset(); };
  const templates = catalog.isError ? [] : catalog.data?.templates ?? [];
  const categories = [...new Set(templates.map((t) => t.category))];
  const missing = tpl?.fields.some((f) => f.required && !(values[f.key] ?? "").trim());

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o && !fin.isPending) reset(); }}>
      <DialogContent className="max-h-[92vh] w-[calc(100%-1.5rem)] overflow-y-auto sm:max-w-3xl" data-testid="aidoc-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Sparkles className="size-5 text-azure" /> Créer un document avec l'IA</DialogTitle>
          <DialogDescription>Gratuit · le document final est ajouté directement à votre commande dans cette boutique.</DialogDescription>
        </DialogHeader>

        {step === "pick" && (
          <div className="space-y-5" data-testid="aidoc-step-pick">
            {catalog.isLoading && <Loader2 className="mx-auto size-6 animate-spin text-azure" />}
            {catalog.isError && <p className="text-sm text-rose-700" role="alert">{errorMessage(catalog.error)}</p>}
            {categories.map((c) => (
              <div key={c}>
                <p className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{c}</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {templates.filter((t) => t.category === c).map((t) => (
                    <button key={t.code} type="button" onClick={() => { setTpl(t); setValues({}); setStep("form"); }}
                      className="rounded-xl border bg-white px-4 py-3 text-left text-sm font-medium text-ink transition-[border-color,background-color] hover:border-azure hover:bg-azure/5"
                      data-testid={`aidoc-template-${t.code}`}>{t.name}</button>
                  ))}
                </div>
              </div>
            ))}
            {catalog.data && (
              <a href={catalog.data.catalogue_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm font-medium text-azure hover:underline" data-testid="aidoc-catalogue-link">
                Voir le catalogue complet sur ProDocOnline <ExternalLink className="size-3.5" />
              </a>
            )}
          </div>
        )}

        {step === "form" && tpl && (
          <form className="space-y-4" data-testid="aidoc-step-form" onSubmit={(e) => { e.preventDefault(); gen.mutate(); }}>
            <button type="button" onClick={() => setStep("pick")} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-ink" data-testid="aidoc-back-to-templates"><ArrowLeft className="size-4" /> Modèles</button>
            <p className="font-heading text-lg font-semibold text-ink" data-testid="aidoc-template-name">{tpl.name}</p>
            {tpl.fields.map((f) => (
              <div key={f.key} className="space-y-1.5">
                <Label htmlFor={`aidoc-${f.key}`}>{f.label}{f.required ? " *" : " (facultatif)"}</Label>
                {f.multiline
                  ? <Textarea id={`aidoc-${f.key}`} rows={3} maxLength={3000} placeholder={f.placeholder} value={values[f.key] ?? ""} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} data-testid={`aidoc-field-${f.key}`} />
                  : <Input id={`aidoc-${f.key}`} maxLength={300} placeholder={f.placeholder} value={values[f.key] ?? ""} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} data-testid={`aidoc-field-${f.key}`} />}
              </div>
            ))}
            <p className="text-xs text-muted-foreground">L'IA n'invente aucune information : ce qui manque apparaît « [à compléter] » et reste modifiable.</p>
            {gen.isError && <p className="text-sm text-rose-700" role="alert" data-testid="aidoc-generate-error">{errorMessage(gen.error)}</p>}
            <Button type="submit" disabled={gen.isPending || missing} className="h-11" data-testid="aidoc-generate-button">
              {gen.isPending ? <><Loader2 className="size-4 animate-spin" /> Rédaction en cours…</> : <><Sparkles className="size-4" /> Générer le document</>}
            </Button>
          </form>
        )}

        {step === "edit" && tpl && (
          <div className="space-y-4" data-testid="aidoc-step-edit">
            <button type="button" onClick={() => setStep("form")} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-ink" data-testid="aidoc-back-to-form"><ArrowLeft className="size-4" /> Modifier les informations</button>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-3">
                <div className="space-y-1.5"><Label htmlFor="aidoc-title">Titre</Label><Input id="aidoc-title" maxLength={150} value={title} onChange={(e) => setTitle(e.target.value)} data-testid="aidoc-edit-title" /></div>
                <div className="space-y-1.5"><Label htmlFor="aidoc-body">Texte (corrigez librement)</Label>
                  <Textarea id="aidoc-body" rows={16} maxLength={20000} value={body} onChange={(e) => setBody(e.target.value)} className="font-mono text-xs" data-testid="aidoc-edit-body" /></div>
              </div>
              <div><p className="mb-1.5 text-sm font-medium">Aperçu</p><Preview title={title} body={body} /></div>
            </div>
            {fin.isError && <p className="text-sm text-rose-700" role="alert" data-testid="aidoc-finalize-error">{errorMessage(fin.error)}</p>}
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => fin.mutate()} disabled={fin.isPending || body.trim().length < 10} className="h-11" data-testid="aidoc-print-button">
                {fin.isPending ? <><Loader2 className="size-4 animate-spin" /> Création du PDF…</> : <><Printer className="size-4" /> Imprimer avec PrintDrop</>}
              </Button>
              <p className="text-xs text-muted-foreground">En cliquant, vous validez cette version : le PDF final est ajouté à votre commande.</p>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
