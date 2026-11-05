/**
 * Tous les statuts affichables sous forme de badge.
 * - Rapprochement : Rapprochée, À vérifier, Non rapprochée
 * - Prévisions : Prévu, En attente, Réalisé, Reporté, Annulé
 * - Contrôle de solde : Conforme, Écart, À vérifier
 * - Référentiel (banques, comptes) : Actif, Inactif
 * - Lignes d'un import : Valide, Erreur, Doublon
 */
export const STATUSES = [
  "Rapprochée",
  "À vérifier",
  "Non rapprochée",
  "Écart",
  "Prévu",
  "En attente",
  "Réalisé",
  "Reporté",
  "Annulé",
  "Conforme",
  "Actif",
  "Inactif",
  "Valide",
  "Erreur",
  "Doublon",
] as const;

export type Status = (typeof STATUSES)[number];
