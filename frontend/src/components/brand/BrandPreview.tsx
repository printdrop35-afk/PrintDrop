import { createContext, useContext, useLayoutEffect } from "react";
import { Link, Outlet } from "react-router-dom";
import { Eye } from "lucide-react";

const BrandCtx = createContext<"v1" | "v2">("v1");
export const useBrandVersion = () => useContext(BrandCtx);

/** Wraps the /apercu/* routes: applies the official v2 brand to the real pages (html.brand-v2) without touching the live ones. */
export function BrandPreview() {
  useLayoutEffect(() => {
    document.documentElement.classList.add("brand-v2");
    return () => document.documentElement.classList.remove("brand-v2");
  }, []);
  return (
    <BrandCtx.Provider value="v2">
      <div className="fixed bottom-3 left-3 z-[60] flex items-center gap-2 rounded-full bg-amber-400 px-3 py-1.5 text-xs font-semibold text-amber-950 shadow-lg" data-testid="preview-banner">
        <Eye className="size-3.5" /> Aperçu de la nouvelle identité — non publié
        <Link to="/apercu" className="underline" data-testid="preview-home-link">Accueil aperçu</Link>
      </div>
      <Outlet />
    </BrandCtx.Provider>
  );
}

/** Inside the preview, internal links stay inside /apercu where a preview page exists. */
export function usePreviewHref() {
  const v = useBrandVersion();
  return (path: string) => (v === "v2" ? `/apercu${path === "/" ? "" : path}` : path);
}
