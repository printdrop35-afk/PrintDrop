import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SiteFooter, SiteHeader } from "@/components/site/SiteChrome";
import { apiPost, errorMessage } from "@/lib/api";
import { COMPANY } from "@/lib/brand";
import type { ContactIn, ContactOut } from "@/lib/types";

export function ContactForm({ defaultDemo = false }: { defaultDemo?: boolean }) {
  const [form, setForm] = useState<ContactIn>({
    kind: defaultDemo ? "demo" : "contact", name: "", business: "", email: "", subject: defaultDemo ? "Demande de démo" : "", message: "", website: "",
  });
  const send = useMutation({ mutationFn: () => apiPost<ContactOut>("/public/contact", form) });
  const set = (k: keyof ContactIn) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = (e: FormEvent) => { e.preventDefault(); send.mutate(); };

  if (send.data) {
    return (
      <div className="rounded-xl border bg-background p-6" data-testid="contact-success" role="status">
        <CheckCircle2 className="size-7 text-emerald-600" />
        <p className="mt-3 font-semibold text-ink">Merci, votre message a bien été reçu.</p>
        <p className="mt-1 text-sm text-slate-600">
          {send.data.delivered ? "Il a été transmis à l'équipe PrintDrop, qui vous répondra par e-mail." : "Il est enregistré et sera traité par l'équipe PrintDrop, qui vous répondra par e-mail."}
        </p>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="grid gap-4 rounded-xl border bg-background p-6 sm:grid-cols-2" data-testid="contact-form" noValidate={false}>
      <div className="space-y-1.5"><Label htmlFor="c-name">Nom *</Label><Input id="c-name" required minLength={2} maxLength={100} value={form.name} onChange={set("name")} autoComplete="name" data-testid="contact-name" /></div>
      <div className="space-y-1.5"><Label htmlFor="c-business">Établissement</Label><Input id="c-business" maxLength={120} value={form.business} onChange={set("business")} autoComplete="organization" data-testid="contact-business" /></div>
      <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="c-email">E-mail *</Label><Input id="c-email" type="email" required value={form.email} onChange={set("email")} autoComplete="email" data-testid="contact-email" /></div>
      <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="c-subject">Sujet *</Label><Input id="c-subject" required minLength={2} maxLength={150} value={form.subject} onChange={set("subject")} data-testid="contact-subject" /></div>
      <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="c-message">Message *</Label><Textarea id="c-message" required minLength={10} maxLength={4000} rows={5} value={form.message} onChange={set("message")} data-testid="contact-message" /></div>
      <input type="text" name="website" value={form.website} onChange={set("website")} tabIndex={-1} autoComplete="off" className="hidden" aria-hidden="true" />
      <label className="flex items-center gap-2 text-sm text-slate-600 sm:col-span-2">
        <input type="checkbox" checked={form.kind === "demo"} onChange={(e) => setForm((f) => ({ ...f, kind: e.target.checked ? "demo" : "contact" }))} className="size-4 accent-[#0868EF]" data-testid="contact-demo-checkbox" />
        Je souhaite une démonstration
      </label>
      {send.isError && <p className="text-sm text-rose-700 sm:col-span-2" role="alert" data-testid="contact-error">{errorMessage(send.error)}</p>}
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <Button type="submit" disabled={send.isPending} className="h-11 px-6" data-testid="contact-submit">{send.isPending ? "Envoi…" : "Envoyer le message"}</Button>
        <p className="text-xs text-slate-500">Vos données servent uniquement à répondre à votre demande.</p>
      </div>
    </form>
  );
}

export default function Contact() {
  const [params] = useSearchParams();
  const demo = params.get("sujet") === "demo";
  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main className="mx-auto grid max-w-7xl gap-10 px-5 py-16 sm:px-8 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <h1 className="font-heading text-4xl font-bold text-ink" data-testid="contact-title">{demo ? "Réserver une démo" : "Contactez PrintDrop"}</h1>
          <p className="mt-4 leading-relaxed text-slate-600">
            {demo ? "Dites-nous en quelques mots comment fonctionne votre boutique : nous vous proposerons un créneau de démonstration par e-mail." : "Une question sur PrintDrop, votre abonnement ou l'installation ? Écrivez-nous."}
          </p>
          <div className="mt-8 flex gap-3 rounded-xl border bg-white p-5 text-sm" data-testid="contact-address">
            <MapPin className="size-5 shrink-0 text-azure" />
            <address className="not-italic leading-relaxed text-slate-700">
              <span className="font-semibold text-ink">{COMPANY.name}</span><br />{COMPANY.street}<br />{COMPANY.postalCode} {COMPANY.city}<br />{COMPANY.country}
            </address>
          </div>
        </div>
        <ContactForm key={demo ? "demo" : "contact"} defaultDemo={demo} />
      </main>
      <SiteFooter />
    </div>
  );
}
