import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPut, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/i18n";
import type { AgentReleaseIn, AgentReleaseOut } from "@/lib/types";

/** Super-admin: one installer link + latest version for every shop (enables « Télécharger l'agent » and update notices). */
export function AgentReleaseAdmin() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-agent-release"], queryFn: () => apiGet<AgentReleaseOut>("/admin/agent-release") });
  const [form, setForm] = useState<AgentReleaseIn>({ url: "", version: "", notes: "" });
  useEffect(() => {
    if (q.data) setForm({ url: q.data.url, version: q.data.version, notes: q.data.notes });
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
      <form className="mt-4 grid gap-3 md:grid-cols-[1fr_140px]" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <label className="text-sm">
          <span className="font-medium text-ink">Lien de l'installateur</span>
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
            {q.data?.url ? "Téléchargement actif" : "Téléchargement désactivé (aucun lien)"}
            {q.data?.updated_at ? ` · modifié le ${formatDateTime(q.data.updated_at)}` : ""}
          </span>
        </div>
      </form>
    </section>
  );
}
