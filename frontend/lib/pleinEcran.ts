/**
 * Mode plein écran du rapprochement (27/10/2026) : le menu, l'en-tête et les compteurs sont
 * masqués pour laisser la place aux volets. Il n'est pas mémorisé : on retrouve la vue normale au
 * prochain chargement et en quittant la page. À lire avec
 * `useSyncExternalStore(subscribe, estPleinEcran, () => false)`.
 */
const listeners = new Set<() => void>();
let actif = false;

export function estPleinEcran(): boolean {
  return actif;
}

export function setPleinEcran(valeur: boolean): void {
  if (valeur === actif) return;
  actif = valeur;
  listeners.forEach((listener) => listener());
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
