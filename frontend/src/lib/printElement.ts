/**
 * Prints ONE element (receipt, pickup ticket) in a clean hidden frame with the app's styles,
 * so page layout (side sheets, fixed panels, buttons) can never leak into or crop the printout.
 * Opens the browser's print dialog: the user still confirms.
 */
export function printElement(el: HTMLElement | null, opts: { pageWidth?: string; title?: string } = {}): void {
  if (!el) return;
  const styles = Array.from(document.querySelectorAll('link[rel="stylesheet"], style'))
    .map((n) => n.outerHTML)
    .join("\n");
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.title = opts.title ?? "Impression";
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
  const html = `<!doctype html><html lang="fr" class="${document.documentElement.className}"><head><meta charset="utf-8">
<base href="${location.origin}/"><title>${opts.title ?? "PrintDrop"}</title>${styles}
<style>
  @page { margin: 6mm; }
  html, body { background: #fff !important; margin: 0; }
  body { display: flex; justify-content: center; }
  .pd-print-root { width: ${opts.pageWidth ?? "100%"}; max-width: 100%; }
  .pd-print-root, .pd-print-root * { visibility: visible !important; }
  .pd-no-print { display: none !important; }
  .pd-print-root > * { position: static !important; max-width: none !important; width: 100% !important; box-shadow: none !important; }
</style></head><body><div class="pd-print-root">${el.outerHTML}</div></body></html>`;
  frame.srcdoc = html;
  frame.onload = () => {
    const w = frame.contentWindow;
    if (!w) return;
    const go = () => {
      w.focus();
      w.print();
      window.setTimeout(() => frame.remove(), 1000);
    };
    // wait for the logo image(s) inside the frame before printing
    const imgs = Array.from(w.document.images).filter((i) => !i.complete);
    if (!imgs.length) return go();
    let left = imgs.length;
    imgs.forEach((i) => { i.onload = i.onerror = () => { if (--left === 0) go(); }; });
  };
  document.body.appendChild(frame);
}
