/**
 * Barre de navigation réduite (icônes seules) ou agrandie, au choix de l'utilisateur sur grand écran
 * (décision du 08/10/2026). Le choix est mémorisé dans le navigateur ; si ce stockage est
 * indisponible (navigation privée, données bloquées), il vaut pour la visite en cours seulement.
 * À lire avec `useSyncExternalStore(subscribe, isCollapsed, () => false)`.
 */
const KEY = "simtis.menu.reduit";
const listeners = new Set<() => void>();
// Dernier choix de la visite : il l'emporte sur le stockage, qui peut être indisponible
let choix: boolean | null = null;

function stored(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function isCollapsed(): boolean {
  return choix ?? stored();
}

export function setCollapsed(value: boolean): void {
  choix = value;
  try {
    window.localStorage.setItem(KEY, value ? "1" : "0");
  } catch {
    // Stockage indisponible : le choix vaut pour la visite en cours
  }
  listeners.forEach((listener) => listener());
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Un choix fait dans un autre onglet s'applique aussi ici
  const onStorage = (event: StorageEvent) => {
    if (event.key === KEY) {
      choix = null;
      listener();
    }
  };
  if (typeof window !== "undefined") window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    if (typeof window !== "undefined") window.removeEventListener("storage", onStorage);
  };
}
