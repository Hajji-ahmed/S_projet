/** Historique (P16.2) : affichage des valeurs du journal. */
import type { ValeurJson } from "@/types/historique";

/** Une valeur enregistrée, lisible sur une ligne : listes séparées par des virgules, objets en
 * « clé : valeur », vide = « - ». Aucune conversion de montant (texte exact). */
export function valeurLisible(valeur: ValeurJson | undefined): string {
  if (valeur === null || valeur === undefined || valeur === "") return "-";
  if (typeof valeur === "boolean") return valeur ? "oui" : "non";
  if (Array.isArray(valeur)) return valeur.length ? valeur.map(valeurLisible).join(", ") : "-";
  if (typeof valeur === "object") {
    const entrees = Object.entries(valeur);
    return entrees.length
      ? entrees.map(([cle, v]) => `${cle} : ${valeurLisible(v)}`).join(" · ")
      : "-";
  }
  return String(valeur);
}

/** « fichier_nom » → « Fichier nom ». */
export function champLisible(champ: string): string {
  const texte = champ.replaceAll("_", " ");
  return texte.charAt(0).toUpperCase() + texte.slice(1);
}

/** Un filtre au moins est actif (la page ne compte pas). */
export function filtreActif(recherche: Record<string, string | number>): boolean {
  return Object.entries(recherche).some(([cle, valeur]) => cle !== "page" && valeur !== "");
}
