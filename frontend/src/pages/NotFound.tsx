import { Link } from "react-router-dom";
import { ArrowRight, Home } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { SiteFooter, SiteHeader } from "@/components/site/SiteChrome";
import { useSeo } from "@/lib/seo";
import { cn } from "@/lib/utils";

export default function NotFound() {
  useSeo({
    title: "Page introuvable (404) — PrintDrop",
    description: "La page que vous recherchez n'existe pas ou a été déplacée. Retournez à l'accueil de PrintDrop, le logiciel de gestion pour cybercafé et reprographie.",
    path: "/404",
    robots: "noindex, follow",
  });
  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main className="mx-auto flex max-w-3xl flex-col items-center px-5 py-24 text-center sm:px-8">
        <p className="font-mono text-6xl font-bold text-azure" data-testid="notfound-code">404</p>
        <h1 className="mt-4 font-heading text-3xl font-bold text-ink" data-testid="notfound-title">Cette page n'existe pas</h1>
        <p className="mt-4 max-w-xl leading-relaxed text-slate-600" data-testid="notfound-text">
          La page que vous cherchez a peut-être été déplacée ou supprimée. PrintDrop est le logiciel de gestion
          des commandes d'impression pour cybercafé, reprographie et magasin de photocopie.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link to="/" className={cn(buttonVariants(), "h-11 px-6")} data-testid="notfound-home">
            <Home className="size-4" /> Retour à l'accueil
          </Link>
          <Link to="/contact" className={cn(buttonVariants({ variant: "outline" }), "h-11 px-6")} data-testid="notfound-contact">
            Nous contacter <ArrowRight className="size-4" />
          </Link>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
