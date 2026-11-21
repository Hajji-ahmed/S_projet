"use client";

import { Cake, Gift, PartyPopper, X } from "lucide-react";
import { useEffect, useState, type CSSProperties } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { cn } from "@/lib/cn";
import {
  ANNIVERSAIRE,
  CLE_CELEBRATION_VUE,
  DUREE_CELEBRATION_MS,
  estAnniversaire,
} from "@/lib/anniversaire";

/**
 * Surprise d'anniversaire de Salma (24/11/2026) : écran de 40 s à la première connexion du jour,
 * puis bannière en haut des pages jusqu'à minuit. Invisible pour tous les autres comptes.
 */
export function Anniversaire() {
  const { user } = useAuth();
  const [maintenant, setMaintenant] = useState(() => new Date());

  // Revérifie la date chaque minute : la bannière disparaît d'elle-même à minuit
  useEffect(() => {
    const minuterie = window.setInterval(() => setMaintenant(new Date()), 60_000);
    return () => window.clearInterval(minuterie);
  }, []);

  if (!estAnniversaire(user?.email, maintenant)) return null;
  return <Fete />;
}

function lireVue(): boolean {
  try {
    return window.localStorage.getItem(CLE_CELEBRATION_VUE) === "1";
  } catch {
    return false;
  }
}

function Fete() {
  const [celebration, setCelebration] = useState(() => !lireVue());

  useEffect(() => {
    if (!celebration) return;
    try {
      window.localStorage.setItem(CLE_CELEBRATION_VUE, "1");
    } catch {
      // Stockage indisponible : l'écran repassera au prochain chargement, sans gravité
    }
    const minuterie = window.setTimeout(() => setCelebration(false), DUREE_CELEBRATION_MS);
    return () => window.clearTimeout(minuterie);
  }, [celebration]);

  return (
    <>
      {celebration && <Celebration onFermer={() => setCelebration(false)} />}
      <Banniere />
    </>
  );
}

const COULEURS_BALLON = [
  "fill-simtis-fete-rose",
  "fill-simtis-fete-rose-fonce",
  "fill-simtis-fete-rose",
  "fill-simtis-secondary",
  "fill-simtis-fete-rose",
  "fill-simtis-warning",
];

const COULEURS_CONFETTI = [
  "bg-simtis-fete-rose",
  "bg-simtis-fete-rose-fonce",
  "bg-simtis-secondary",
  "bg-simtis-warning",
  "bg-simtis-primary",
];

// Positions fixes (pas de hasard au rendu), réparties sur toute la largeur
const BALLONS = Array.from({ length: 22 }, (_, i) => ({
  gauche: (i * 37 + 3) % 96,
  delai: (i * 1.3) % 9,
  duree: 9 + (i % 4) * 1.5,
  taille: 52 + (i % 3) * 16,
  couleur: COULEURS_BALLON[i % COULEURS_BALLON.length],
}));

const CONFETTIS = Array.from({ length: 48 }, (_, i) => ({
  gauche: (i * 53 + 7) % 100,
  delai: (i * 0.37) % 6,
  duree: 4 + (i % 5),
  couleur: COULEURS_CONFETTI[i % COULEURS_CONFETTI.length],
  rond: i % 3 === 0,
}));

function Ballon({ taille, className }: { taille: number; className: string }) {
  return (
    <svg width={taille} height={taille * 1.8} viewBox="0 0 40 72" aria-hidden="true">
      <ellipse cx="20" cy="22" rx="17" ry="21" className={className} />
      <ellipse cx="13" cy="14" rx="4" ry="6" className="fill-simtis-card opacity-40" />
      <path d="M17 42 L23 42 L20 46 Z" className={className} />
      <path
        d="M20 46 C 14 54, 26 60, 20 72"
        fill="none"
        strokeWidth="1"
        className="stroke-simtis-muted"
      />
    </svg>
  );
}

function Celebration({ onFermer }: { onFermer: () => void }) {
  useEffect(() => {
    const fermerSurEchap = (event: KeyboardEvent) => {
      if (event.key === "Escape") onFermer();
    };
    window.addEventListener("keydown", fermerSurEchap);
    return () => window.removeEventListener("keydown", fermerSurEchap);
  }, [onFermer]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Joyeux anniversaire ${ANNIVERSAIRE.prenom}`}
      className="fixed inset-0 z-[100] overflow-hidden bg-simtis-fete-rose-bg/95"
    >
      {CONFETTIS.map((c, i) => (
        <span
          key={`c${i}`}
          aria-hidden="true"
          style={
            { left: `${c.gauche}%`, "--d": `${c.duree}s`, "--r": `${c.delai}s` } as CSSProperties
          }
          className={cn(
            "absolute top-0 block h-3 w-2 animate-[simtis-confetti-tombe_var(--d)_linear_var(--r)_infinite] motion-reduce:hidden",
            c.rond && "h-2.5 w-2.5 rounded-full",
            c.couleur,
          )}
        />
      ))}

      {BALLONS.map((b, i) => (
        <div
          key={`b${i}`}
          aria-hidden="true"
          style={
            { left: `${b.gauche}%`, "--d": `${b.duree}s`, "--r": `${b.delai}s` } as CSSProperties
          }
          className="absolute -bottom-40 animate-[simtis-ballon-monte_var(--d)_ease-in_var(--r)_infinite] opacity-0 motion-reduce:bottom-4 motion-reduce:animate-none motion-reduce:opacity-100"
        >
          <Ballon taille={b.taille} className={b.couleur} />
        </div>
      ))}

      <div className="relative flex h-full items-center justify-center p-4">
        <div className="max-w-2xl animate-[simtis-fete-apparait_900ms_ease-out_both] rounded-[18px] bg-simtis-card px-6 py-10 text-center shadow-simtis-hover sm:px-12">
          <div className="mb-4 flex justify-center gap-4 text-simtis-fete-rose-fonce">
            <PartyPopper className="size-10" aria-hidden="true" />
            <Cake className="size-12" aria-hidden="true" />
            <Gift className="size-10" aria-hidden="true" />
          </div>
          <p className="text-lg font-medium text-simtis-muted">Happy birthday to you</p>
          <h1 className="mt-2 text-4xl font-bold text-simtis-fete-rose-fonce sm:text-5xl">
            Joyeux anniversaire {ANNIVERSAIRE.prenom} !
          </h1>
          <p className="mt-3 text-2xl font-semibold text-simtis-primary-dark">
            Happy birthday dear {ANNIVERSAIRE.prenom}
          </p>
          <p className="mt-6 text-simtis-text">
            Toute l&apos;équipe SIMTIS te souhaite une merveilleuse journée.
          </p>
          <button
            type="button"
            onClick={onFermer}
            className="mt-8 inline-flex items-center gap-2 rounded-[10px] bg-simtis-fete-rose-fonce px-5 py-2.5 text-sm font-semibold text-simtis-card transition-opacity duration-150 hover:opacity-90"
          >
            <X className="size-4" aria-hidden="true" />
            Merci !
          </button>
        </div>
      </div>
    </div>
  );
}

function Banniere() {
  return (
    <div
      role="status"
      className="relative flex items-center gap-4 overflow-hidden rounded-card border border-simtis-fete-rose bg-simtis-fete-rose-bg px-5 py-3 shadow-simtis"
    >
      <Cake className="size-7 shrink-0 text-simtis-fete-rose-fonce" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-bold text-simtis-fete-rose-fonce">
          Joyeux anniversaire {ANNIVERSAIRE.prenom} !
        </p>
        <p className="text-sm text-simtis-text">
          Happy birthday to you, de la part de toute l&apos;équipe SIMTIS.
        </p>
      </div>
      <div className="hidden shrink-0 items-end gap-1 sm:flex" aria-hidden="true">
        {COULEURS_BALLON.slice(0, 5).map((couleur, i) => (
          <div
            key={i}
            style={{ animationDelay: `${i * 0.4}s` }}
            className="animate-[simtis-ballon-flotte_3s_ease-in-out_infinite]"
          >
            <Ballon taille={20 + (i % 2) * 6} className={couleur} />
          </div>
        ))}
      </div>
    </div>
  );
}
