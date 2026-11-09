import type { ReactNode } from "react";
import { Logo } from "@/components/Logo";

const SHOP_IMG =
  "https://images.unsplash.com/photo-1753351050724-511764d227e3?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85&w=1200";

export function AuthShell({ title, subtitle, children, aside }: { title: string; subtitle: string; children: ReactNode; aside: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-ink p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <img src={SHOP_IMG} alt="" className="absolute inset-0 size-full object-cover opacity-25" />
        <div className="absolute inset-0 bg-gradient-to-br from-ink via-ink/90 to-ink-2/70" />
        <div className="relative"><Logo inverse /></div>
        <div className="relative max-w-md animate-rise">{aside}</div>
        <p className="relative text-xs text-slate-400">© {new Date().getFullYear()} PrintDrop</p>
      </aside>
      <main className="flex flex-col px-6 py-10 sm:px-12">
        <div className="lg:hidden"><Logo /></div>
        <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center py-10 animate-rise">
          <h1 className="text-3xl font-bold text-ink sm:text-4xl">{title}</h1>
          <p className="mt-2 text-muted-foreground">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </div>
      </main>
    </div>
  );
}
