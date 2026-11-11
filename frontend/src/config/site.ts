/**
 * PrintDrop marketing site — ALL editable values in one place.
 * Anything left empty / null is simply hidden on the site (nothing is invented).
 * Plan prices are NOT here: they are read live from the plans you manage in Super-admin › Offres.
 */

export const SITE_CONFIG = {
  /** Contact shown in the « Réserver une démo » section. Leave "" to hide. */
  contact: {
    whatsappNumber: "", // [WHATSAPP_NUMBER] international format without + or spaces, e.g. "33612345678"
    phone: "", // [PHONE] displayed as written, e.g. "02 99 00 00 00"
  },

  /** Plausible analytics (privacy-friendly, no cookies). Leave "" to disable completely. */
  analytics: {
    plausibleDomain: "", // e.g. "printdrop.fr"
    plausibleScriptSrc: "https://plausible.io/js/script.tagged-events.js",
  },

  /** Social preview image (Open Graph) — replace the file in /public/brand or change this path. */
  ogImage: "/brand/printdrop-og.png",

  /** Screenshot of the Windows agent shown in « Impression automatique ». "" = placeholder box. */
  agentScreenshot: "",

  /** FAQ « Combien de temps pour démarrer ? » — [placeholder] until you confirm the real figure. */
  startupTime: "",

  /**
   * « Ils nous font confiance » — rendered ONLY when at least one real entry exists.
   * Never add fictitious testimonials, shops or figures.
   */
  testimonials: [] as { quote: string; author: string; role: string; shop: string; city?: string }[],
  shops: [] as { name: string; city?: string; logo?: string }[],

  /** Demo shop (clearly labelled as such on the site). */
  demoShop: { name: "CyberCafé Bastille", slug: "cybercafe-bastille" },
} as const;

export type Testimonial = (typeof SITE_CONFIG.testimonials)[number];
