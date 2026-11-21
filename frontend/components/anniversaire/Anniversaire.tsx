"use client";

import { Cake, Gift, PartyPopper, Volume2, VolumeX, X } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { cn } from "@/lib/cn";
import {
  ANNIVERSAIRE,
  cleCelebrationVue,
  DUREE_CELEBRATION_MS,
  estAnniversaire,
} from "@/lib/anniversaire";

/** Chanson jouée pendant l'écran de célébration (fichier libre de droits dans public/). */
const CHANSON = "/anniversaire/chanson.mp3";

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
  const cle = cleCelebrationVue(maintenant);
  return <Fete key={cle} cle={cle} />;
}

function lireVue(cle: string): boolean {
  try {
    return window.localStorage.getItem(cle) === "1";
  } catch {
    return false;
  }
}

function Fete({ cle }: { cle: string }) {
  const [celebration, setCelebration] = useState(() => !lireVue(cle));

  useEffect(() => {
    if (!celebration) return;
    try {
      window.localStorage.setItem(cle, "1");
    } catch {
      // Stockage indisponible : l'écran repassera au prochain chargement, sans gravité
    }
    const minuterie = window.setTimeout(() => setCelebration(false), DUREE_CELEBRATION_MS);
    return () => window.clearTimeout(minuterie);
  }, [celebration, cle]);

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

// Feux d'artifice : bouquets à des endroits fixes, qui éclatent l'un après l'autre
const FEUX = [
  { haut: 14, gauche: 12, delai: 0 },
  { haut: 10, gauche: 78, delai: 0.5 },
  { haut: 32, gauche: 88, delai: 1.1 },
  { haut: 30, gauche: 6, delai: 1.6 },
  { haut: 70, gauche: 85, delai: 0.8 },
  { haut: 72, gauche: 14, delai: 1.9 },
  { haut: 6, gauche: 45, delai: 1.3 },
];

/** Étincelles disposées en cercle, lancées depuis le centre de leur parent. */
function Eclat({
  nombre,
  portee,
  duree,
  delai = 0,
  boucle = false,
}: {
  nombre: number;
  portee: number;
  duree: number;
  delai?: number;
  boucle?: boolean;
}) {
  return (
    <span aria-hidden="true" className="pointer-events-none absolute top-1/2 left-1/2">
      {Array.from({ length: nombre }, (_, i) => (
        <span
          key={i}
          style={
            {
              "--a": `${(360 / nombre) * i}deg`,
              "--dist": `${portee}px`,
              animation: `simtis-etincelle ${duree}s ease-out ${delai}s ${boucle ? "infinite" : "1 both"}`,
            } as CSSProperties
          }
          className={cn(
            "absolute -top-1 -left-1 block size-2 rounded-full opacity-0",
            COULEURS_CONFETTI[i % COULEURS_CONFETTI.length],
          )}
        />
      ))}
    </span>
  );
}

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

/** Ballon qui monte ; un clic le fait éclater, il revient au cycle suivant. */
function BallonMontant({ ballon }: { ballon: (typeof BALLONS)[number] }) {
  const [eclate, setEclate] = useState(false);
  return (
    <div
      style={
        {
          left: `${ballon.gauche}%`,
          "--d": `${ballon.duree}s`,
          "--r": `${ballon.delai}s`,
        } as CSSProperties
      }
      onAnimationIteration={(event) => {
        if (event.target === event.currentTarget) setEclate(false);
      }}
      className="absolute -bottom-40 animate-[simtis-ballon-monte_var(--d)_ease-in_var(--r)_infinite] opacity-0 motion-reduce:bottom-4 motion-reduce:animate-none motion-reduce:opacity-100"
    >
      {eclate ? (
        <div
          className="relative"
          style={{ width: ballon.taille, height: ballon.taille * 1.8 }}
          aria-hidden="true"
        >
          <Eclat nombre={12} portee={ballon.taille} duree={0.6} />
        </div>
      ) : (
        <button
          type="button"
          tabIndex={-1}
          aria-hidden="true"
          onClick={() => setEclate(true)}
          className="cursor-pointer transition-transform duration-150 hover:scale-110"
        >
          <Ballon taille={ballon.taille} className={ballon.couleur} />
        </button>
      )}
    </div>
  );
}

/** Titre dont les lettres sautillent en vague ; lu en entier par les lecteurs d'écran. */
function TitreQuiDanse({ texte }: { texte: string }) {
  const mots = texte.split(" ");
  let rang = 0;
  return (
    <h1
      aria-label={texte}
      className="mt-2 text-4xl font-bold text-simtis-fete-rose-fonce sm:text-5xl"
    >
      {mots.map((mot, m) => (
        <span key={m} aria-hidden="true" className="inline-block whitespace-nowrap">
          {Array.from(mot).map((lettre) => {
            const numero = rang++;
            return (
              <span
                key={numero}
                style={{ animationDelay: `${numero * 0.07}s` }}
                className="inline-block animate-[simtis-lettre-saute_1.6s_ease-in-out_infinite]"
              >
                {lettre}
              </span>
            );
          })}
          {m < mots.length - 1 && <span className="inline-block w-[0.3em]" />}
        </span>
      ))}
    </h1>
  );
}

/** Gâteau à 3 bougies : un clic souffle les bougies et lance des confettis. */
function Gateau() {
  const [souffle, setSouffle] = useState(false);
  const bougies = [44, 70, 96];
  return (
    <button
      type="button"
      onClick={() => setSouffle(true)}
      disabled={souffle}
      aria-label={souffle ? "Bougies soufflées" : "Souffler les bougies"}
      title={souffle ? undefined : "Souffle les bougies !"}
      className="relative mx-auto block cursor-pointer disabled:cursor-default"
    >
      <svg width="140" height="120" viewBox="0 0 140 120" aria-hidden="true">
        {bougies.map((x, i) => (
          <g key={x}>
            <rect
              x={x - 3}
              y="22"
              width="6"
              height="26"
              rx="2"
              className={i === 1 ? "fill-simtis-secondary" : "fill-simtis-fete-rose"}
            />
            {!souffle && (
              <g
                style={{ transformOrigin: `${x}px 20px`, animationDelay: `${i * 0.15}s` }}
                className="animate-[simtis-flamme_0.5s_ease-in-out_infinite]"
              >
                <ellipse cx={x} cy="12" rx="5" ry="9" className="fill-simtis-warning" />
                <ellipse cx={x} cy="15" rx="2.5" ry="5" className="fill-simtis-fete-flamme" />
              </g>
            )}
          </g>
        ))}
        <rect x="30" y="46" width="80" height="28" rx="6" className="fill-simtis-fete-rose" />
        <path
          d="M30 54 Q40 62 50 54 Q60 62 70 54 Q80 62 90 54 Q100 62 110 54 L110 50 L30 50 Z"
          className="fill-simtis-card"
        />
        <rect
          x="14"
          y="72"
          width="112"
          height="38"
          rx="8"
          className="fill-simtis-fete-rose-fonce"
        />
        <path
          d="M14 82 Q28 92 42 82 Q56 92 70 82 Q84 92 98 82 Q112 92 126 82 L126 78 L14 78 Z"
          className="fill-simtis-fete-rose-bg"
        />
        {[30, 55, 85, 110].map((x) => (
          <circle key={x} cx={x} cy="98" r="3" className="fill-simtis-warning" />
        ))}
        <rect x="4" y="108" width="132" height="6" rx="3" className="fill-simtis-border" />
      </svg>
      {souffle && (
        <span className="absolute inset-x-0 top-4 h-0">
          <Eclat nombre={18} portee={90} duree={1.2} />
        </span>
      )}
    </button>
  );
}

type EtatSon = "chargement" | "joue" | "bloque" | "coupe" | "absent";

/** Joue la chanson en boucle pendant l'écran ; s'arrête quand l'écran se ferme. */
function useChanson() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [etat, setEtat] = useState<EtatSon>("chargement");

  useEffect(() => {
    const audio = new Audio(CHANSON);
    audio.loop = true;
    audioRef.current = audio;
    audio.addEventListener("error", () => setEtat("absent"));
    audio
      .play()
      .then(() => setEtat("joue"))
      .catch((erreur: unknown) => {
        // Lecture refusée sans clic (session restaurée au chargement) : bouton « Activer le son »
        if (erreur instanceof DOMException && erreur.name === "NotAllowedError") {
          setEtat("bloque");
        } else {
          setEtat("absent");
        }
      });
    return () => {
      audio.pause();
      audioRef.current = null;
    };
  }, []);

  const activer = () => {
    audioRef.current
      ?.play()
      .then(() => setEtat("joue"))
      .catch(() => setEtat("absent"));
  };

  const basculer = () => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = !audio.muted;
    setEtat(audio.muted ? "coupe" : "joue");
  };

  return { etat, activer, basculer };
}

function BoutonSon({
  etat,
  activer,
  basculer,
}: {
  etat: EtatSon;
  activer: () => void;
  basculer: () => void;
}) {
  if (etat === "absent" || etat === "chargement") return null;
  const bloque = etat === "bloque";
  const Icone = etat === "coupe" ? VolumeX : Volume2;
  return (
    <button
      type="button"
      onClick={bloque ? activer : basculer}
      className={cn(
        "absolute top-4 right-4 z-10 inline-flex items-center gap-2 rounded-full bg-simtis-card px-4 py-2 text-sm font-semibold text-simtis-fete-rose-fonce shadow-simtis-hover transition-transform duration-150 hover:scale-105",
        bloque && "animate-bounce",
      )}
    >
      <Icone className="size-4" aria-hidden="true" />
      {bloque ? "Activer le son" : etat === "coupe" ? "Remettre le son" : "Couper le son"}
    </button>
  );
}

function Celebration({ onFermer }: { onFermer: () => void }) {
  const son = useChanson();

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
      <BoutonSon {...son} />

      {FEUX.map((f, i) => (
        <div
          key={`f${i}`}
          aria-hidden="true"
          style={{ top: `${f.haut}%`, left: `${f.gauche}%` }}
          className="absolute size-0 motion-reduce:hidden"
        >
          <Eclat nombre={14} portee={70 + (i % 3) * 20} duree={2.2} delai={f.delai} boucle />
        </div>
      ))}

      {CONFETTIS.map((c, i) => (
        <span
          key={`c${i}`}
          aria-hidden="true"
          style={
            { left: `${c.gauche}%`, "--d": `${c.duree}s`, "--r": `${c.delai}s` } as CSSProperties
          }
          className={cn(
            "pointer-events-none absolute top-0 block h-3 w-2 animate-[simtis-confetti-tombe_var(--d)_linear_var(--r)_infinite] motion-reduce:hidden",
            c.rond && "h-2.5 w-2.5 rounded-full",
            c.couleur,
          )}
        />
      ))}

      {BALLONS.map((b, i) => (
        <BallonMontant key={`b${i}`} ballon={b} />
      ))}

      <div className="pointer-events-none relative flex h-full items-center justify-center p-4">
        <div className="pointer-events-auto max-w-2xl animate-[simtis-fete-apparait_900ms_ease-out_both] rounded-[18px] bg-simtis-card px-6 py-8 text-center shadow-simtis-hover sm:px-12">
          <div className="mb-2 flex items-end justify-center gap-4 text-simtis-fete-rose-fonce">
            <PartyPopper className="mb-2 size-9" aria-hidden="true" />
            <Gateau />
            <Gift className="mb-2 size-9" aria-hidden="true" />
          </div>
          <p className="text-lg font-medium text-simtis-muted">Happy birthday to you</p>
          <TitreQuiDanse texte={`Joyeux anniversaire ${ANNIVERSAIRE.prenom} !`} />
          <p className="mt-3 text-2xl font-semibold text-simtis-primary-dark">
            Happy birthday dear {ANNIVERSAIRE.prenom}
          </p>
          <p className="mt-6 text-simtis-text">
            Toute l&apos;équipe SIMTIS te souhaite une merveilleuse journée.
          </p>
          <p className="mt-1 text-xs text-simtis-muted">
            Souffle les bougies et éclate les ballons !
          </p>
          <button
            type="button"
            onClick={onFermer}
            className="mt-6 inline-flex items-center gap-2 rounded-[10px] bg-simtis-fete-rose-fonce px-5 py-2.5 text-sm font-semibold text-simtis-card transition-opacity duration-150 hover:opacity-90"
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
