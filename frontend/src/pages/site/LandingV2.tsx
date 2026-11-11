import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight, BarChart3, Calculator, CheckCircle2, ChevronDown, Clock, Download, FileText, ImageIcon, KeyRound, ListOrdered,
  MessageCircle, Phone, Printer, QrCode, Quote, ShieldCheck, Smartphone, Store, Timer, Usb, Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { buttonVariants } from "@/components/ui/button";
import { SiteFooter, SiteHeader } from "@/components/site/SiteChrome";
import { SITE_CONFIG } from "@/config/site";
import { track } from "@/lib/analytics";
import { apiGet, apiPost, errorMessage } from "@/lib/api";
import { formatEUR } from "@/i18n";
import { cn } from "@/lib/utils";
import type { ContactIn, ContactOut, PublicAgentVersionOut, PublicPlanOut } from "@/lib/types";

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

const FAQ = [
  { q: "Est-ce compatible avec mon imprimante ?", a: "L'impression directe passe par l'agent PrintDrop sur un PC Windows 10/11 et utilise les imprimantes déjà installées sur ce PC (USB, Wi-Fi ou réseau), avec leur pilote habituel. Si votre imprimante imprime depuis ce PC, elle fonctionne en principe avec PrintDrop : testez-la pendant l'essai. Sans agent, vous pouvez toujours télécharger les documents et les imprimer vous-même." },
  { q: "Faut-il laisser un PC allumé toute la journée ?", a: "Uniquement pour l'impression directe : l'agent doit tourner sur le PC relié aux imprimantes pendant vos heures d'ouverture (il peut démarrer avec Windows). Les commandes des clients sont reçues même PC éteint ; elles vous attendent dans le tableau de bord." },
  { q: "Mes données et celles de mes clients sont-elles protégées (RGPD) ?", a: "Les données sont strictement isolées par entreprise : une boutique ne voit jamais les commandes d'une autre. Les documents sont envoyés dans un espace privé, ouverts uniquement par lien sécurisé à durée limitée, et supprimés automatiquement après le retrait ou l'annulation de la commande. Le détail figure dans la politique de confidentialité." },
  { q: "Que se passe-t-il si le fichier d'un client est illisible ou mal formaté ?", a: "Le fichier est vérifié dès l'envoi : un format non accepté ou un document illisible est refusé avec un message clair, et le client peut en envoyer un autre. Les fichiers Word (.docx) sont convertis en PDF ; vous voyez le document avant d'imprimer et pouvez annuler la commande si besoin." },
  { q: "Comment est calculé le prix ?", a: "Par le serveur, à partir des tarifs configurés par votre boutique (format, couleur, recto-verso, services, remises, minimum de commande). Le client voit le prix exact avant de valider et ne peut pas le modifier." },
  { q: "Puis-je gérer plusieurs boutiques et une équipe ?", a: "Oui. Vous créez des comptes employés avec des permissions adaptées, et selon votre offre vous gérez plusieurs boutiques, chacune avec son QR code et ses tarifs. Un journal d'audit garde la trace des actions." },
  { q: "Le paiement en ligne est-il disponible ?", a: "Pas encore pour vos clients : aujourd'hui, ils paient au comptoir (espèces ou carte) et vous enregistrez le paiement dans PrintDrop. Le paiement en ligne est prévu sur la feuille de route." },
  { q: "Combien de temps pour démarrer ?", a: SITE_CONFIG.startupTime || "[À compléter]" },
];

const STRIP = [
  { icon: Clock, text: "Moins d'attente au comptoir" },
  { icon: Usb, text: "Plus de clés USB (et de virus)" },
  { icon: Calculator, text: "Prix toujours exacts, zéro litige" },
  { icon: Printer, text: "Impression automatique depuis votre PC" },
];

const WHY = [
  { icon: Timer, title: "Du temps gagné à chaque client", text: "Le client prépare sa commande dans la file d'attente. Au comptoir, vous n'avez plus qu'à imprimer et encaisser." },
  { icon: Calculator, title: "Moins d'erreurs", text: "Format, couleur, recto-verso et exemplaires sont choisis par le client et le prix est calculé selon vos tarifs. Plus de malentendu." },
  { icon: ShieldCheck, title: "Fini l'e-mail perso et les clés USB", text: "Les documents arrivent dans votre espace PrintDrop, pas dans votre boîte mail. Aucune clé USB inconnue branchée sur votre PC." },
  { icon: Users, title: "Servir plus de clients", text: "Les commandes s'enchaînent sans bouchon au comptoir, même aux heures de pointe, avec un code de suivi pour chaque client." },
];

const AGENT_STEPS = [
  { title: "Téléchargez l'agent", text: "Depuis « Imprimantes » dans votre tableau de bord, installez PrintDrop sur le PC Windows 10/11 relié à vos imprimantes." },
  { title: "Appairez-le à votre boutique", text: "Saisissez le code d'appairage affiché dans le tableau de bord. L'agent détecte les imprimantes installées sur le PC." },
  { title: "Imprimez en un clic", text: "Lancez une commande depuis le tableau de bord : les fichiers partent directement vers l'imprimante, sans téléchargement ni ouverture manuelle." },
];

export default function LandingV2() {
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
                <Link to="/inscription" onClick={() => track("Signup CTA", { from: "hero" })} className={cn(buttonVariants({ size: "lg" }), "h-12 px-6 text-base")} data-testid="hero-cta-trial">
                  Essai gratuit 14 jours <ArrowRight className="size-4" />
                </Link>
                <Link to={`/s/${SITE_CONFIG.demoShop.slug}`} className={cn(buttonVariants({ variant: "outline", size: "lg" }), "h-12 px-6 text-base")} data-testid="hero-cta-portal">
                  Essayer le portail client
                </Link>
                <a href="#demo" className="inline-flex h-12 items-center gap-2 rounded-md px-3 text-base font-medium text-azure underline-offset-4 transition-colors hover:text-ink hover:underline" data-testid="hero-cta-demo">
                  Réserver une démo de 15 min
                </a>
              </div>
              <p className="mt-4 text-sm text-slate-500">Sans carte bancaire · Sans engagement · Paiement au comptoir pour vos clients</p>
            </div>
            <PhoneDemo />
          </div>
        </section>

        {/* BENEFIT STRIP */}
        <section aria-label="Bénéfices" className="bg-ink text-white">
          <ul className="mx-auto grid max-w-7xl grid-cols-1 gap-x-6 gap-y-4 px-5 py-6 sm:grid-cols-2 sm:px-8 lg:grid-cols-4" data-testid="benefit-strip">
            {STRIP.map((b, i) => (
              <li key={b.text} className="flex items-center gap-3 text-sm font-medium" data-testid={`benefit-strip-${i}`}>
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-white/10 text-[#5EEAD4]"><b.icon className="size-4" aria-hidden="true" /></span>{b.text}
              </li>
            ))}
          </ul>
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

        {/* WHY */}
        <section id="pourquoi" className="scroll-mt-20 border-y bg-white">
          <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
            <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Pourquoi PrintDrop</p>
            <h2 className="mt-3 max-w-2xl font-heading text-3xl font-bold text-ink sm:text-4xl">Ce que ça change pour votre boutique.</h2>
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {WHY.map((w, i) => (
                <article key={w.title} className="rounded-xl border bg-background p-6 transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-azure/30" data-testid={`why-card-${i}`}>
                  <span className="grid size-10 place-items-center rounded-lg bg-white text-azure ring-1 ring-slate-200"><w.icon className="size-5" aria-hidden="true" /></span>
                  <h3 className="mt-4 font-semibold text-ink">{w.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{w.text}</p>
                </article>
              ))}
            </div>
          </div>
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
                Ouvrez la boutique de démonstration « {SITE_CONFIG.demoShop.name} », envoyez un document et voyez le prix se calculer. C'est exactement la page que vos clients obtiennent en scannant votre QR code.
              </p>
              <ul className="mt-6 space-y-2 text-sm text-slate-200">
                {["Aucune installation, fonctionne sur tous les smartphones", "Prix affiché avant validation", "Code de suivi remis au client"].map((t) => (
                  <li key={t} className="flex gap-2"><CheckCircle2 className="size-4 shrink-0 text-[#08BBD0]" /> {t}</li>
                ))}
              </ul>
              <Link to={`/s/${SITE_CONFIG.demoShop.slug}`} className={cn(buttonVariants({ size: "lg" }), "mt-8 h-12 bg-[#08BBD0] px-6 text-[#042F2E] hover:bg-[#069EAF]")} data-testid="qr-demo-open">
                <Smartphone className="size-4" /> Ouvrir la boutique de démonstration
              </Link>
            </div>
            <img src="https://images.unsplash.com/photo-1600147131759-880e94a6185f?crop=entropy&cs=srgb&fm=jpg&w=1100&q=75" alt="Client scannant un QR code avec son smartphone"
              loading="lazy" width={1100} height={733} className="aspect-[3/2] w-full rounded-2xl object-cover" />
          </div>
        </section>

        {/* WINDOWS AGENT */}
        <AgentSection />

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
                  <Link to="/inscription" onClick={() => track("Signup CTA", { from: `plan-${p.code}` })} className={cn(buttonVariants({ variant: i === 1 ? "default" : "outline" }), "mt-6 w-full")} data-testid={`plan-${p.code}-cta`}>Commencer l'essai</Link>
                </article>
              ))}
              {plans.isPending && <p className="text-sm text-slate-500">Chargement des offres…</p>}
            </div>
            {/* Note: « Le plus choisi » is a presentation highlight, not a usage statistic. */}
            <p className="mt-8 text-sm text-slate-600" data-testid="pricing-payment-note">
              Le paiement en ligne pour vos clients arrive bientôt. Aujourd'hui, l'encaissement se fait au comptoir.
            </p>
            <Link to="/roadmap" className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-azure hover:underline" data-testid="pricing-roadmap-link">Voir la feuille de route <ArrowRight className="size-3.5" /></Link>
          </div>
        </section>

        {/* SOCIAL PROOF — only rendered with real data from config/site.ts */}
        <SocialProof />

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

        {/* DEMO */}
        <section id="demo" className="scroll-mt-20 bg-white">
          <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 sm:px-8 lg:grid-cols-[1fr_1.3fr]">
            <div>
              <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Démo</p>
              <h2 className="mt-3 font-heading text-3xl font-bold text-ink">Réserver une démo de 15 min</h2>
              <p className="mt-4 leading-relaxed text-slate-600">Laissez-nous vos coordonnées : nous vous recontactons pour vous montrer PrintDrop sur un cas concret de votre boutique.</p>
              <DemoContacts />
            </div>
            <DemoForm />
          </div>
        </section>

        {/* CTA */}
        <section className="bg-azure">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-6 px-5 py-14 sm:px-8">
            <h2 className="max-w-xl font-heading text-3xl font-bold text-white">Modernisez votre comptoir dès aujourd'hui.</h2>
            <div className="flex flex-wrap gap-3">
              <Link to="/inscription" onClick={() => track("Signup CTA", { from: "footer-cta" })} className={cn(buttonVariants({ size: "lg" }), "h-12 bg-white px-6 text-azure hover:bg-slate-100")} data-testid="cta-trial">Essai gratuit 14 jours</Link>
              <a href="#demo" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "h-12 border-white/60 bg-transparent px-6 text-white hover:bg-white/10 hover:text-white")} data-testid="cta-demo">Réserver une démo de 15 min</a>
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

function AgentSection() {
  const v = useQuery({ queryKey: ["public-agent-version"], queryFn: () => apiGet<PublicAgentVersionOut>("/public/agent-version"), staleTime: 300_000 });
  const version = v.isError ? null : v.data?.version;
  return (
    <section id="impression-automatique" className="mx-auto max-w-7xl scroll-mt-20 px-5 py-20 sm:px-8">
      <div className="grid gap-12 lg:grid-cols-[1fr_1.1fr] lg:items-center">
        <div>
          <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Impression automatique</p>
          <h2 className="mt-3 font-heading text-3xl font-bold text-ink sm:text-4xl">L'agent Windows envoie les commandes vers vos imprimantes.</h2>
          <p className="mt-4 leading-relaxed text-slate-600">
            Installé sur le PC de la boutique, l'agent PrintDrop reçoit les commandes que vous lancez depuis le tableau de bord et les imprime directement
            sur vos imprimantes, au bon format et au bon nombre d'exemplaires. La commande passe en « Prête » une fois l'impression terminée.
          </p>
          <ol className="mt-8 space-y-5">
            {AGENT_STEPS.map((s, i) => (
              <li key={s.title} className="flex gap-4" data-testid={`agent-step-${i + 1}`}>
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-azure font-mono text-sm font-semibold text-white">{i + 1}</span>
                <div><h3 className="font-semibold text-ink">{s.title}</h3><p className="mt-1 text-sm leading-relaxed text-slate-600">{s.text}</p></div>
              </li>
            ))}
          </ol>
          <p className="mt-8 inline-flex rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800" data-testid="agent-version-note">
            {version ? `Version ${version}` : "Version en cours"} – en amélioration continue
          </p>
        </div>
        <AgentScreenshot />
      </div>
    </section>
  );
}

/** Replace by setting SITE_CONFIG.agentScreenshot to an image path. */
function AgentScreenshot() {
  const src: string = SITE_CONFIG.agentScreenshot;
  if (src) return <img src={src} alt="Fenêtre de l'agent Windows PrintDrop" loading="lazy" className="w-full rounded-2xl border shadow-[0_24px_48px_-28px_rgba(9,38,92,0.35)]" data-testid="agent-screenshot" />;
  return (
    <div className="grid aspect-[4/3] w-full place-items-center rounded-2xl border-2 border-dashed border-slate-300 bg-[#F4F7FC] text-center text-sm text-slate-500" data-testid="agent-screenshot-placeholder">
      <div><ImageIcon className="mx-auto size-8 text-slate-400" aria-hidden="true" /><p className="mt-2">Capture d'écran de l'agent Windows</p><p className="text-xs">(à remplacer)</p></div>
    </div>
  );
}

function SocialProof() {
  const { testimonials, shops } = SITE_CONFIG;
  if (testimonials.length === 0 && shops.length === 0) return null;
  return (
    <section className="mx-auto max-w-7xl px-5 py-20 sm:px-8" data-testid="social-proof">
      <h2 className="font-heading text-3xl font-bold text-ink">Ils nous font confiance</h2>
      {shops.length > 0 && (
        <ul className="mt-8 flex flex-wrap items-center gap-x-10 gap-y-4" data-testid="social-proof-shops">
          {shops.map((sh) => (
            <li key={sh.name} className="text-sm font-semibold text-slate-600">
              {sh.logo ? <img src={sh.logo} alt={sh.name} className="h-10 w-auto" loading="lazy" /> : <>{sh.name}{sh.city ? ` · ${sh.city}` : ""}</>}
            </li>
          ))}
        </ul>
      )}
      {testimonials.length > 0 && (
        <div className="mt-10 grid gap-5 md:grid-cols-2" data-testid="social-proof-testimonials">
          {testimonials.map((t) => (
            <figure key={t.author + t.shop} className="rounded-xl border bg-white p-6">
              <Quote className="size-6 text-azure" aria-hidden="true" />
              <blockquote className="mt-3 leading-relaxed text-slate-700">« {t.quote} »</blockquote>
              <figcaption className="mt-4 text-sm"><span className="font-semibold text-ink">{t.author}</span> — {t.role}, {t.shop}{t.city ? ` (${t.city})` : ""}</figcaption>
            </figure>
          ))}
        </div>
      )}
    </section>
  );
}

function DemoContacts() {
  const whatsappNumber: string = SITE_CONFIG.contact.whatsappNumber;
  const phone: string = SITE_CONFIG.contact.phone;
  if (!whatsappNumber && !phone) return null;
  return (
    <div className="mt-8 flex flex-wrap gap-3">
      {whatsappNumber && (
        <a href={`https://wa.me/${whatsappNumber}`} target="_blank" rel="noopener noreferrer" onClick={() => track("WhatsApp Click")}
          className={cn(buttonVariants({ variant: "outline" }), "h-11 border-emerald-300 text-emerald-800 hover:bg-emerald-50")} data-testid="demo-whatsapp-button">
          <MessageCircle className="size-4" /> WhatsApp
        </a>
      )}
      {phone && (
        <a href={`tel:${phone.replace(/\s/g, "")}`} className={cn(buttonVariants({ variant: "outline" }), "h-11")} data-testid="demo-phone-link">
          <Phone className="size-4" /> {phone}
        </a>
      )}
    </div>
  );
}

const EMPTY_DEMO: ContactIn = { kind: "demo", name: "", business: "", city: "", email: "", phone: "", subject: "", message: "", website: "" };

function DemoForm() {
  const [form, setForm] = useState<ContactIn>(EMPTY_DEMO);
  const send = useMutation({
    mutationFn: () => apiPost<ContactOut>("/public/contact", form),
    onSuccess: () => track("Demo Request"),
  });
  const set = (k: keyof ContactIn) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = (e: FormEvent) => { e.preventDefault(); send.mutate(); };

  if (send.data) {
    return (
      <div className="rounded-xl border bg-background p-6" data-testid="demo-success" role="status">
        <CheckCircle2 className="size-7 text-emerald-600" />
        <p className="mt-3 font-semibold text-ink">Merci, votre demande de démo a bien été enregistrée.</p>
        <p className="mt-1 text-sm text-slate-600">Nous vous recontactons rapidement par e-mail{form.phone ? " ou par téléphone" : ""} pour fixer un créneau de 15 minutes.</p>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="grid gap-4 rounded-xl border bg-background p-6 sm:grid-cols-2" data-testid="demo-form">
      <div className="space-y-1.5"><Label htmlFor="d-name">Nom *</Label><Input id="d-name" required minLength={2} maxLength={100} value={form.name} onChange={set("name")} autoComplete="name" data-testid="demo-name" /></div>
      <div className="space-y-1.5"><Label htmlFor="d-business">Nom de la boutique *</Label><Input id="d-business" required minLength={2} maxLength={120} value={form.business} onChange={set("business")} autoComplete="organization" data-testid="demo-business" /></div>
      <div className="space-y-1.5"><Label htmlFor="d-city">Ville *</Label><Input id="d-city" required minLength={2} maxLength={80} value={form.city} onChange={set("city")} autoComplete="address-level2" data-testid="demo-city" /></div>
      <div className="space-y-1.5"><Label htmlFor="d-email">E-mail *</Label><Input id="d-email" type="email" required value={form.email} onChange={set("email")} autoComplete="email" data-testid="demo-email" /></div>
      <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="d-phone">Téléphone / WhatsApp (facultatif)</Label><Input id="d-phone" type="tel" maxLength={30} value={form.phone} onChange={set("phone")} autoComplete="tel" data-testid="demo-phone" /></div>
      <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="d-message">Message (facultatif)</Label><Textarea id="d-message" maxLength={4000} rows={4} value={form.message} onChange={set("message")} placeholder="Ex : nombre d'imprimantes, horaires, questions…" data-testid="demo-message" /></div>
      <input type="text" name="website" value={form.website} onChange={set("website")} tabIndex={-1} autoComplete="off" className="hidden" aria-hidden="true" />
      {send.isError && <p className="text-sm text-rose-700 sm:col-span-2" role="alert" data-testid="demo-error">{errorMessage(send.error)}</p>}
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <Button type="submit" disabled={send.isPending} className="h-11 px-6" data-testid="demo-submit">{send.isPending ? "Envoi…" : "Demander ma démo"}</Button>
        <p className="text-xs text-slate-500">Vos données servent uniquement à organiser la démo.</p>
      </div>
    </form>
  );
}
