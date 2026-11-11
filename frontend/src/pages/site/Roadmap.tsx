import { Link } from "react-router-dom";
import { CheckCircle2, Clock } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { SiteFooter, SiteHeader } from "@/components/site/SiteChrome";
import { cn } from "@/lib/utils";

type Item = { label: string; status: "Disponible" | "À venir"; note?: string };

const ITEMS: Item[] = [
  { label: "Portail client par QR code (sans compte ni application)", status: "Disponible" },
  { label: "Envoi de PDF, Word (.docx) et images depuis le téléphone", status: "Disponible" },
  { label: "Prix calculé par le serveur selon vos tarifs (format, couleur, recto-verso, services, remises)", status: "Disponible" },
  { label: "Tableau de bord des commandes, code de suivi et page « Suivre une commande »", status: "Disponible" },
  { label: "Agent Windows : impression directe vers les imprimantes du PC", status: "Disponible", note: "à tester sur votre matériel pendant l'essai" },
  { label: "Photocopie et numérisation au comptoir via l'agent", status: "Disponible", note: "selon les pilotes de votre copieur / scanner" },
  { label: "Encaissement au comptoir (espèces / carte) et reçu de retrait", status: "Disponible" },
  { label: "Équipe avec permissions, multi-boutiques et journal d'audit", status: "Disponible" },
  { label: "Rapport quotidien par e-mail", status: "Disponible" },
  { label: "Message « commande prête » par e-mail", status: "Disponible" },
  { label: "Message « commande prête » par SMS", status: "À venir", note: "nécessite l'activation d'un fournisseur SMS" },
  { label: "Paiement en ligne par les clients finaux", status: "À venir" },
  { label: "Renouvellement automatique de l'abonnement", status: "À venir" },
  { label: "Installateur Windows signé (sans alerte de sécurité Windows)", status: "À venir" },
];

export default function Roadmap() {
  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
        <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">Feuille de route</p>
        <h1 className="mt-3 font-heading text-4xl font-bold text-ink" data-testid="roadmap-title">Transparence sur l'avancement du produit</h1>
        <p className="mt-4 leading-relaxed text-slate-600">
          Ce qui fonctionne aujourd'hui, et ce qui arrive. Nous ne présentons jamais comme disponible une fonctionnalité qui ne l'est pas.
        </p>
        <ul className="mt-10 divide-y rounded-xl border bg-white" data-testid="roadmap-list">
          {ITEMS.map((it, i) => (
            <li key={it.label} className="flex items-start gap-4 p-5" data-testid={`roadmap-item-${i}`}>
              {it.status === "Disponible" ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" /> : <Clock className="mt-0.5 size-5 shrink-0 text-amber-600" />}
              <div className="flex-1">
                <p className="font-medium text-ink">{it.label}</p>
                {it.note && <p className="mt-0.5 text-sm text-slate-500">{it.note}</p>}
              </div>
              <span className={cn("shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold", it.status === "Disponible" ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800")}
                data-testid={`roadmap-status-${i}`}>{it.status}</span>
            </li>
          ))}
        </ul>
        <div className="mt-10 flex flex-wrap gap-3">
          <Link to="/inscription" className={buttonVariants()} data-testid="roadmap-cta-trial">Essai gratuit 14 jours</Link>
          <Link to="/#demo" className={buttonVariants({ variant: "outline" })} data-testid="roadmap-cta-demo">Réserver une démo de 15 min</Link>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
