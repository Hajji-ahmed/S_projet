import { describe, expect, it } from "vitest";

import {
  blocageImport,
  cellulesText,
  defaultChecked,
  pageOf,
  sageLinesFor,
  toggleVue,
} from "./importLines";

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
    const gardees = new Set([3, 4, 5]);
    expect(sageLinesFor(lines, "toutes", gardees).map((l) => l.numero)).toEqual([3, 4, 5, 6]);
    expect(sageLinesFor(lines, "importer", gardees).map((l) => l.numero)).toEqual([3, 4, 5]);
    expect(sageLinesFor(lines, "erreurs", gardees).map((l) => l.numero)).toEqual([4]);
    expect(sageLinesFor(lines, "doublons", gardees).map((l) => l.numero)).toEqual([5, 6]);
    expect(sageLinesFor(lines, "ignorees", gardees)).toEqual([]);
  });

  it("une ligne en erreur décochée disparaît du filtre des erreurs", () => {
    expect(sageLinesFor(lines, "erreurs", new Set([3, 5]))).toEqual([]);
    expect(sageLinesFor(lines, "toutes", new Set([3, 5])).map((l) => l.numero)).toEqual([
      3, 4, 5, 6,
    ]);
  });
});

describe("defaultChecked", () => {
  it("coche les lignes valides, en erreur et les doublons internes, jamais une ligne déjà importée", () => {
    const lines = [
      { numero: 3, statut: "Valide", doublon_de: null },
      { numero: 4, statut: "Erreur", doublon_de: null },
      { numero: 5, statut: "Doublon", doublon_de: 3 },
      { numero: 6, statut: "Doublon", doublon_de: null },
    ];
    expect([...defaultChecked(lines)]).toEqual([3, 4, 5]);
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

describe("blocageImport", () => {
  const ok = { dejaImporte: false, cochees: 3, erreursCochees: 0, ouvertureManquante: false };

  it("ne bloque rien quand tout est prêt", () => {
    expect(blocageImport(ok)).toBeNull();
  });

  it("donne la première raison qui bloque", () => {
    expect(blocageImport({ ...ok, dejaImporte: true, cochees: 0 })?.raison).toBe("deja_importe");
    expect(blocageImport({ ...ok, cochees: 0, erreursCochees: 2 })?.raison).toBe("aucune");
    expect(blocageImport({ ...ok, erreursCochees: 2, ouvertureManquante: true })).toEqual({
      raison: "erreurs",
      message: "2 lignes cochées en erreur : corrigez-les ou décochez-les.",
    });
    expect(blocageImport({ ...ok, ouvertureManquante: true })?.raison).toBe("ouverture");
  });

  it("renvoie vers Sage pour corriger une écriture", () => {
    expect(blocageImport({ ...ok, erreursCochees: 1, correction: "Sage" })?.message).toBe(
      "1 ligne cochée en erreur : corrigez l'export dans Sage ou décochez-la.",
    );
  });
});
