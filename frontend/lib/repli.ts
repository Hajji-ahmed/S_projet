/**
 * Carte repliable dont l'état est gardé dans le navigateur (26/10/2026), comme la barre latérale
 * (`lib/sidebar.ts`) : si le stockage est indisponible (navigation privée), le choix vaut pour la
 * visite en cours. À lire avec `useSyncExternalStore(subscribe, lire, () => defaut)`.
 */
export type Repli = {
  lire: () => boolean;
  ecrire: (ouverte: boolean) => void;
  subscribe: (listener: () => void) => () => void;
};

export function repli(cle: string, defaut = false): Repli {
  const listeners = new Set<() => void>();
  let choix: boolean | null = null;

  function stocke(): boolean {
    try {
      const valeur = window.localStorage.getItem(cle);
      return valeur === null ? defaut : valeur === "1";
    } catch {
      return defaut;
    }
  }

  return {
    lire: () => choix ?? stocke(),
    ecrire: (ouverte) => {
      choix = ouverte;
      try {
        window.localStorage.setItem(cle, ouverte ? "1" : "0");
      } catch {
        // Stockage indisponible : le choix vaut pour la visite en cours
      }
      listeners.forEach((listener) => listener());
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
