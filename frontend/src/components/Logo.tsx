import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";

/** Official PrintDrop logo (centralised assets in /public/brand, see src/lib/brand.ts). Never stretched: height-only sizing. */
export function Logo({ inverse = false, className, variant = "full", to = "/" }: { inverse?: boolean; className?: string; variant?: "full" | "icon"; to?: string }) {
  const src = variant === "icon" ? (inverse ? BRAND.logo.iconDark : BRAND.logo.icon) : inverse ? BRAND.logo.dark : BRAND.logo.light;
  return (
    <Link to={to} data-testid="logo-link" className={cn("inline-flex items-center", className)} aria-label="PrintDrop — accueil">
      <img src={src} alt="PrintDrop" width={variant === "icon" ? 36 : 180} height={36} className={cn("w-auto select-none", variant === "icon" ? "h-9" : "h-9 sm:h-10")} draggable={false} />
    </Link>
  );
}
