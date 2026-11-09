import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Download, FileCheck2, Loader2 } from "lucide-react";
import { Logo } from "@/components/Logo";
import { apiGet, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/i18n";
import type { ScanPublicOut } from "@/lib/types";

/** Customer page behind the QR code / e-mail link: download the scanned document. No account, no code. */
export default function ScanDownload() {
  const { token = "" } = useParams();
  const q = useQuery({ queryKey: ["scan", token], queryFn: () => apiGet<ScanPublicOut>(`/public/scans/${encodeURIComponent(token)}`), retry: false });
  const s = q.data;
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-white px-4 py-3"><Logo /></header>
      <main className="mx-auto max-w-md space-y-4 p-4 pt-8" data-testid="scan-download-page">
        {q.isLoading && <Loader2 className="mx-auto size-6 animate-spin text-azure" />}
        {q.isError && <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900" data-testid="scan-download-error">{errorMessage(q.error)}</p>}
        {s && (
          <section className="space-y-4 rounded-2xl border bg-white p-6 text-center shadow-sm">
            <FileCheck2 className="mx-auto size-10 text-azure" />
            <div>
              <h1 className="font-heading text-xl font-bold text-ink">Votre scan est prêt</h1>
              <p className="text-sm text-muted-foreground">{s.shop_name} · {s.filename} · {s.pages} page{s.pages > 1 ? "s" : ""}</p>
            </div>
            {!s.available ? (
              <p className="rounded-lg bg-slate-50 p-3 text-sm text-muted-foreground" data-testid="scan-download-deleted">Ce scan a été supprimé (24 h après le premier téléchargement).</p>
            ) : !s.paid ? (
              <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900" data-testid="scan-download-unpaid">Le scan sera disponible dès le paiement au comptoir.</p>
            ) : (
              <a href={`/api/public/scans/${encodeURIComponent(token)}/file`} className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-azure font-semibold text-white transition-colors hover:bg-azure/90" data-testid="scan-download-button">
                <Download className="size-5" /> Télécharger ({s.kind.toUpperCase()})
              </a>
            )}
            <p className="text-xs text-muted-foreground" data-testid="scan-download-retention">
              {s.first_download_at ? `Premier téléchargement le ${formatDateTime(s.first_download_at)} — le fichier est supprimé 24 h après.` : "Le fichier sera supprimé de nos serveurs 24 h après votre premier téléchargement."}
            </p>
          </section>
        )}
      </main>
    </div>
  );
}
