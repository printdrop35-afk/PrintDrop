import { useEffect } from "react";

const SITE = "https://printdrop.fr";

type JsonLd = Record<string, unknown> | Record<string, unknown>[];

interface SeoOptions {
  title: string;
  description: string;
  path: string; // absolute path beginning with "/"
  /** robots directives. Defaults to "index,follow". Use "noindex,nofollow" for private pages. */
  robots?: string;
  /** Override OG type (default "website"). */
  ogType?: string;
  /** Optional OG image override (absolute URL or root-relative path). */
  image?: string;
  /** Optional JSON-LD blocks to inject. */
  jsonLd?: JsonLd;
}

function upsertMeta(attr: "name" | "property", key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel: string, href: string) {
  let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

function upsertJsonLd(id: string, data: JsonLd) {
  let el = document.getElementById(id) as HTMLScriptElement | null;
  if (!el) {
    el = document.createElement("script");
    el.type = "application/ld+json";
    el.id = id;
    document.head.appendChild(el);
  }
  el.textContent = JSON.stringify(data);
}

function removeJsonLd(id: string) {
  document.getElementById(id)?.remove();
}

/** Absolute URL for a root-relative path. */
export function absUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return path.startsWith("/") ? `${SITE}${path}` : `${SITE}/${path}`;
}

/**
 * Per-route SEO. Call once from a page component.
 * Sets <title>, meta description, canonical link, robots meta,
 * Open Graph, Twitter card, and optional JSON-LD blocks.
 */
export function useSeo(opts: SeoOptions) {
  const canonical = absUrl(opts.path);
  const image = absUrl(opts.image ?? "/brand/printdrop-og.png");
  const robots = opts.robots ?? "index,follow";

  useEffect(() => {
    document.title = opts.title;
    upsertMeta("name", "description", opts.description);
    upsertMeta("name", "robots", robots);
    upsertLink("canonical", canonical);

    upsertMeta("property", "og:type", opts.ogType ?? "website");
    upsertMeta("property", "og:title", opts.title);
    upsertMeta("property", "og:description", opts.description);
    upsertMeta("property", "og:url", canonical);
    upsertMeta("property", "og:image", image);
    upsertMeta("property", "og:site_name", "PrintDrop");
    upsertMeta("property", "og:locale", "fr_FR");

    upsertMeta("name", "twitter:card", "summary_large_image");
    upsertMeta("name", "twitter:title", opts.title);
    upsertMeta("name", "twitter:description", opts.description);
    upsertMeta("name", "twitter:image", image);

    if (opts.jsonLd) {
      upsertJsonLd("route-jsonld", opts.jsonLd);
    } else {
      removeJsonLd("route-jsonld");
    }

    return () => {
      // Leave meta in place; next route overwrites via upsert.
    };
  }, [opts.title, opts.description, canonical, image, robots, opts.ogType, opts.jsonLd]);
}

/** Mark a page as non-indexable. Shorthand for useSeo({ robots: "noindex,nofollow" }). */
export function useNoIndex(path: string, title: string) {
  useSeo({
    title,
    description: "Page privée non destinée à l'indexation par les moteurs de recherche.",
    path,
    robots: "noindex,nofollow",
  });
}

/** Static organization + website JSON-LD shared across the site (in index.html). */
export const ORG_JSONLD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "PrintDrop",
  url: SITE,
  logo: absUrl("/brand/printdrop-logo-light.png"),
  description:
    "Logiciel de gestion pour cybercafé et reprographie : réception de documents par QR code, gestion des commandes d'impression et de la file d'attente.",
  address: {
    "@type": "PostalAddress",
    streetAddress: "2 Rue du Couesnon",
    postalCode: "35230",
    addressLocality: "Orgères",
    addressCountry: "FR",
  },
  sameAs: [] as string[],
};

export const WEBSITE_JSONLD = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "PrintDrop",
  url: SITE,
  inLanguage: "fr-FR",
  description:
    "Logiciel de gestion pour cybercafé et reprographie : impression par QR code, gestion des commandes et des documents à imprimer.",
};

export function softwareAppJsonLd(path: string): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "PrintDrop",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web, Windows 10, Windows 11",
    url: absUrl(path),
    inLanguage: "fr-FR",
    description:
      "Logiciel de gestion pour cybercafé et reprographie : réception de documents par QR code, gestion des commandes d'impression, tarifs calculés par le serveur et impression directe via l'agent Windows.",
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "EUR",
      description: "Essai gratuit 14 jours, sans carte bancaire.",
    },
  };
}

export function faqJsonLd(items: { q: string; a: string }[]): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((it) => ({
      "@type": "Question",
      name: it.q,
      acceptedAnswer: { "@type": "Answer", text: it.a },
    })),
  };
}

export function breadcrumbJsonLd(crumbs: { name: string; path: string }[]): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: crumbs.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: c.name,
      item: absUrl(c.path),
    })),
  };
}
