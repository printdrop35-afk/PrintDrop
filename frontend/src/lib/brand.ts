/** Single source of truth for PrintDrop branding & company information (used by logo, footer, legal pages, SEO). */

export const BRAND = {
  name: "PrintDrop",
  tagline: "Logiciel de gestion pour imprimeries et photocopies",
  colors: { navy: "#09265C", blue: "#0868EF", cyan: "#08BBD0", white: "#FFFFFF", light: "#F4F7FC", dark: "#071A3D" },
  logo: {
    light: "/brand/printdrop-logo.svg",
    dark: "/brand/printdrop-logo-dark.svg",
    mono: "/brand/printdrop-logo-mono.svg",
    icon: "/brand/printdrop-icon.svg",
    iconDark: "/brand/printdrop-icon-dark.svg",
    appIcon: "/brand/printdrop-app-icon.svg",
    pngLight: "/brand/printdrop-logo-light.png",
    pngDark: "/brand/printdrop-logo-dark.png",
  },
} as const;

/** Official information supplied by the owner. Do not edit without the owner's confirmation. */
export const COMPANY = {
  name: "PrintDrop",
  street: "2 Rue du Couesnon",
  postalCode: "35230",
  city: "OREGRES", // ⚠ spelling to be verified by the owner before publication (supplied as-is)
  country: "France",
  siren: "800646697",
} as const;

/** Legally required details NOT supplied yet — shown as « à compléter » on legal pages, never invented. */
export const COMPANY_PENDING = {
  legalForm: null as string | null, // forme juridique
  capital: null as string | null, // capital social
  rcsCity: null as string | null, // greffe d'immatriculation (RCS de …)
  vatNumber: null as string | null, // n° TVA intracommunautaire
  publicationDirector: null as string | null, // directeur de la publication
  publicEmail: null as string | null, // e-mail affiché publiquement
  phone: null as string | null,
  host: null as string | null, // hébergeur : nom, adresse, téléphone
  documentRetention: null as string | null, // durée de conservation des documents clients
} as const;

export const LEGAL_LINKS = [
  { slug: "mentions-legales", label: "Mentions légales" },
  { slug: "confidentialite", label: "Politique de confidentialité" },
  { slug: "cgu", label: "Conditions Générales d'Utilisation" },
  { slug: "cookies", label: "Gestion des cookies" },
] as const;

export type LegalSlug = (typeof LEGAL_LINKS)[number]["slug"];

export function formatSiren(s: string) {
  return s.replace(/^(\d{3})(\d{3})(\d{3})$/, "$1 $2 $3");
}
