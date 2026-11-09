import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, BarChart3, Bell, Calculator, CheckCircle2, ChevronDown, Clock, FileText, Layers, ListOrdered, Printer, QrCode,
  ShieldCheck, Smartphone, Store, Users,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { SiteFooter, SiteHeader } from "@/components/site/SiteChrome";
import { usePreviewHref } from "@/components/brand/BrandPreview";
import { ContactForm } from "@/pages/site/Contact";
import { apiGet } from "@/lib/api";
import { formatEUR } from "@/i18n";
import { cn } from "@/lib/utils";
import type { PublicPlanOut } from "@/lib/types";

const STEPS = [
  { icon: QrCode, title: "Le client scanne le QR code", text: "Affiché au comptoir ou en vitrine. Aucun compte ni application à installer." },
  { icon: FileText, title: "Il envoie ses documents", text: "PDF, Word, photos depuis son téléphone. Il choisit format, couleur et exemplaires et voit le prix calculé selon vos tarifs." },
  { icon: Printer, title: "Vous imprimez, il récupère", text: "La commande arrive dans votre file. Vous lancez l'impression et le client est prévenu quand c'est prêt." },
];

const FEATURES = [
  { icon: ListOrdered, title: "File d'impression en temps réel", text: "Commandes, statuts et travaux d'impression au même endroit, actualisés automatiquement.", wide: true },
  { icon: Calculator, title: "Vos tarifs, calculés par le serveur", text: "A4/A3, N&B/couleur, recto-verso, reliure, plastification, remises et minimum de commande." },
  { icon: QrCode, title: "QR code par boutique", text: "Un portail client à votre nom, prêt à imprimer pour le comptoir." },
  { icon: Printer, title: "Impression directe", text: "Agent Windows pour envoyer les documents vers vos imprimantes USB ou réseau en un clic." },
  { icon: BarChart3, title: "Rapports quotidiens", text: "Chiffre d'affaires, pages imprimées et heures d'affluence, par e-mail chaque soir." },
  { icon: Users, title: "Équipe et multi-boutiques", text: "Comptes employés avec permissions, plusieurs points de vente, journal d'audit.", wide: true },
];

const BENEFITS = [
  { icon: Clock, title: "Moins d'attente au comptoir", text: "Plus de clés USB ni d'e-mails à ouvrir : les documents arrivent prêts à imprimer." },
  { icon: ShieldCheck, title: "Documents privés", text: "Chaque boutique ne voit que ses propres commandes. Les fichiers sont ouverts par lien sécurisé à durée limitée." },
  { icon: Bell, title: "Clients informés", text: "Message « commande prête » par e-mail, suivi de commande avec code et téléphone." },
  { icon: Layers, title: "Prix justes et cohérents", text: "Le même tarif pour tous, calculé automatiquement, sans erreur de calcul au comptoir." },
];

const FAQ = [
  { q: "Mes clients doivent-ils installer une application ?", a: "Non. Ils scannent le QR code de votre boutique et utilisent la page web PrintDrop depuis le navigateur de leur téléphone, sans créer de compte." },
  { q: "Quels fichiers sont acceptés ?", a: "PDF, images PNG et JPG, ainsi que les documents Word (.docx), convertis automatiquement en PDF avant impression." },
  { q: "Comment le prix est-il calculé ?", a: "Selon la grille que vous configurez (format, couleur, recto-verso, services, remises). Le calcul est fait par le serveur : le client ne peut pas modifier le prix." },
  { q: "Comment mes clients paient-ils ?", a: "Le paiement se fait au comptoir (espèces ou carte) et vous l'enregistrez dans PrintDrop. Le paiement en ligne par les clients n'est pas encore disponible." },
  { q: "Quelles imprimantes sont compatibles ?", a: "L'impression directe passe par l'agent PrintDrop installé sur un PC Windows 10/11 et utilise les imprimantes installées sur ce PC (USB, Wi-Fi ou Ethernet). Testez-le sur votre matériel pendant l'essai. Sans agent, vous pouvez toujours télécharger les documents et les imprimer vous-même." },
  { q: "Puis-je essayer avant de m'abonner ?", a: "Oui, l'essai gratuit dure 14 jours, sans carte bancaire. L'abonnement se renouvelle ensuite manuellement à chaque échéance, sans prélèvement automatique." },
];

export default function LandingV2() {
  const href = usePreviewHref();
  const plans = useQuery({ queryKey: ["public-plans"], queryFn: () => apiGet<PublicPlanOut[]>("/public/plans") });
  const planList = plans.isError ? [] : plans.data ?? [];

  return (
    <div className="min-h-screen bg-background text-ink">
      <SiteHeader home />
      <main>
        {/* HERO */}
        <section className="relative overflow-hidden bg-white">
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#E2E8F0_1px,transparent_1px),linear-gradient(to_bottom,#E2E8F0_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_at_top_right,black,transparent_70%)] opacity-60" />
          <div className="relative mx-auto grid max-w-7xl items-center gap-14 px-5 py-16 sm:px-8 lg:grid-cols-[1.1fr_1fr] lg:py-24">
            <div className="animate-rise">
              <p className="inline-flex items-center gap-2 rounded-full bg-[#E0F7FA] px-3 py-1 text-xs font-semibold tracking-[0.15em] text-[#0E7490] uppercase">
                <Store className="size-3.5" /> Imprimeries · Reprographies · Cybercafés
              </p>
              <h1 className="mt-6 font-heading text-[2.6rem] leading-[1.05] font-bold text-ink sm:text-6xl" data-testid="hero-title">
                Votre imprimerie.<br />Plus intelligente.<br />Plus rapide. <span className="text-azure">Digitale.</span>
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600">
                Permettez à vos clients d'envoyer leurs documents directement depuis leur smartphone. Simplifiez les commandes d'impression,
                gagnez du temps au comptoir et modernisez votre activité.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/inscription" className={cn(buttonVariants({ size: "lg" }), "h-12 px-6 text-base")} data-testid="hero-cta-trial">
                  Essai gratuit 14 jours <ArrowRight className="size-4" />
                </Link>
                <Link to={href("/contact?sujet=demo")} className={cn(buttonVariants({ variant: "outline", size: "lg" }), "h-12 px-6 text-base")} data-testid="hero-cta-demo">
                  Réserver une démo
                </Link>
              </div>
              <p className="mt-4 text-sm text-slate-500">Sans carte bancaire · Sans engagement · Paiement au comptoir pour vos clients</p>
            </div>
            <PhoneDemo />
          </div>
        </section>

        {/* WHAT IS */}
        <section className="border-y bg-background">
          <div className="mx-auto grid max-w-7xl gap-8 px-5 py-14 sm:px-8 md:grid-cols-[1fr_1.4fr] md:items-center">
            <h2 className="font-heading text-3xl font-bold text-ink">Qu'est-ce que PrintDrop ?</h2>
            <p className="text-lg leading-relaxed text-slate-600" data-testid="what-is">
              PrintDrop est une solution digitale de gestion des commandes et d'impression par QR code pour les professionnels de l'impression.
              Vos clients déposent leurs documents en ligne, vous recevez des commandes complètes avec le prix déjà calculé, et vous les imprimez en un clic.
            </p>
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section id="comment-ca-marche" className="mx-auto max-w-7xl scroll-mt-20 px-5 py-20 sm:px-8">
          <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Comment ça marche</p>
          <h2 className="mt-3 max-w-2xl font-heading text-3xl font-bold text-ink sm:text-4xl">Trois étapes, du téléphone du client à votre imprimante.</h2>
          <ol className="mt-12 grid gap-5 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className="relative rounded-xl border bg-white p-6 transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-azure/30" data-testid={`step-${i + 1}`}>
                <span className="font-mono text-sm font-semibold text-azure">0{i + 1}</span>
                <s.icon className="mt-4 size-7 text-ink" />
                <h3 className="mt-4 text-lg font-semibold text-ink">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{s.text}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* FEATURES */}
        <section id="fonctionnalites" className="scroll-mt-20 bg-white">
          <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
            <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Fonctionnalités</p>
            <h2 className="mt-3 max-w-2xl font-heading text-3xl font-bold text-ink sm:text-4xl">Tout ce qu'il faut pour gérer vos commandes d'impression.</h2>
            <div className="mt-12 grid gap-4 md:grid-cols-3">
              {FEATURES.map((f) => (
                <article key={f.title} className={cn("rounded-xl border bg-background p-6 transition-colors duration-200 hover:border-azure/30", f.wide && "md:col-span-2")}>
                  <span className="grid size-10 place-items-center rounded-lg bg-white text-azure ring-1 ring-slate-200"><f.icon className="size-5" /></span>
                  <h3 className="mt-4 font-semibold text-ink">{f.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{f.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* DASHBOARD PREVIEW */}
        <section className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
          <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr] lg:items-center">
            <div>
              <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Tableau de bord</p>
              <h2 className="mt-3 font-heading text-3xl font-bold text-ink">Vos commandes en un coup d'œil.</h2>
              <p className="mt-4 leading-relaxed text-slate-600">Statuts, paiements, impression directe et alertes imprimante : votre comptoir est piloté depuis un seul écran, sur ordinateur ou tablette.</p>
              <Link to="/inscription" className={cn(buttonVariants(), "mt-6")} data-testid="dashboard-cta-trial">Essayer le tableau de bord <ArrowRight className="size-4" /></Link>
            </div>
            <DashboardMock />
          </div>
        </section>

        {/* QR DEMO */}
        <section id="demo-qr" className="scroll-mt-20 bg-ink text-white">
          <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 sm:px-8 lg:grid-cols-2 lg:items-center">
            <div>
              <p className="text-xs font-semibold tracking-[0.15em] text-[#5EEAD4] uppercase">Démo QR</p>
              <h2 className="mt-3 font-heading text-3xl font-bold">Essayez le portail client comme vos clients.</h2>
              <p className="mt-4 leading-relaxed text-slate-300">
                Ouvrez la boutique de démonstration, envoyez un document et voyez le prix se calculer. C'est exactement la page que vos clients obtiennent en scannant votre QR code.
              </p>
              <ul className="mt-6 space-y-2 text-sm text-slate-200">
                {["Aucune installation, fonctionne sur tous les smartphones", "Prix affiché avant validation", "Code de suivi remis au client"].map((t) => (
                  <li key={t} className="flex gap-2"><CheckCircle2 className="size-4 shrink-0 text-[#08BBD0]" /> {t}</li>
                ))}
              </ul>
              <Link to={href("/s/cybercafe-bastille")} className={cn(buttonVariants({ size: "lg" }), "mt-8 h-12 bg-[#08BBD0] px-6 text-[#042F2E] hover:bg-[#069EAF]")} data-testid="qr-demo-open">
                <Smartphone className="size-4" /> Ouvrir la boutique de démonstration
              </Link>
            </div>
            <img src="https://images.unsplash.com/photo-1600147131759-880e94a6185f?crop=entropy&cs=srgb&fm=jpg&w=1100&q=75" alt="Client scannant un QR code avec son smartphone"
              loading="lazy" width={1100} height={733} className="aspect-[3/2] w-full rounded-2xl object-cover" />
          </div>
        </section>

        {/* BENEFITS */}
        <section className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
          <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Pour les professionnels</p>
          <h2 className="mt-3 max-w-2xl font-heading text-3xl font-bold text-ink sm:text-4xl">Pensé pour le quotidien d'une boutique d'impression.</h2>
          <div className="mt-12 grid gap-x-10 gap-y-8 sm:grid-cols-2">
            {BENEFITS.map((b) => (
              <div key={b.title} className="flex gap-4">
                <b.icon className="mt-0.5 size-6 shrink-0 text-azure" />
                <div><h3 className="font-semibold text-ink">{b.title}</h3><p className="mt-1 text-sm leading-relaxed text-slate-600">{b.text}</p></div>
              </div>
            ))}
          </div>
        </section>

        {/* PRICING */}
        <section id="tarifs" className="scroll-mt-20 border-y bg-white">
          <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
            <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Tarifs</p>
            <h2 className="mt-3 font-heading text-3xl font-bold text-ink sm:text-4xl">Un abonnement simple, selon la taille de votre activité.</h2>
            <p className="mt-3 text-slate-600">14 jours d'essai gratuit, sans carte bancaire. Prix hors taxes, renouvellement manuel à chaque échéance.</p>
            <div className="mt-10 grid gap-5 md:grid-cols-3" data-testid="pricing-plans">
              {planList.map((p, i) => (
                <article key={p.code} className={cn("flex flex-col rounded-xl border bg-background p-6", i === 1 && "border-azure ring-1 ring-azure")} data-testid={`plan-${p.code}`}>
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-ink">{p.name}</h3>
                    {i === 1 && <span className="rounded-full bg-azure px-2.5 py-0.5 text-xs font-semibold text-white">Le plus choisi</span>}
                  </div>
                  <p className="mt-1 text-sm text-slate-600">{p.description}</p>
                  <p className="mt-5"><span className="font-heading text-4xl font-bold text-ink">{formatEUR(p.monthly_ht_cents)}</span> <span className="text-sm text-slate-500">HT / mois</span></p>
                  <ul className="mt-5 flex-1 space-y-2 text-sm text-slate-700">
                    {p.features.map((f) => <li key={f} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-azure" /> {f}</li>)}
                  </ul>
                  <Link to="/inscription" className={cn(buttonVariants({ variant: i === 1 ? "default" : "outline" }), "mt-6 w-full")} data-testid={`plan-${p.code}-cta`}>Commencer l'essai</Link>
                </article>
              ))}
              {plans.isPending && <p className="text-sm text-slate-500">Chargement des offres…</p>}
            </div>
            {/* Note: « Le plus choisi » is a presentation highlight, not a usage statistic. */}
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="mx-auto max-w-3xl scroll-mt-20 px-5 py-20 sm:px-8">
          <h2 className="font-heading text-3xl font-bold text-ink">Questions fréquentes</h2>
          <div className="mt-8 divide-y rounded-xl border bg-white" data-testid="faq-list">
            {FAQ.map((f, i) => (
              <details key={f.q} className="group p-5" data-testid={`faq-${i}`}>
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold text-ink">
                  {f.q}<ChevronDown className="size-4 shrink-0 text-slate-400 transition-transform duration-200 group-open:rotate-180" />
                </summary>
                <p className="mt-3 text-sm leading-relaxed text-slate-600">{f.a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* CONTACT */}
        <section id="contact" className="scroll-mt-20 bg-white">
          <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 sm:px-8 lg:grid-cols-[1fr_1.3fr]">
            <div>
              <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Contact</p>
              <h2 className="mt-3 font-heading text-3xl font-bold text-ink">Une question, une démo ?</h2>
              <p className="mt-4 leading-relaxed text-slate-600">Écrivez-nous : nous vous répondons par e-mail et organisons une démonstration adaptée à votre boutique.</p>
            </div>
            <ContactForm />
          </div>
        </section>

        {/* CTA */}
        <section className="bg-azure">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-6 px-5 py-14 sm:px-8">
            <h2 className="max-w-xl font-heading text-3xl font-bold text-white">Modernisez votre comptoir dès aujourd'hui.</h2>
            <div className="flex flex-wrap gap-3">
              <Link to="/inscription" className={cn(buttonVariants({ size: "lg" }), "h-12 bg-white px-6 text-azure hover:bg-slate-100")} data-testid="cta-trial">Essai gratuit 14 jours</Link>
              <Link to={href("/contact?sujet=demo")} className={cn(buttonVariants({ variant: "outline", size: "lg" }), "h-12 border-white/60 bg-transparent px-6 text-white hover:bg-white/10 hover:text-white")} data-testid="cta-demo">Réserver une démo</Link>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

function PhoneDemo() {
  return (
    <figure className="relative mx-auto w-full max-w-[340px] animate-rise" aria-label="Illustration du portail client sur smartphone">
      <div className="rounded-[2.2rem] border-[10px] border-ink bg-white shadow-[0_30px_60px_-30px_rgba(9,38,92,0.45)]">
        <div className="rounded-t-[1.4rem] bg-ink px-5 pt-6 pb-5 text-white">
          <p className="text-[11px] font-semibold tracking-[0.15em] text-[#7DD3FC] uppercase">Portail client</p>
          <p className="mt-1 font-heading text-lg font-bold">Votre boutique</p>
        </div>
        <div className="space-y-3 p-4">
          <div className="grid place-items-center rounded-xl border-2 border-dashed border-azure/40 bg-[#F4F7FC] py-5 text-center text-xs text-slate-600">
            <FileText className="size-6 text-azure" /><span className="mt-1.5 font-semibold text-ink">memoire.pdf</span>24 pages
          </div>
          {[["Format", "A4"], ["Couleur", "Noir & blanc"], ["Recto-verso", "Oui"], ["Exemplaires", "2"]].map(([k, v]) => (
            <div key={k} className="flex justify-between rounded-lg border px-3 py-2 text-xs"><span className="text-slate-500">{k}</span><span className="font-semibold text-ink">{v}</span></div>
          ))}
          <div className="flex items-center justify-between rounded-xl bg-azure px-4 py-3 text-white">
            <span className="text-xs">Total</span><span className="font-mono text-sm font-semibold">calculé par la boutique</span>
          </div>
        </div>
      </div>
      <figcaption className="mt-3 text-center text-xs text-slate-500">Illustration — l'affichage réel dépend des tarifs de chaque boutique.</figcaption>
    </figure>
  );
}

function DashboardMock() {
  const rows = [
    ["PD-7K2M9Q", "memoire.pdf", "En attente", "bg-amber-50 text-amber-800"],
    ["PD-3XH8LT", "cv.docx", "En impression", "bg-[#EAF2FE] text-[#0756C5]"],
    ["PD-9PW4RA", "photo.jpg", "Prête", "bg-emerald-50 text-emerald-800"],
  ];
  return (
    <figure className="overflow-hidden rounded-xl border bg-white shadow-[0_24px_48px_-28px_rgba(9,38,92,0.35)]" aria-label="Illustration du tableau de bord">
      <div className="flex items-center gap-1.5 border-b bg-[#F4F7FC] px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-slate-300" /><span className="size-2.5 rounded-full bg-slate-300" /><span className="size-2.5 rounded-full bg-slate-300" />
        <span className="ml-3 text-xs text-slate-500">Commandes</span>
      </div>
      <div className="grid grid-cols-[150px_1fr]">
        <div className="hidden space-y-1 bg-ink p-3 text-xs text-slate-300 sm:block" style={{ gridRow: "span 2" }}>
          {["Commandes", "File d'impression", "Rapports", "Tarifs", "Imprimantes"].map((n, i) => (
            <div key={n} className={cn("rounded-md px-2.5 py-2", i === 0 && "bg-azure text-white")}>{n}</div>
          ))}
        </div>
        <div className="col-span-2 p-4 sm:col-span-1">
          <table className="w-full text-left text-xs">
            <thead className="text-[11px] tracking-wider text-slate-500 uppercase"><tr><th className="py-2">Code</th><th>Document</th><th>Statut</th></tr></thead>
            <tbody>
              {rows.map(([c, d, s, cls]) => (
                <tr key={c} className="border-t"><td className="py-2.5 font-mono font-semibold text-ink">{c}</td><td className="text-slate-600">{d}</td>
                  <td><span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", cls)}>{s}</span></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <figcaption className="border-t px-4 py-2 text-[11px] text-slate-500">Illustration — données d'exemple.</figcaption>
    </figure>
  );
}
