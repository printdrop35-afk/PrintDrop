import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download, Loader2, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiDelete, apiGet, apiPut, apiUpload, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/i18n";
import type { AgentReleaseIn, AgentReleaseOut } from "@/lib/types";

/** Super-admin: one installer link + latest version for every shop (enables « Télécharger l'agent » and update notices). */
export function AgentReleaseAdmin() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-agent-release"], queryFn: () => apiGet<AgentReleaseOut>("/admin/agent-release") });
  const [form, setForm] = useState<AgentReleaseIn>({ url: "", version: "", notes: "" });
  useEffect(() => {
    if (q.data) setForm({ url: q.data.external_url ?? "", version: q.data.version, notes: q.data.notes });
  }, [q.data]);
  const save = useMutation({
    mutationFn: () => apiPut<AgentReleaseOut>("/admin/agent-release", form),
    onSuccess: () => {
      toast.success("Agent Windows mis à jour pour toutes les boutiques");
      qc.invalidateQueries({ queryKey: ["admin-agent-release"] });
      qc.invalidateQueries({ queryKey: ["agent-download"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const fileRef = useRef<HTMLInputElement>(null);
  const done = (msg: string) => { toast.success(msg); qc.invalidateQueries({ queryKey: ["admin-agent-release"] }); qc.invalidateQueries({ queryKey: ["agent-download"] }); };
  const upload = useMutation({
    mutationFn: (f: File) => apiUpload<AgentReleaseOut>(`/admin/agent-release/upload?notes=${encodeURIComponent(form.notes)}`, f),
    onSuccess: (r) => done(`Installateur v${r.version} publié : toutes les boutiques peuvent le télécharger`),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({ mutationFn: () => apiDelete<AgentReleaseOut>("/admin/agent-release/file"), onSuccess: () => done("Installateur retiré"), onError: (e) => toast.error(errorMessage(e)) });
  const hosted = !!q.data?.filename;
  const set = (k: keyof AgentReleaseIn) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <section className="rounded-2xl border bg-card p-5" data-testid="admin-agent-release">
      <div className="flex items-center gap-2">
        <Download className="size-5 text-azure" />
        <h2 className="text-lg font-semibold text-ink">Agent Windows — installateur</h2>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Lien direct vers le fichier .exe publié par GitHub (Releases). Il active le bouton « Télécharger l'agent » de toutes les boutiques.
        Augmentez la version pour afficher un avis de mise à jour aux boutiques dont l'agent est plus ancien.
      </p>
      <div className="mt-4 rounded-xl border border-dashed p-4" data-testid="agent-installer-hosted">
        <p className="text-sm font-semibold text-ink">Installateur hébergé sur printdrop.fr (recommandé)</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Par défaut, les boutiques reçoivent l'installateur livré avec PrintDrop (backend/agent_dist). Pour publier une autre version sans redéployer, envoyez ici un fichier PrintDrop-Setup-x.y.z.exe (la version est lue dans le nom du fichier).
        </p>
        {hosted ? (
          <p className="mt-2 text-sm" data-testid="agent-installer-info">
            <span className="font-semibold text-emerald-700">En ligne</span> · {q.data?.filename} · {((q.data?.size_bytes ?? 0) / 1048576).toFixed(1)} Mo
            <span className="block break-all font-mono text-[11px] text-muted-foreground">SHA-256 {q.data?.sha256}</span>
          </p>
        ) : <p className="mt-2 text-sm text-amber-700" data-testid="agent-installer-none">Aucun installateur hébergé.</p>}
        <input ref={fileRef} type="file" accept=".exe" className="hidden" data-testid="agent-installer-input"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" onClick={() => fileRef.current?.click()} disabled={upload.isPending} data-testid="agent-installer-upload">
            {upload.isPending ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />} {upload.isPending ? "Envoi…" : hosted ? "Remplacer l'installateur" : "Envoyer l'installateur (.exe)"}
          </Button>
          {hosted && <Button type="button" variant="outline" onClick={() => remove.mutate()} disabled={remove.isPending} data-testid="agent-installer-remove"><Trash2 className="size-4" /> Retirer</Button>}
        </div>
      </div>
      <form className="mt-4 grid gap-3 md:grid-cols-[1fr_140px]" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <label className="text-sm">
          <span className="font-medium text-ink">Ou lien externe (utilisé seulement sans installateur hébergé)</span>
          <Input value={form.url} onChange={set("url")} placeholder="https://github.com/compte/depot/releases/latest/download/PrintDrop-Setup.exe" className="mt-1" data-testid="agent-release-url" />
        </label>
        <label className="text-sm">
          <span className="font-medium text-ink">Dernière version</span>
          <Input value={form.version} onChange={set("version")} placeholder="0.2.0" className="mt-1 font-mono" data-testid="agent-release-version" />
        </label>
        <label className="text-sm md:col-span-2">
          <span className="font-medium text-ink">Nouveautés (affichées aux boutiques)</span>
          <Textarea value={form.notes} onChange={set("notes")} rows={2} maxLength={500} className="mt-1" data-testid="agent-release-notes" />
        </label>
        <div className="flex flex-wrap items-center gap-3 md:col-span-2">
          <Button type="submit" disabled={save.isPending} data-testid="agent-release-save">Enregistrer</Button>
          <span className="text-xs text-muted-foreground" data-testid="agent-release-status">
            {hosted ? "Téléchargement actif (printdrop.fr)" : q.data?.url ? "Téléchargement actif (lien externe)" : "Téléchargement désactivé"}
            {q.data?.updated_at ? ` · modifié le ${formatDateTime(q.data.updated_at)}` : ""}
          </span>
        </div>
      </form>
    </section>
  );
}
