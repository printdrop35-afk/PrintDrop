import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export function Logo({ inverse = false, className }: { inverse?: boolean; className?: string }) {
  return (
    <Link to="/" data-testid="logo-link" className={cn("inline-flex items-center gap-2.5", className)}>
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
