/**
 * Surprise d'anniversaire de Salma (24/11/2026) : réservée à son compte, ce jour-là à l'heure du Maroc.
 * Ponctuel : à retirer après la date, avec components/anniversaire/ et les tokens « fete ».
 */
export const ANNIVERSAIRE = {
  email: "simtis.jeid.s@softgroup.ma",
  prenom: "Salma",
  jour: "2026-11-24",
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
  return (
    email.trim().toLowerCase() === ANNIVERSAIRE.email &&
    jourAuMaroc(maintenant) === ANNIVERSAIRE.jour
  );
}

/** Clé qui retient que l'écran de 40 s est déjà passé ce jour-là. */
export const CLE_CELEBRATION_VUE = `simtis.anniversaire.${ANNIVERSAIRE.jour}.vue`;
