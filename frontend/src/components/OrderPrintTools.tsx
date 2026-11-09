import { useRef, useState } from "react";
import { Download, FileDown, Printer } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { tk } from "@/i18n";
import type { OrderOut, QuoteLine } from "@/lib/types";

/** "1, 3, 5-7" from [1,3,5,6,7] — compact display of the exact pages the customer asked for. */
export function formatPages(pages: number[] | null | undefined): string {
  if (!pages?.length) return "—";
  const out: string[] = [];
  for (let i = 0; i < pages.length; i++) {
    let j = i;
    while (j + 1 < pages.length && pages[j + 1] === pages[j] + 1) j++;
    out.push(j > i + 1 ? `${pages[i]}-${pages[j]}` : j === i + 1 ? `${pages[i]}, ${pages[j]}` : `${pages[i]}`);
    i = j;
  }
  return out.join(", ");
}

const fileUrl = (orderId: string, docId: string, variant: "original" | "print", disposition: "attachment" | "inline") =>
  `/api/orders/${orderId}/documents/${docId}/file?variant=${variant}&disposition=${disposition}`;

/**
 * Per-document print facts + the three separate actions. Downloading never prints; « Imprimer » opens the
 * system print dialog on the print-ready file (only the selected pages) and the employee confirms there.
 */
export function OrderLineDetails({ order, canDownload }: { order: OrderOut; canDownload: boolean }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [printing, setPrinting] = useState<string | null>(null);
  const deleted = !!order.purged_at;
  const docs = order.lines.filter((l): l is QuoteLine & { document_id: string } => l.kind === "print" && !!l.document_id);

  const openPrintDialog = (l: QuoteLine & { document_id: string }) => {
    const f = frame.current;
    if (!f) return;
    setPrinting(l.document_id);
    f.onload = () => {
      try {
        f.contentWindow?.focus();
        f.contentWindow?.print(); // system dialog: nothing prints until the employee confirms
      } catch {
        window.open(fileUrl(order.id, l.document_id, "print", "inline"), "_blank", "noopener");
      }
      setPrinting(null);
    };
    f.src = fileUrl(order.id, l.document_id, "print", "inline");
  };

  if (!docs.length) return null;
  return (
    <div className="space-y-2" data-testid="order-print-details">
      <iframe ref={frame} title="Aperçu avant impression" className="hidden" aria-hidden="true" />
      {docs.map((l, i) => {
        const selected = l.selected_pages ?? null;
        const toPrint = (selected?.length ?? l.pages) * l.copies;
        return (
          <div key={l.document_id} className="rounded-xl border bg-white p-3" data-testid={`print-details-${i}`}>
            <p className="truncate text-sm font-semibold text-ink" data-testid={`print-details-${i}-filename`}>{l.filename ?? "Document"}</p>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
              <div><dt className="text-muted-foreground">Pages du document</dt><dd className="font-semibold text-ink" data-testid={`print-details-${i}-doc-pages`}>{l.document_pages ?? "—"}</dd></div>
              <div><dt className="text-muted-foreground">Pages demandées</dt><dd className="font-semibold text-ink" data-testid={`print-details-${i}-requested`}>{l.options?.page_range ? formatPages(selected) : "Toutes"}</dd></div>
              <div><dt className="text-muted-foreground">Pages à imprimer</dt><dd className="font-semibold text-ink" data-testid={`print-details-${i}-to-print`}>{toPrint}{l.copies > 1 ? ` (${selected?.length ?? l.pages} × ${l.copies} ex.)` : ""}</dd></div>
              <div><dt className="text-muted-foreground">Exemplaires</dt><dd className="font-semibold text-ink">{l.copies}</dd></div>
              <div><dt className="text-muted-foreground">Couleur</dt><dd className="font-semibold text-ink" data-testid={`print-details-${i}-color`}>{l.options?.color === "color" ? "Couleur" : "Noir & blanc"}</dd></div>
              <div><dt className="text-muted-foreground">Format</dt><dd className="font-semibold text-ink">{l.options ? `${tk("paper", l.options.paper_size)}${l.options.duplex ? " · recto-verso" : ""}` : "—"}</dd></div>
            </dl>
            {deleted ? (
              <p className="mt-2 text-xs text-muted-foreground" data-testid={`print-details-${i}-deleted`}>Fichier supprimé après la fin de la commande.</p>
            ) : canDownload && (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" render={<a href={fileUrl(order.id, l.document_id, "original", "attachment")} download data-testid={`print-details-${i}-download-original`} />}>
                  <Download className="size-3.5" /> Original
                </Button>
                <Button size="sm" variant="outline" render={<a href={fileUrl(order.id, l.document_id, "print", "attachment")} download data-testid={`print-details-${i}-download-print`} />}>
                  <FileDown className="size-3.5" /> PDF à imprimer
                </Button>
                <Button size="sm" disabled={printing === l.document_id} onClick={() => { openPrintDialog(l); toast.info("Vérifiez l'aperçu puis confirmez l'impression dans la fenêtre du système"); }}
                  data-testid={`print-details-${i}-print`}>
                  <Printer className="size-3.5" /> Imprimer…
                </Button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
