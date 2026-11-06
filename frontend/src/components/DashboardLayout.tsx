import { useState } from "react";
import { Navigate, NavLink, Outlet } from "react-router-dom";
import { BarChart3, ClipboardList, Euro, LogOut, Menu, Printer, QrCode, ScrollText, Users, Store, Loader2 } from "lucide-react";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Logo } from "@/components/Logo";
import { useMe } from "@/hooks/useMe";
import { endSession } from "@/lib/session";
import { t, tk } from "@/i18n";
import { cn } from "@/lib/utils";
import type { MessageKey } from "@/i18n/fr";
import type { DashboardCtx } from "@/hooks/useDashboard";
import type { MeOut } from "@/lib/types";

const NAV: { to: string; key: MessageKey; icon: typeof ClipboardList; perm: string; testId: string }[] = [
  { to: "/dashboard", key: "nav.orders", icon: ClipboardList, perm: "orders:read", testId: "nav-orders" },
  { to: "/dashboard/rapports", key: "nav.reports", icon: BarChart3, perm: "reports:read", testId: "nav-reports" },
  { to: "/dashboard/tarifs", key: "nav.pricing", icon: Euro, perm: "shop:read", testId: "nav-pricing" },
  { to: "/dashboard/boutique", key: "nav.shop", icon: QrCode, perm: "shop:read", testId: "nav-shop" },
  { to: "/dashboard/imprimantes", key: "nav.devices", icon: Printer, perm: "devices:read", testId: "nav-devices" },
  { to: "/dashboard/equipe", key: "nav.team", icon: Users, perm: "staff:read", testId: "nav-team" },
  { to: "/dashboard/journal", key: "nav.audit", icon: ScrollText, perm: "audit:read", testId: "nav-audit" },
];

const SHOP_KEY = "pd_shop";

function SidebarBody({ me, shopId, setShopId, onNavigate }: { me: MeOut; shopId: string; setShopId: (id: string) => void; onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-sidebar p-5 text-sidebar-foreground">
      <Logo inverse />
      <div className="mt-8">
        <p className="mb-2 text-[11px] font-semibold tracking-[0.15em] text-slate-500 uppercase">{me.org?.name}</p>
        {me.shops.length > 1 ? (
          <Select value={shopId} onValueChange={(v: string) => setShopId(v)}>
            <SelectTrigger className="h-10 w-full border-sidebar-border bg-sidebar-accent text-white" data-testid="shop-selector">
              <SelectValue>{(v) => me.shops.find((s) => s.id === v)?.name ?? "Boutique"}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {me.shops.map((s) => <SelectItem key={s.id} value={s.id} data-testid={`shop-option-${s.slug}`}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
        ) : (
          <p className="flex items-center gap-2 rounded-lg bg-sidebar-accent px-3 py-2.5 text-sm font-medium text-white" data-testid="current-shop-name">
            <Store className="size-4 text-sky-400" /> {me.shops[0]?.name}
          </p>
        )}
      </div>
      <nav className="mt-6 flex flex-col gap-1">
        {NAV.filter((n) => me.permissions.includes(n.perm)).map((n) => (
          <NavLink key={n.to} to={n.to} end onClick={onNavigate} data-testid={n.testId}
            className={({ isActive }) => cn("flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
              isActive ? "bg-azure text-white shadow-[0_8px_20px_-10px_rgba(37,99,235,0.9)]" : "text-slate-300 hover:bg-sidebar-accent hover:text-white")}>
            <n.icon className="size-4" /> {t(n.key)}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto rounded-xl border border-sidebar-border p-3">
        <p className="truncate text-sm font-semibold text-white" data-testid="current-user-name">{me.user.name}</p>
        <p className="text-xs text-slate-400" data-testid="current-user-role">{me.role ? tk("role", me.role) : ""}</p>
        <button type="button" onClick={() => endSession("/login")} data-testid="logout-button"
          className="mt-3 inline-flex items-center gap-2 text-xs text-slate-400 transition-colors hover:text-white">
          <LogOut className="size-3.5" /> {t("nav.logout")}
        </button>
      </div>
    </div>
  );
}

export default function DashboardLayout() {
  const meQ = useMe();
  const [shopIdState, setShopIdState] = useState(() => localStorage.getItem(SHOP_KEY) ?? "");
  const [mobileOpen, setMobileOpen] = useState(false);

  if (meQ.isLoading) {
    return <div className="grid min-h-screen place-items-center"><Loader2 className="size-6 animate-spin text-azure" /></div>;
  }
  const me = meQ.isError ? undefined : meQ.data;
  if (!me) return <Navigate to="/login" replace />;
  if (!me.org) return <Navigate to={me.platform_role === "superadmin" ? "/superadmin" : "/login"} replace />;
  if (me.org.status !== "active") {
    return (
      <div className="grid min-h-screen place-items-center px-6 text-center" data-testid="org-suspended">
        <div>
          <h1 className="text-2xl font-bold text-ink">Organisation suspendue</h1>
          <p className="mt-2 text-muted-foreground">L'accès à {me.org.name} est temporairement suspendu. Contactez le support PrintDrop.</p>
          <button type="button" className="mt-6 text-sm font-semibold text-azure" onClick={() => endSession("/login")} data-testid="suspended-logout-button">Se déconnecter</button>
        </div>
      </div>
    );
  }

  const shop = me.shops.find((s) => s.id === shopIdState) ?? me.shops[0];
  const setShopId = (id: string) => { localStorage.setItem(SHOP_KEY, id); setShopIdState(id); };
  const ctx: DashboardCtx = { me, shop, can: (p) => me.permissions.includes(p) };

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="sticky top-0 hidden h-screen lg:block"><SidebarBody me={me} shopId={shop.id} setShopId={setShopId} /></aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-white/85 px-4 backdrop-blur-md lg:hidden">
          <button type="button" onClick={() => setMobileOpen(true)} aria-label="Menu" data-testid="mobile-menu-button" className="grid size-10 place-items-center rounded-lg hover:bg-muted">
            <Menu className="size-5" />
          </button>
          <span className="font-heading font-semibold text-ink">{shop.name}</span>
        </header>
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-[280px] border-none p-0" showCloseButton={false}>
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <SidebarBody me={me} shopId={shop.id} setShopId={setShopId} onNavigate={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>
        <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-8 sm:py-8">
          <Outlet context={ctx} />
        </main>
      </div>
    </div>
  );
}
