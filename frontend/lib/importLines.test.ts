import { describe, expect, it } from "vitest";

import { cellulesText, pageOf, sageLinesFor, toggleVue } from "./importLines";

describe("toggleVue", () => {
  it("filtre sur la tuile cliquée, et réaffiche tout au second clic", () => {
    expect(toggleVue("toutes", "erreurs")).toBe("erreurs");
    expect(toggleVue("doublons", "erreurs")).toBe("erreurs");
    expect(toggleVue("erreurs", "erreurs")).toBe("toutes");
  });
});

describe("sageLinesFor", () => {
  const lines = [
    { numero: 3, statut: "Valide" },
    { numero: 4, statut: "Erreur" },
    { numero: 5, statut: "Doublon" },
    { numero: 6, statut: "Doublon" },
  ];

  it("garde les lignes de la tuile choisie", () => {
    const gardees = new Set([5]);
    expect(sageLinesFor(lines, "toutes", gardees).map((l) => l.numero)).toEqual([3, 4, 5, 6]);
    expect(sageLinesFor(lines, "importer", gardees).map((l) => l.numero)).toEqual([3, 5]);
    expect(sageLinesFor(lines, "erreurs", gardees).map((l) => l.numero)).toEqual([4]);
    expect(sageLinesFor(lines, "doublons", gardees).map((l) => l.numero)).toEqual([5, 6]);
    expect(sageLinesFor(lines, "ignorees", gardees)).toEqual([]);
  });
});

describe("cellulesText", () => {
  it("montre les cellules non vides d'une ligne ignorée", () => {
    expect(cellulesText(["", "", "TOTAL", "", "1000"])).toBe("TOTAL · 1000");
    expect(cellulesText([])).toBe("(ligne vide)");
  });
});

describe("pageOf", () => {
  const rows = Array.from({ length: 250 }, (_, index) => index + 1);

  it("découpe par pages de 100", () => {
    expect(pageOf(rows, 1)).toMatchObject({ page: 1, pages: 3 });
    expect(pageOf(rows, 1).rows).toHaveLength(100);
    expect(pageOf(rows, 3).rows).toEqual(Array.from({ length: 50 }, (_, index) => index + 201));
  });

  it("ramène une page hors bornes dans le fichier", () => {
    expect(pageOf(rows, 9).page).toBe(3);
    expect(pageOf(rows, 0).page).toBe(1);
    expect(pageOf([], 4)).toEqual({ rows: [], page: 1, pages: 1 });
  });
});
