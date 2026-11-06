import { Link } from "react-router-dom";
import { ArrowRight, Calculator, FileUp, QrCode, ShieldCheck, Store, Printer, CheckCircle2, Clock } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Logo } from "@/components/Logo";
import { cn } from "@/lib/utils";

const STEPS = [
  { icon: QrCode, title: "Scannez", text: "Le client scanne le QR code affiché au comptoir de votre boutique." },
  { icon: FileUp, title: "Déposez", text: "Il envoie ses PDF ou photos depuis son téléphone, en toute confidentialité." },
  { icon: Calculator, title: "Validez", text: "Format, couleur, recto-verso, exemplaires : le prix est calculé par le serveur." },
  { icon: Printer, title: "Récupérez", text: "Vous imprimez, encaissez au comptoir et le client suit sa commande en direct." },
];

const ROADMAP: { label: string; done: boolean }[] = [
  { label: "Comptes, entreprises, boutiques & rôles", done: true },
  { label: "Isolation stricte des données par entreprise", done: true },
  { label: "Portail client QR, dépôt de documents privé", done: true },
  { label: "Tarifs configurables & calcul serveur", done: true },
  { label: "Gestion des commandes & encaissement comptoir", done: true },
  { label: "Super-administration de la plateforme", done: true },
  { label: "Paiement en ligne avec webhooks vérifiés", done: false },
  { label: "Agent local Windows (impression automatique, v0.1)", done: true },
  { label: "Notifications e-mail / SMS « commande prête »", done: true },
  { label: "Caisse, statistiques avancées & abonnements", done: false },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-white/10 bg-ink/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
          <Logo inverse />
          <nav className="flex items-center gap-2">
            <Link to="/suivi" className="hidden rounded-lg px-3 py-2 text-sm text-slate-300 transition-colors hover:text-white sm:block" data-testid="nav-track-link">
              Suivre une commande
            </Link>
            <Link to="/login" className="rounded-lg px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-white/10" data-testid="nav-login-link">
              Connexion
            </Link>
            <Link to="/inscription" className={cn(buttonVariants({ size: "sm" }), "h-9 px-4")} data-testid="nav-register-link">
              Essai gratuit
            </Link>
          </nav>
        </div>
      </header>

      <section className="relative overflow-hidden bg-ink text-white">
        <div className="pointer-events-none absolute -top-40 right-0 size-[640px] rounded-full bg-azure/25 blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 left-1/3 size-[380px] rounded-full bg-teal-pd/20 blur-3xl" />
        <div className="relative mx-auto grid max-w-7xl gap-14 px-5 py-20 sm:px-8 lg:grid-cols-[1.15fr_1fr] lg:py-28">
          <div className="animate-rise">
            <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold tracking-[0.15em] text-sky-300 uppercase">
              <Store className="size-3.5" /> Cybercafés · Reprographies · Copy-centers
            </p>
            <h1 className="mt-6 text-5xl leading-[1.05] font-bold sm:text-6xl">
              L'impression par QR code,<br /><span className="text-sky-400">sans clé USB ni e-mail.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg text-slate-300">
              PrintDrop permet à vos clients d'envoyer leurs documents depuis leur téléphone, de voir le prix exact et de suivre leur commande.
              Vous gérez commandes, tarifs, équipe et encaissements depuis un seul tableau de bord.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link to="/inscription" className={cn(buttonVariants({ size: "lg" }), "h-12 px-6 text-base")} data-testid="hero-register-button">
                Créer mon espace boutique <ArrowRight className="size-4" />
              </Link>
              <Link to="/s/cybercafe-bastille" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "h-12 border-white/20 bg-white/5 px-6 text-base text-white hover:bg-white/10 hover:text-white")} data-testid="hero-demo-portal-button">
                Essayer le portail client
              </Link>
            </div>
          </div>

          <div className="relative animate-rise [animation-delay:120ms]">
            <div className="absolute -inset-4 rotate-2 rounded-3xl bg-white/5" />
            <div className="relative rounded-3xl border border-white/10 bg-white p-6 text-ink shadow-2xl">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold tracking-[0.15em] text-slate-500 uppercase">Portail client</p>
                  <p className="font-heading text-xl font-bold">CyberCafé Bastille</p>
                </div>
                <QrCode className="size-10 text-azure" />
              </div>
              <div className="dot-grid mt-5 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-5">
                <div className="flex items-center gap-3 rounded-xl bg-white p-3 shadow-sm">
                  <span className="grid size-10 place-items-center rounded-lg bg-rose-50 text-xs font-bold text-rose-600">PDF</span>
                  <div className="flex-1">
                    <p className="text-sm font-semibold">memoire-final.pdf</p>
                    <p className="text-xs text-slate-500">24 pages · A4 · N&B · Recto-verso</p>
                  </div>
                  <span className="font-mono text-sm font-semibold">3,24 €</span>
                </div>
                <div className="mt-3 flex items-center gap-3 rounded-xl bg-white p-3 shadow-sm">
                  <span className="grid size-10 place-items-center rounded-lg bg-sky-50 text-xs font-bold text-sky-600">JPG</span>
                  <div className="flex-1">
                    <p className="text-sm font-semibold">photo-identite.jpg</p>
                    <p className="text-xs text-slate-500">1 page · A4 · Couleur · ×2</p>
                  </div>
                  <span className="font-mono text-sm font-semibold">1,20 €</span>
                </div>
              </div>
              <div className="mt-5 flex items-center justify-between rounded-2xl bg-ink px-5 py-4 text-white">
                <span className="text-sm text-slate-300">Total calculé par le serveur</span>
                <span className="font-mono text-2xl font-bold">4,44 €</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
        <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Comment ça marche</p>
        <h2 className="mt-3 max-w-2xl text-4xl font-bold text-ink">Quatre étapes, du téléphone du client à votre imprimante.</h2>
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <div key={s.title} className={cn("rounded-2xl border bg-card p-6 transition-shadow hover:shadow-lg", i % 2 === 1 && "lg:translate-y-6")} data-testid={`how-step-${i + 1}`}>
              <span className="font-mono text-xs text-slate-400">0{i + 1}</span>
              <s.icon className="mt-4 size-7 text-azure" />
              <h3 className="mt-4 text-xl font-semibold text-ink">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-y bg-white">
        <div className="mx-auto grid max-w-7xl gap-12 px-5 py-20 sm:px-8 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <ShieldCheck className="size-9 text-teal-pd" />
            <h2 className="mt-4 text-3xl font-bold text-ink">Transparence sur l'avancement du produit</h2>
            <p className="mt-4 text-muted-foreground">
              PrintDrop est construit par étapes. Voici ce qui est réellement disponible aujourd'hui et ce qui arrive.
              Aucun paiement n'est simulé : l'encaissement se fait au comptoir tant que le paiement en ligne n'est pas livré.
            </p>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2" data-testid="roadmap-list">
            {ROADMAP.map((r) => (
              <li key={r.label} className="flex items-start gap-3 rounded-xl border bg-background p-4 text-sm">
                {r.done ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" /> : <Clock className="mt-0.5 size-4 shrink-0 text-amber-600" />}
                <span>
                  <span className="font-medium text-ink">{r.label}</span>
                  <span className={cn("ml-2 text-xs", r.done ? "text-emerald-700" : "text-amber-700")}>{r.done ? "Disponible" : "À venir"}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <footer className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-10 text-sm text-muted-foreground sm:px-8">
        <Logo />
        <p>© {new Date().getFullYear()} PrintDrop — Plateforme SaaS pour professionnels de l'impression.</p>
      </footer>
    </div>
  );
}
