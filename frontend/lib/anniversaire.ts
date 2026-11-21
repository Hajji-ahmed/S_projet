/**
 * Surprise d'anniversaire de Salma (24/11/2026) : réservée à son compte, ce jour-là à l'heure du Maroc.
 * Le compte d'Ahmed Hajji la voit aussi le 21/11 (test sur le serveur) et le 24/11.
 * Ponctuel : à retirer après la date, avec components/anniversaire/ et les tokens « fete ».
 */
export const ANNIVERSAIRE = {
  prenom: "Salma",
  /** Email de connexion → jours (AAAA-MM-JJ, heure du Maroc) où la surprise s'affiche. */
  destinataires: {
    "simtis.jeid.s@softgroup.ma": ["2026-11-24"],
    "simtis.hajji.a@softgroup.ma": ["2026-11-21", "2026-11-24"],
  } as Record<string, readonly string[]>,
} as const;

/** Durée de l'écran de célébration, en millisecondes. */
export const DUREE_CELEBRATION_MS = 40_000;

/** Date du jour au Maroc, au format AAAA-MM-JJ. */
export function jourAuMaroc(maintenant: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Casablanca",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(maintenant);
}

export function estAnniversaire(email: string | null | undefined, maintenant: Date): boolean {
  if (!email) return false;
  const jours = ANNIVERSAIRE.destinataires[email.trim().toLowerCase()];
  return jours?.includes(jourAuMaroc(maintenant)) ?? false;
}

/** Clé qui retient que l'écran de 40 s est déjà passé ce jour-là. */
export function cleCelebrationVue(maintenant: Date): string {
  return `simtis.anniversaire.${jourAuMaroc(maintenant)}.vue`;
}
