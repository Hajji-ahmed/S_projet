/** N° pièce des écritures de frais, donné à l'export vers Sage (09/11/2026).
 *
 * Copie de `frais_service.premiere_piece` : le comptable tape la première pièce de la banque et
 * du mois (« BP2610001 »), les suivantes se numérotent à la suite. Le serveur refait le contrôle. */

export const PIECE_MAX = 999;

/** « BP2610 » : code de la banque, année sur 2 chiffres et mois (« 2026-10 »). */
export function prefixePiece(banque: string, mois: string): string {
  return `${banque}${mois.slice(2, 4)}${mois.slice(5, 7)}`;
}

/** Le N° tel qu'il sera envoyé : sans espaces, en majuscules. */
export function normaliserPiece(texte: string): string {
  return texte.replace(/\s+/g, "").toUpperCase();
}

/** Message d'erreur du N° de la première pièce pour `nb` écritures, ou null s'il est bon. */
export function erreurPiece(
  texte: string,
  banque: string,
  mois: string,
  nb: number,
): string | null {
  const numero = normaliserPiece(texte);
  const prefixe = prefixePiece(banque, mois);
  const rang = numero.slice(prefixe.length);
  if (!numero.startsWith(prefixe) || !/^\d{3}$/.test(rang) || Number(rang) === 0) {
    return `Le N° s'écrit ${prefixe} suivi de 3 chiffres (ex. ${prefixe}001).`;
  }
  if (Number(rang) + nb - 1 > PIECE_MAX) {
    return `${nb} écriture${nb > 1 ? "s" : ""} à partir de ${numero} dépassent ${prefixe}${PIECE_MAX}.`;
  }
  return null;
}

/** Première et dernière pièce de la série (le N° doit être valide). */
export function seriePieces(texte: string, banque: string, mois: string, nb: number) {
  const numero = normaliserPiece(texte);
  const prefixe = prefixePiece(banque, mois);
  const rang = Number(numero.slice(prefixe.length));
  const piece = (n: number) => `${prefixe}${String(n).padStart(3, "0")}`;
  return { premiere: piece(rang), derniere: piece(rang + nb - 1) };
}

/** « octobre 2026 » pour « 2026-10 ». */
export function libelleMois(mois: string): string {
  const [annee, numero] = mois.split("-").map(Number);
  return new Intl.DateTimeFormat("fr-FR", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(annee, numero - 1, 1)));
}
