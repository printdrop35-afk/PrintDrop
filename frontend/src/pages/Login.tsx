import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthShell } from "@/components/AuthShell";
import { apiPost, errorMessage } from "@/lib/api";
import { beginSession } from "@/lib/session";
import { queryClient } from "@/lib/queryClient";
import { ME_KEY } from "@/hooks/useMe";
import type { LoginIn, MeOut } from "@/lib/types";

export function landingPathFor(me: MeOut): string {
  if (me.platform_role === "superadmin" && !me.org) return "/superadmin";
  return "/dashboard";
}

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const login = useMutation({
    mutationFn: (body: LoginIn) => apiPost<MeOut>("/auth/login", body),
    onSuccess: (me) => {
      beginSession();
      queryClient.setQueryData(ME_KEY, me);
      toast.success(`Bienvenue, ${me.user.name}`);
      navigate(landingPathFor(me));
    },
    onError: (err) => setError(errorMessage(err, "Connexion impossible")),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    login.mutate({ email, password });
  };

  return (
    <AuthShell
      title="Connexion"
      subtitle="Accédez au tableau de bord de votre boutique."
      aside={
        <>
          <p className="text-sm font-semibold tracking-[0.15em] text-sky-300 uppercase">Espace professionnel</p>
          <h2 className="mt-4 text-4xl leading-tight font-bold">Toutes vos commandes d'impression, au même endroit.</h2>
          <p className="mt-4 text-slate-300">Vos clients scannent, déposent et paient. Vous imprimez et encaissez — sans clé USB ni e-mail.</p>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-5" data-testid="login-form">
        <div className="space-y-2">
          <Label htmlFor="email">Adresse e-mail</Label>
          <Input id="email" type="email" autoComplete="email" required value={email}
            onChange={(e) => setEmail(e.target.value)} className="h-11" data-testid="login-email-input" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Mot de passe</Label>
          <Input id="password" type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} className="h-11" data-testid="login-password-input" />
        </div>
        {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700" data-testid="login-error">{error}</p>}
        <Button type="submit" className="h-11 w-full text-base" disabled={login.isPending} data-testid="login-submit-button">
          {login.isPending ? "Connexion…" : "Se connecter"}
        </Button>
      </form>
      <p className="mt-6 text-sm text-muted-foreground">
        Pas encore de compte ?{" "}
        <Link to="/inscription" className="font-semibold text-azure hover:underline" data-testid="login-register-link">
          Créer mon espace boutique
        </Link>
      </p>
    </AuthShell>
  );
}
