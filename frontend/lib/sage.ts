/**
 * « Récupérer le GL » depuis la base Sage (21/11/2026) : période, cases cochées par défaut et
 * comptes à valider. Fonctions pures.
 */

import { defaultChecked } from "@/lib/importLines";

/** Période proposée : du 1er du mois en cours à aujourd'hui (dates « AAAA-MM-JJ »). */
export function periodeParDefaut(today: string): { du: string; au: string } {
  return { du: `${today.slice(0, 8)}01`, au: today };
}

/**
 * Date de la copie de la base Sage, telle qu'elle est écrite dans la base (heure du serveur Sage,
 * sans fuseau) : « 2026-11-21T00:33:00.113 » → « 21/11/2026 à 00:33 ». Sans objet Date : aucun
 * décalage de fuseau.
 */
export function formatCopie(iso: string | null): string | null {
  const match = iso?.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!match) return null;
  const [, year, month, day, hour, minute] = match;
  return `${day}/${month}/${year} à ${hour}:${minute}`;
}

type Ligne = { numero: number; statut: string; doublon_de: number | null; piece_repetee?: boolean };

/**
 * Cases cochées par défaut : les nouvelles lignes. Ni les lignes déjà importées (jamais
 * cochables) ni les erreurs, qui se corrigent dans Sage : cochée, une erreur bloquerait la
 * validation du compte.
 */
export function cochesParDefaut(lignes: readonly Ligne[]): Set<number> {
  const erreurs = new Set(lignes.filter((l) => l.statut === "Erreur").map((l) => l.numero));
  return new Set([...defaultChecked(lignes)].filter((numero) => !erreurs.has(numero)));
}

/** Comptes que « Tout valider » importe : pas encore importés, sans blocage, dans l'ordre. */
export function comptesAValider<T extends { bank_account_id: number }>(
  comptes: readonly T[],
  etat: ReadonlyMap<number, { importe: boolean; bloque: boolean }>,
): T[] {
  return comptes.filter((compte) => {
    const item = etat.get(compte.bank_account_id);
    return !!item && !item.importe && !item.bloque;
  });
}
