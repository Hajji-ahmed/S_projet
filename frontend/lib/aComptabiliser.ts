/**
 * Page « À comptabiliser » (21/11/2026) : frais bancaires non rapprochés, à passer dans Sage.
 * Le menu affiche leur nombre pour la société active, toutes dates confondues.
 */

/** Texte du badge du menu : rien à 0 (ou inconnu), « 99+ » au-delà de 99. */
export function texteBadge(nombre: number | null | undefined): string | null {
  if (!nombre || nombre < 0) return null;
  return nombre > 99 ? "99+" : String(nombre);
}

// Une validation ou un export sur la page change le nombre : le menu le relit.
const listeners = new Set<() => void>();

export function abonnerAComptabiliser(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function signalerAComptabiliser(): void {
  listeners.forEach((listener) => listener());
}
