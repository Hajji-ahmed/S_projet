import { apiFetch } from "@/lib/api";
import type { ModeleMapping, Regle, RegleInput } from "@/types/parametres";

export function getGrille() {
  return apiFetch<Regle[]>("/parametres/rapprochement");
}

/** Tout ou rien ; vaut pour le prochain lancement du moteur. */
export function saveGrille(regles: RegleInput[]) {
  return apiFetch<Regle[]>("/parametres/rapprochement", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ regles }),
  });
}

export function getMappings() {
  return apiFetch<ModeleMapping[]>("/parametres/mappings");
}

export function deleteMapping(id: number) {
  return apiFetch<void>(`/parametres/mappings/${id}`, { method: "DELETE" });
}
