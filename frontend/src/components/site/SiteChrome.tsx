import { useState } from "react";
import { Link } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Logo } from "@/components/Logo";
import { COMPANY, COMPANY_PENDING, formatSiren } from "@/lib/brand";
import { cn } from "@/lib/utils";
import { track } from "@/lib/analytics";

const NAV = [
  { href: "#fonctionnalites", label: "Fonctionnalités" },
  { href: "#comment-ca-marche", label: "Comment ça marche" },
  { href: "#demo-qr", label: "Démo QR" },
  { href: "#tarifs", label: "Tarifs" },
  { href: "#demo", label: "Démo" },
  { href: "#faq", label: "FAQ" },
];

export function SiteHeader({ home = false }: { home?: boolean }) {
  const [open, setOpen] = useState(false);
  const anchor = (h: string) => (home ? h : `/${h}`);
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-5 sm:px-8">
        <Logo />
        <nav className="hidden items-center gap-1 lg:flex" aria-label="Navigation principale">
          {NAV.map((n) => (
            <a key={n.href} href={anchor(n.href)} className="rounded-md px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:text-ink" data-testid={`site-nav-${n.href.slice(1)}`}>{n.label}</a>
          ))}
        </nav>
        <div className="hidden items-center gap-2 lg:flex">
          <Link to="/suivi" className="rounded-md px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:text-ink" data-testid="site-nav-track">Suivre une commande</Link>
          <Link to={"/connexion"} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-9")} data-testid="site-nav-login">Se connecter</Link>
          <Link to="/inscription" onClick={() => track("Signup CTA", { from: "nav" })} className={cn(buttonVariants({ size: "sm" }), "h-9 px-4")} data-testid="nav-cta-trial">Essai gratuit</Link>
        </div>
        <button type="button" className="grid size-10 place-items-center rounded-lg text-ink lg:hidden" onClick={() => setOpen((o) => !o)} aria-label="Menu" aria-expanded={open} data-testid="site-nav-toggle">
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>
      {open && (
        <nav className="border-t bg-white px-5 py-3 lg:hidden" data-testid="site-nav-mobile">
          {NAV.map((n) => (
            <a key={n.href} href={anchor(n.href)} onClick={() => setOpen(false)} className="block rounded-md px-2 py-2.5 text-sm font-medium text-ink">{n.label}</a>
          ))}
          <div className="mt-2 grid grid-cols-2 gap-2 border-t pt-3">
            <Link to={"/connexion"} className={buttonVariants({ variant: "outline" })}>Se connecter</Link>
            <Link to="/inscription" className={buttonVariants()}>Essai gratuit</Link>
          </div>
        </nav>
      )}
    </header>
  );
}

/** Discreet growth link shown at the bottom of the customer portal and tracking pages. */
export function PoweredBy({ className }: { className?: string }) {
  return (
    <p className={cn("px-4 py-6 text-center text-[11px] leading-relaxed text-slate-400", className)} data-testid="powered-by">
      Propulsé par PrintDrop – Vous gérez une boutique d'impression ?{" "}
      <Link to="/inscription?ref=portal" className="underline-offset-2 hover:text-slate-600 hover:underline" data-testid="powered-by-link">Essayez gratuitement</Link>
    </p>
  );
}

export function SiteFooter() {
  return (
    <footer className="bg-ink-2 text-slate-300" data-testid="site-footer">
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 sm:px-8 md:grid-cols-[1.3fr_1fr_1fr]">
        <div>
          <Logo inverse />
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-slate-400">
            Solution de gestion des commandes d'impression et de dépôt de documents par QR code pour imprimeries, reprographies et cybercafés.
          </p>
        </div>
        <div>
          <h2 className="text-xs font-semibold tracking-[0.15em] text-white uppercase">Société</h2>
          <address className="mt-4 text-sm leading-relaxed not-italic" data-testid="footer-company">
            <span className="font-semibold text-white">{COMPANY.name}</span><br />
            {COMPANY.street}<br />
            {COMPANY.postalCode} {COMPANY.city}<br />
            {COMPANY.country}<br />
            <span data-testid="footer-siren">R.C.S. {COMPANY_PENDING.rcsCity} {formatSiren(COMPANY.siren)}</span>
          </address>
        </div>
        <div>
          <h2 className="text-xs font-semibold tracking-[0.15em] text-white uppercase">Informations</h2>
          <ul className="mt-4 space-y-2 text-sm">
            <li><Link to={"/contact"} className="transition-colors hover:text-white" data-testid="footer-link-contact">Contact</Link></li>
            <li><Link to="/roadmap" className="transition-colors hover:text-white" data-testid="footer-link-roadmap">Voir la feuille de route</Link></li>
            <li><Link to="/mentions-legales" className="transition-colors hover:text-white" data-testid="footer-link-mentions">Mentions légales</Link></li>
            <li><Link to="/confidentialite" className="transition-colors hover:text-white" data-testid="footer-link-privacy">Politique de confidentialité</Link></li>
            <li><Link to="/cgu" className="transition-colors hover:text-white" data-testid="footer-link-cgu">CGU</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10">
        <p className="mx-auto max-w-7xl px-5 py-5 text-xs text-slate-500 sm:px-8">© {new Date().getFullYear()} {COMPANY.name}. Tous droits réservés.</p>
      </div>
    </footer>
  );
}
