"use client";

import { CircleAlert, Eye, EyeOff, LogIn } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { safeNextPath } from "@/lib/redirect";

const INPUT_CLASSES =
  "h-[42px] w-full rounded-lg border border-simtis-border bg-simtis-card px-3 text-sm text-simtis-text placeholder:text-simtis-muted focus:border-simtis-primary focus:ring-2 focus:ring-simtis-primary/15 focus:outline-none disabled:opacity-60";

export function LoginForm() {
  const { status, login } = useAuth();
  const router = useRouter();
  const nextPath = safeNextPath(useSearchParams().get("next"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Déjà connecté (session restaurée) : inutile de rester sur cette page
  useEffect(() => {
    if (status === "authenticated") router.replace(nextPath);
  }, [status, nextPath, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      router.replace(nextPath);
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 401
          ? caught.message
          : "Connexion impossible pour le moment. Réessayez dans quelques instants.",
      );
      setPassword("");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg bg-simtis-danger-bg px-3 py-2.5 text-sm text-simtis-danger-fg"
        >
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{error}</span>
        </div>
      )}

      <div>
        <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-simtis-text">
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          autoFocus
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          disabled={submitting}
          placeholder="prenom.nom@simtis.ma"
          className={INPUT_CLASSES}
        />
      </div>

      <div>
        <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-simtis-text">
          Mot de passe
        </label>
        <div className="relative">
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={submitting}
            className={`${INPUT_CLASSES} pr-11`}
          />
          <button
            type="button"
            onClick={() => setShowPassword((shown) => !shown)}
            aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
            aria-pressed={showPassword}
            className="absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-lg text-simtis-muted transition-colors hover:text-simtis-primary"
          >
            {showPassword ? (
              <EyeOff className="h-4 w-4" aria-hidden />
            ) : (
              <Eye className="h-4 w-4" aria-hidden />
            )}
          </button>
        </div>
      </div>

      <Button
        type="submit"
        icon={LogIn}
        disabled={submitting || !email || !password}
        className="w-full justify-center"
      >
        {submitting ? "Connexion..." : "Se connecter"}
      </Button>
    </form>
  );
}
