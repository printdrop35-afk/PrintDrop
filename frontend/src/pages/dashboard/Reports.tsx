import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Mail, Send } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useDashboard } from "@/hooks/useDashboard";
import { apiGet, apiPost, apiPut, errorMessage } from "@/lib/api";
import { formatEUR } from "@/i18n";
import type { DailyReportOut, ReportSettingsIn, ReportSettingsOut } from "@/lib/types";

const parisToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Paris" }).format(new Date());
const shift = (day: string, n: number) => {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
const longDate = (day: string) => new Intl.DateTimeFormat("fr-FR", { dateStyle: "full", timeZone: "UTC" }).format(new Date(`${day}T12:00:00Z`));

function Stat({ label, value, hint, testId, tone = "text-ink" }: { label: string; value: string | number; hint?: string; testId: string; tone?: string }) {
  return (
    <div className="rounded-2xl border bg-card p-4" data-testid={testId}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={`mt-1 font-heading text-2xl font-bold ${tone}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export default function Reports() {
  const { shop, can } = useDashboard();
  const qc = useQueryClient();
  const today = parisToday();
  const [day, setDay] = useState(today);

  const report = useQuery({
    queryKey: ["report", shop.id, day],
    queryFn: () => apiGet<DailyReportOut>(`/shops/${shop.id}/reports/daily?day=${day}`),
    refetchInterval: day === today ? 30_000 : false,
  });
  const settings = useQuery({ queryKey: ["report-settings"], queryFn: () => apiGet<ReportSettingsOut>("/reports/settings") });
  const save = useMutation({
    mutationFn: (body: ReportSettingsIn) => apiPut<ReportSettingsOut>("/reports/settings", body),
    onSuccess: (s) => { qc.setQueryData(["report-settings"], s); toast.success(s.daily_email ? "Rapport quotidien activé (21h)" : "Rapport quotidien désactivé"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const sendNow = useMutation({
    mutationFn: () => apiPost<{ sent_to: string }>("/reports/email-now"),
    onSuccess: (r) => toast.success(`Rapport envoyé à ${r.sent_to}`),
    onError: (e) => toast.error(errorMessage(e)),
  });

  const r = report.isError ? undefined : report.data;
  const s = settings.isError ? undefined : settings.data;
  const manage = can("reports:manage");
  const chart = (r?.hours ?? []).filter((h) => h.hour >= 7 && h.hour <= 22);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold tracking-[0.15em] text-azure uppercase">{shop.name}</p>
          <h1 className="mt-1 text-3xl font-bold text-ink">Rapport quotidien</h1>
          <p className="mt-1 text-sm text-muted-foreground capitalize" data-testid="report-day-label">{longDate(day)}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setDay(shift(day, -1))} aria-label="Jour précédent" data-testid="report-prev-day"><ChevronLeft className="size-4" /></Button>
          <Input type="date" value={day} max={today} onChange={(e) => e.target.value && setDay(e.target.value)} className="h-9 w-40" data-testid="report-day-input" />
          <Button variant="outline" size="icon" disabled={day >= today} onClick={() => setDay(shift(day, 1))} aria-label="Jour suivant" data-testid="report-next-day"><ChevronRight className="size-4" /></Button>
          {day !== today && <Button variant="ghost" size="sm" onClick={() => setDay(today)} data-testid="report-today">Aujourd'hui</Button>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Chiffre d'affaires encaissé" value={r ? formatEUR(r.revenue_cents) : "—"} hint={r ? `Espèces ${formatEUR(r.revenue_cash_cents)} · Carte ${formatEUR(r.revenue_card_cents)}` : undefined} testId="report-revenue" />
        <Stat label="Commandes" value={r?.orders_total ?? "—"} hint={r ? `${r.orders_picked_up} retirées · ${r.orders_cancelled} annulées` : undefined} testId="report-orders" />
        <Stat label="Pages imprimées" value={r ? r.pages_bw + r.pages_color : "—"} hint={r ? `${r.pages_bw} N&B · ${r.pages_color} couleur · ${r.sheets} feuilles` : undefined} testId="report-pages" />
        <Stat label="Heure la plus chargée" value={r?.busiest_hour != null ? `${r.busiest_hour}h – ${r.busiest_hour + 1}h` : "—"} testId="report-busiest-hour" tone="text-azure" />
        <Stat label="Panier moyen" value={r ? formatEUR(r.avg_basket_cents) : "—"} hint={r ? `${r.payments_count} paiement(s)` : undefined} testId="report-avg-basket" />
        <Stat label="Photocopies / scans" value={r ? `${r.photocopies} / ${r.scans}` : "—"} testId="report-services" />
        <Stat label="Travaux agent imprimés / échecs" value={r ? `${r.jobs_printed} / ${r.jobs_failed}` : "—"} testId="report-jobs" />
        <Stat label="Reste à encaisser" value={r ? formatEUR(r.unpaid_cents) : "—"} testId="report-unpaid" tone="text-rose-600" />
      </div>

      <section className="rounded-2xl border bg-card p-5">
        <h2 className="text-lg font-semibold text-ink">Activité par heure</h2>
        <p className="text-xs text-muted-foreground">Commandes reçues entre 7h et 23h (heure de Paris). La barre bleue foncée marque l'heure la plus chargée.</p>
        <div className="mt-4 h-64" data-testid="report-hourly-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#E2E8F0" />
              <XAxis dataKey="hour" tickFormatter={(h: number) => `${h}h`} tick={{ fontSize: 12, fill: "#64748B" }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#64748B" }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: "#EFF6FF" }} labelFormatter={(label: string) => `${label}h – ${Number(label) + 1}h`}
                formatter={(value: number, name: string) => (name === "orders" ? [value, "Commandes"] : [formatEUR(value), "Encaissé"])} />
              <Bar dataKey="orders" radius={[6, 6, 0, 0]}>
                {chart.map((h) => <Cell key={h.hour} fill={h.hour === r?.busiest_hour ? "#1D4ED8" : "#93C5FD"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="flex flex-wrap items-center gap-4 rounded-2xl border bg-card p-5" data-testid="report-email-settings">
        <Mail className="size-6 text-azure" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-ink">Rapport par e-mail chaque soir à 21h</p>
          <p className="text-sm text-muted-foreground">Toutes vos boutiques, envoyé à {s?.recipient ?? "…"} (compte propriétaire).</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={!!s?.daily_email} disabled={!manage || !s || save.isPending} onCheckedChange={(c: boolean) => save.mutate({ daily_email: c })} data-testid="report-email-toggle" />
          Activé
        </label>
        {manage && (
          <Button variant="outline" disabled={sendNow.isPending} onClick={() => sendNow.mutate()} data-testid="report-email-now-button">
            <Send className="size-4" /> Envoyer maintenant
          </Button>
        )}
      </section>
    </div>
  );
}
