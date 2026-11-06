import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthShell } from "@/components/AuthShell";
import { apiPost, errorMessage } from "@/lib/api";
import { beginSession } from "@/lib/session";
import { queryClient } from "@/lib/queryClient";
import { ME_KEY } from "@/hooks/useMe";
import type { MeOut, RegisterIn } from "@/lib/types";

const EMPTY: RegisterIn = { org_name: "", shop_name: "", city: "", owner_name: "", email: "", password: "" };

const FIELDS: { key: keyof RegisterIn; label: string; type?: string; auto?: string; hint?: string }[] = [
  { key: "org_name", label: "Nom de l'entreprise", hint: "Raison sociale" },
  { key: "shop_name", label: "Nom de la boutique", hint: "Affiché à vos clients" },
  { key: "city", label: "Ville" },
  { key: "owner_name", label: "Votre nom complet", auto: "name" },
  { key: "email", label: "Adresse e-mail", type: "email", auto: "email" },
  { key: "password", label: "Mot de passe (8 caractères min.)", type: "password", auto: "new-password" },
];

export default function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState<RegisterIn>(EMPTY);
  const [error, setError] = useState("");

  const register = useMutation({
    mutationFn: (body: RegisterIn) => apiPost<MeOut>("/auth/register", body),
    onSuccess: (me) => {
      beginSession();
      queryClient.setQueryData(ME_KEY, me);
      toast.success("Votre espace PrintDrop est prêt");
      navigate("/dashboard");
    },
    onError: (err) => setError(errorMessage(err, "Inscription impossible")),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    register.mutate(form);
  };

  return (
    <AuthShell
      title="Créer votre espace"
      subtitle="Ouvrez votre boutique PrintDrop en moins de deux minutes."
      aside={
        <>
          <p className="text-sm font-semibold tracking-[0.15em] text-sky-300 uppercase">Essai gratuit</p>
          <h2 className="mt-4 text-4xl leading-tight font-bold">Votre QR code d'impression, prêt aujourd'hui.</h2>
          <ul className="mt-6 space-y-3 text-slate-200">
            {["Portail client mobile en français", "Tarifs calculés automatiquement côté serveur", "Données isolées par entreprise"].map((x) => (
              <li key={x} className="flex items-center gap-3"><CheckCircle2 className="size-5 text-emerald-400" />{x}</li>
            ))}
          </ul>
        </>
      }
    >
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" data-testid="register-form">
        {FIELDS.map((f) => (
          <div key={f.key} className={f.key === "email" || f.key === "password" || f.key === "owner_name" ? "space-y-2 sm:col-span-2" : "space-y-2"}>
            <Label htmlFor={f.key}>{f.label}</Label>
            <Input id={f.key} type={f.type ?? "text"} autoComplete={f.auto} required placeholder={f.hint}
              minLength={f.key === "password" ? 8 : 2 - (f.key === "city" ? 1 : 0)}
              value={form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
              className="h-11" data-testid={`register-${f.key.replace("_", "-")}-input`} />
          </div>
        ))}
        {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 sm:col-span-2" data-testid="register-error">{error}</p>}
        <Button type="submit" className="h-11 text-base sm:col-span-2" disabled={register.isPending} data-testid="register-submit-button">
          {register.isPending ? "Création…" : "Créer mon espace boutique"}
        </Button>
      </form>
      <p className="mt-6 text-sm text-muted-foreground">
        Déjà inscrit ?{" "}
        <Link to="/login" className="font-semibold text-azure hover:underline" data-testid="register-login-link">Se connecter</Link>
      </p>
    </AuthShell>
  );
}
