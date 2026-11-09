import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, Inbox, Mail, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiGet, apiPatch, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/i18n";
import { cn } from "@/lib/utils";
import type { ContactMessageOut, ContactMessageUpdateIn } from "@/lib/types";

type Filter = "open" | "demo" | "all";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "open", label: "À traiter" },
  { key: "demo", label: "Démos" },
  { key: "all", label: "Tous" },
];

/** Super-admin inbox for the public contact / demo form — nothing is lost even if the e-mail copy failed. */
export function ContactInbox() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("open");
  const [openId, setOpenId] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["admin-contact"], queryFn: () => apiGet<ContactMessageOut[]>("/admin/contact-messages"), refetchInterval: 30000 });
  const mark = useMutation({
    mutationFn: ({ id, handled }: { id: string } & ContactMessageUpdateIn) => apiPatch<ContactMessageOut>(`/admin/contact-messages/${id}`, { handled }),
    onSuccess: (m) => {
      toast.success(m.handled ? "Marqué comme traité" : "Remis à traiter");
      qc.invalidateQueries({ queryKey: ["admin-contact"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const all = q.isError ? [] : q.data ?? [];
  const open = all.filter((m) => !m.handled).length;
  const list = all.filter((m) => (filter === "open" ? !m.handled : filter === "demo" ? m.kind === "demo" : true));

  return (
    <section id="messages-du-site" className="scroll-mt-6 rounded-2xl border bg-card p-5" data-testid="admin-contact-inbox">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Inbox className="size-5 text-azure" />
          <h2 className="text-lg font-semibold text-ink">Messages du site</h2>
          {open > 0 && <span className="rounded-full bg-azure px-2 py-0.5 text-xs font-semibold text-white" data-testid="contact-open-count">{open} à traiter</span>}
        </div>
        <div className="flex gap-1 rounded-lg bg-slate-100 p-1" role="tablist">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" role="tab" aria-selected={filter === f.key} onClick={() => setFilter(f.key)} data-testid={`contact-filter-${f.key}`}
              className={cn("rounded-md px-3 py-1 text-xs font-semibold transition-colors", filter === f.key ? "bg-white text-ink shadow-sm" : "text-slate-500 hover:text-ink")}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {q.isError && <p className="mt-3 text-sm text-rose-700">{errorMessage(q.error)}</p>}
      {list.length === 0 ? (
        <p className="mt-4 rounded-lg bg-slate-50 p-4 text-sm text-muted-foreground" data-testid="contact-empty">
          {filter === "open" ? "Aucun message à traiter." : "Aucun message."}
        </p>
      ) : (
        <ul className="mt-4 divide-y rounded-xl border" data-testid="contact-list">
          {list.map((m) => (
            <li key={m.id} className={cn("p-4", m.handled && "bg-slate-50/70")} data-testid={`contact-row-${m.id}`}>
              <button type="button" className="flex w-full flex-wrap items-start justify-between gap-2 text-left" onClick={() => setOpenId(openId === m.id ? null : m.id)} data-testid={`contact-toggle-${m.id}`}>
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2">
                    {m.kind === "demo" && <span className="rounded-full bg-[#E0F7FA] px-2 py-0.5 text-[11px] font-semibold text-[#0E7490]">Démo</span>}
                    <span className={cn("font-semibold", m.handled ? "text-slate-500" : "text-ink")}>{m.subject}</span>
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">{m.name}{m.business ? ` · ${m.business}` : ""} · {m.email}</span>
                </span>
                <span className="text-xs text-muted-foreground">{formatDateTime(m.created_at)}</span>
              </button>
              {openId === m.id && (
                <div className="mt-3 space-y-3">
                  <p className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700" data-testid={`contact-message-${m.id}`}>{m.message}</p>
                  <p className="text-xs text-muted-foreground">{m.delivered ? "Copie envoyée par e-mail à contact@printdrop.fr." : "Copie e-mail non envoyée : message disponible uniquement ici."}</p>
                  <div className="flex flex-wrap gap-2">
                    <a href={`mailto:${m.email}?subject=${encodeURIComponent(`Re : ${m.subject}`)}`} className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-xs font-semibold text-ink transition-colors hover:bg-slate-50" data-testid={`contact-reply-${m.id}`}>
                      <Mail className="size-3.5" /> Répondre
                    </a>
                    <Button size="sm" variant={m.handled ? "outline" : "default"} disabled={mark.isPending} onClick={() => mark.mutate({ id: m.id, handled: !m.handled })} data-testid={`contact-mark-${m.id}`}>
                      {m.handled ? <><RotateCcw className="size-3.5" /> Remettre à traiter</> : <><CheckCircle2 className="size-3.5" /> Marquer comme traité</>}
                    </Button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Header badge: unhandled contact/demo requests, polled every 30 s; a toast announces each new arrival. */
export function NewMessagesBadge() {
  const q = useQuery({ queryKey: ["admin-contact"], queryFn: () => apiGet<ContactMessageOut[]>("/admin/contact-messages"), refetchInterval: 30000 });
  const list = q.isError ? [] : q.data ?? [];
  const open = list.filter((m) => !m.handled);
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!q.data) return;
    const ids = new Set(q.data.map((m) => m.id));
    if (seen.current) {
      const fresh = q.data.filter((m) => !seen.current!.has(m.id));
      if (fresh.length) toast.info(fresh.length === 1 ? `Nouveau message : ${fresh[0].subject}` : `${fresh.length} nouveaux messages du site`);
    }
    seen.current = ids;
  }, [q.data]);
  return (
    <a href="#messages-du-site" className="relative inline-flex items-center gap-2 text-sm text-slate-300 transition-colors hover:text-white" data-testid="admin-messages-badge"
      aria-label={`${open.length} message(s) à traiter`}>
      <Inbox className="size-4" /> Messages
      {open.length > 0 && (
        <span className="grid min-w-5 place-items-center rounded-full bg-[#08BBD0] px-1.5 text-[11px] font-bold text-[#042F2E]" data-testid="admin-messages-count">{open.length}</span>
      )}
    </a>
  );
}
