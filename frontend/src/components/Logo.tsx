import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";
import { useBrandVersion } from "@/components/brand/BrandPreview";

type Variant = "full" | "icon";

export function Logo({ inverse = false, className, variant = "full", to = "/" }: { inverse?: boolean; className?: string; variant?: Variant; to?: string }) {
  const version = useBrandVersion();
  if (version === "v2") {
    const src = variant === "icon" ? (inverse ? BRAND.logo.iconDark : BRAND.logo.icon) : inverse ? BRAND.logo.dark : BRAND.logo.light;
    return (
      <Link to={to === "/" ? "/apercu" : to} data-testid="logo-link" className={cn("inline-flex items-center", className)} aria-label="PrintDrop — accueil">
        <img src={src} alt="PrintDrop" className={cn("w-auto select-none", variant === "icon" ? "h-9" : "h-9 sm:h-10")} draggable={false} />
      </Link>
    );
  }
  return (
    <Link to={to} data-testid="logo-link" className={cn("inline-flex items-center gap-2.5", className)}>
      <span className="relative grid size-9 place-items-center rounded-xl bg-azure text-white shadow-[0_6px_20px_-6px_rgba(37,99,235,0.7)]">
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M7 8V3h10v5" />
          <rect x="3" y="8" width="18" height="9" rx="2" />
          <path d="M7 14h10v7H7z" />
          <path d="M12 17v2" />
        </svg>
        <span className="absolute -right-1 -bottom-1 size-3 rounded-full border-2 border-white bg-teal-pd" />
      </span>
      <span className={cn("font-heading text-xl font-bold tracking-tight", inverse ? "text-white" : "text-ink")}>
        Print<span className="text-azure">Drop</span>
      </span>
    </Link>
  );
}
