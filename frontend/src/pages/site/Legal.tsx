import type { ReactNode } from "react";
import { Navigate, useParams } from "react-router-dom";
import { TriangleAlert } from "lucide-react";
import { SiteFooter, SiteHeader } from "@/components/site/SiteChrome";
import { COMPANY, COMPANY_PENDING, LEGAL_LINKS, formatSiren, type LegalSlug } from "@/lib/brand";

/** Placeholder for legally required information not supplied by the owner — never invented. */
function Todo({ children }: { children: ReactNode }) {
  return <mark className="rounded bg-amber-100 px-1.5 py-0.5 font-medium text-amber-900" data-testid="legal-todo">[À compléter : {children}]</mark>;
}

const Address = () => <>{COMPANY.street}, {COMPANY.postalCode} {COMPANY.city}, {COMPANY.country}</>;

function MentionsLegales() {
  return (
    <>
      <h2>Éditeur du site</h2>
      <p>
        <strong>{COMPANY.name}</strong><br />
        Siège : <Address /><br />
        Immatriculation : {COMPANY_PENDING.rcsCity ? `R.C.S. ${COMPANY_PENDING.rcsCity} ${formatSiren(COMPANY.siren)}` : <Todo>RCS et greffe d'immatriculation</Todo>}<br />
        Contact : {COMPANY_PENDING.publicEmail ?? "formulaire de la page Contact"}{COMPANY_PENDING.phone ? ` — ${COMPANY_PENDING.phone}` : ""}
      </p>
      <h2>Propriété intellectuelle</h2>
      <p>La marque, le logo PrintDrop et les contenus du site sont protégés. Toute reproduction sans autorisation est interdite.</p>
    </>
  );
}

function Confidentialite() {
  return (
    <>
      <p>Cette politique décrit les données traitées par l'application PrintDrop telle qu'elle fonctionne aujourd'hui.</p>
      <h2>Responsables du traitement</h2>
      <p>
        Pour les comptes des boutiques et le site : {COMPANY.name} (<Address />). Pour les commandes passées dans une boutique, la boutique
        concernée détermine l'usage des données de ses clients ; PrintDrop agit alors pour son compte.
      </p>
      <h2>Données traitées</h2>
      <ul>
        <li><strong>Comptes professionnels</strong> (propriétaires, employés) : nom, e-mail, mot de passe (stocké chiffré de façon irréversible), rôle, journal des actions.</li>
        <li><strong>Clients des boutiques</strong> : nom, téléphone, e-mail facultatif, documents envoyés, options d'impression, montant et statut de paiement. Aucun compte client n'est créé.</li>
        <li><strong>Formulaire de contact</strong> : nom, établissement, e-mail, sujet, message, adresse IP (limitation des abus).</li>
        <li><strong>Agent Windows</strong> : nom du poste, liste et état des imprimantes, statuts d'impression. Le contenu des documents n'est pas journalisé.</li>
      </ul>
      <h2>Finalités</h2>
      <p>Gérer les commandes d'impression, prévenir le client quand sa commande est prête (s'il l'a accepté), facturer l'abonnement des boutiques, répondre aux demandes de contact, sécuriser le service.</p>
      <h2>Durées de conservation</h2>
      <ul>
        <li><strong>Documents envoyés par les clients</strong> : {COMPANY_PENDING.documentRetention}. Ils ne peuvent pas être téléchargés par la boutique : ils sont uniquement transmis à l'imprimante, et seules les pages choisies par le client sont envoyées.</li>
        <li><strong>Nom, téléphone et e-mail du client</strong> : effacés en même temps que les documents. La commande reste conservée de façon anonyme (montant, date, statut) pour la comptabilité de la boutique.</li>
        <li><strong>Fichiers envoyés sans commande validée</strong> : supprimés au bout de 24 heures.</li>
        <li><strong>Codes d'appairage de l'agent</strong> : 24 heures maximum.</li>
        <li><strong>Messages du formulaire de contact</strong> : <Todo>durée de conservation</Todo>.</li>
      </ul>
      <p>La suppression est automatique (vérification toutes les heures).</p>
      <h2>Vos droits</h2>
      <p>Vous pouvez demander l'accès, la rectification, l'effacement ou la limitation de vos données, et vous opposer à leur traitement, via la page Contact. Vous pouvez aussi saisir la CNIL (cnil.fr).</p>
      <h2>Sécurité</h2>
      <p>Connexion par cookie sécurisé, isolation des données de chaque boutique, accès aux documents par lien signé à durée limitée.</p>
    </>
  );
}

function Cgu() {
  return (
    <>
      <p><Todo>conditions générales complètes à rédiger et faire valider par un professionnel du droit avant publication</Todo></p>
      <h2>Objet</h2>
      <p>PrintDrop fournit aux professionnels de l'impression un logiciel en ligne de gestion des commandes et un portail de dépôt de documents pour leurs clients.</p>
      <h2>Essai et abonnement</h2>
      <p>Essai gratuit de 14 jours, puis abonnement mensuel ou annuel (Starter, Professional, Business) payable à chaque échéance, sans renouvellement automatique.</p>
      <h2>Responsabilités</h2>
      <p>La boutique reste responsable des documents qu'elle imprime, de ses tarifs, de l'encaissement et de son matériel. L'impression directe dépend du PC Windows, des pilotes et des imprimantes de la boutique.</p>
      <h2>Clients des boutiques</h2>
      <p>Le client s'engage à n'envoyer que des documents qu'il a le droit de faire imprimer. Le prix affiché est calculé selon les tarifs de la boutique ; le paiement s'effectue au comptoir.</p>
      <p>Points à compléter : <Todo>résiliation, suspension, limitation de responsabilité, droit applicable et juridiction, médiation</Todo></p>
    </>
  );
}

function Cookies() {
  return (
    <>
      <p>PrintDrop n'utilise <strong>aucun cookie publicitaire ni de mesure d'audience</strong>.</p>
      <h2>Cookie utilisé</h2>
      <ul>
        <li><strong>Cookie de session</strong> (comptes professionnels uniquement) : il vous maintient connecté. Strictement nécessaire, il est sécurisé (httpOnly) et expire automatiquement.</li>
      </ul>
      <p>Les cookies strictement nécessaires ne requièrent pas de consentement. Les clients qui déposent des documents ne reçoivent aucun cookie de suivi.</p>
      <p>Si des outils de mesure d'audience sont ajoutés plus tard, une demande de consentement sera mise en place avant leur activation.</p>
    </>
  );
}

const DOCS: Record<LegalSlug, () => ReactNode> = {
  "mentions-legales": MentionsLegales, confidentialite: Confidentialite, cgu: Cgu, cookies: Cookies,
};

export default function LegalPage({ slug: forced }: { slug?: LegalSlug }) {
  const params = useParams();
  const slug = (forced ?? params.doc) as LegalSlug;
  const meta = LEGAL_LINKS.find((l) => l.slug === slug);
  if (!meta) return <Navigate to="/" replace />;
  const Body = DOCS[slug];
  return (
    <div className="min-h-screen bg-background">
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-5 py-14 sm:px-8">
        <h1 className="font-heading text-4xl font-bold text-ink" data-testid="legal-title">{meta.label}</h1>
        <div className="mt-6 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" role="note" data-testid="legal-draft-notice">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <p><strong>Version provisoire, à compléter.</strong> Les mentions surlignées doivent être fournies ou validées (idéalement par un professionnel du droit) avant publication. La conformité au RGPD n'a pas encore été vérifiée.</p>
        </div>
        <article className="prose-pd mt-8 space-y-4 leading-relaxed text-slate-700 [&_h2]:mt-8 [&_h2]:font-heading [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-ink [&_li]:ml-5 [&_li]:list-disc [&_ul]:space-y-1.5" data-testid="legal-body">
          <Body />
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
