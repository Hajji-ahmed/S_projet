import { describe, expect, it } from "vitest";

import { champLisible, filtreActif, valeurLisible } from "@/lib/historique";

describe("historique", () => {
  it("affiche les valeurs enregistrées sans les transformer", () => {
    expect(valeurLisible("50000.00")).toBe("50000.00");
    expect(valeurLisible(null)).toBe("-");
    expect(valeurLisible(true)).toBe("oui");
    expect(valeurLisible(["audit.view", "dashboard.view"])).toBe("audit.view, dashboard.view");
    expect(valeurLisible({ commission: "55.00", tva: "5.50" })).toBe(
      "commission : 55.00 · tva : 5.50",
    );
    expect(valeurLisible([])).toBe("-");
  });

  it("rend les noms de champ lisibles", () => {
    expect(champLisible("fichier_nom")).toBe("Fichier nom");
  });

  it("détecte un filtre actif sans compter la page", () => {
    expect(filtreActif({ page: 3, action: "", from: "" })).toBe(false);
    expect(filtreActif({ page: 1, action: "connexion", from: "" })).toBe(true);
  });
});
