/**
 * Fonctions mises de côté. Remettre la valeur à `true` réactive la fonction à l'écran ; le backend,
 * la base et les tests restent en place.
 *
 * ECARTS_ACTIFS : la fonction Écarts (P12) est mise de côté le 07/10/2026 (décision du métier) :
 * plus de menu ni de page `/ecarts`, plus de bouton « Signaler un écart », plus de statut « Écart »
 * dans le filtre du rapprochement. Les écarts ouverts ont été clôturés (migration 0015).
 */
export const ECARTS_ACTIFS = false;
