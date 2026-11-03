import { describe, expect, it } from "vitest";

import {
  basculerGroupe,
  blocageImport,
  totauxCoches,
  cellulesText,
  defaultChecked,
  pageOf,
  sageLinesFor,
  soldesApresImport,
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

describe("groupes de lignes", () => {
  it("coche ou décoche un groupe sans toucher aux autres lignes", () => {
    expect([...basculerGroupe(new Set([3, 5]), [5], false)]).toEqual([3]);
    expect([...basculerGroupe(new Set([3]), [5, 7], true)].sort()).toEqual([3, 5, 7]);
  });
});

describe("totauxCoches", () => {
  const lignes = [
    { numero: 1, debit: "15000000.00", credit: null },
    { numero: 2, debit: null, credit: "273412.92" },
    { numero: 3, debit: null, credit: "4397.13" },
    { numero: 4, debit: null, credit: null },
  ];

  it("additionne les lignes cochées et donne le solde débit − crédit", () => {
    expect(totauxCoches(lignes, new Set([1, 2, 3, 4]))).toEqual({
      debit: "15000000.00",
      credit: "277810.05",
      solde: "14722189.95",
    });
  });

  it("ignore les lignes décochées", () => {
    expect(totauxCoches(lignes, new Set([2]))).toEqual({
      debit: "0.00",
      credit: "273412.92",
      solde: "-273412.92",
    });
  });

  it("vaut zéro sans ligne cochée", () => {
    expect(totauxCoches(lignes, new Set())).toEqual({
      debit: "0.00",
      credit: "0.00",
      solde: "0.00",
    });
  });

  it("compte les centimes exactement", () => {
    const petites = [
      { numero: 1, debit: "0.10", credit: null },
      { numero: 2, debit: "0.20", credit: null },
    ];
    expect(totauxCoches(petites, new Set([1, 2])).solde).toBe("0.30");
  });
});

describe("soldesApresImport", () => {
  const comptes = [
    {
      bank_account_id: 1,
      bank_code: "BP",
      journal: "5243",
      date_solde: "2026-08-31",
      date_ouverture: "2026-01-01",
      solde_avant: "1000.00",
    },
    {
      bank_account_id: 2,
      bank_code: "AWB",
      journal: "5242",
      date_solde: "2026-08-31",
      date_ouverture: null,
      solde_avant: null,
    },
    {
      bank_account_id: 3,
      bank_code: "CIH",
      journal: "5548",
      date_solde: "2026-08-31",
      date_ouverture: "2026-12-31",
      solde_avant: null,
    },
  ];
  const lignes = [
    { numero: 1, bank_account_id: 1, date_ecriture: "2026-08-02", debit: "500.10", credit: null },
    { numero: 2, bank_account_id: 1, date_ecriture: "2026-08-03", debit: null, credit: "0.30" },
    { numero: 3, bank_account_id: 1, date_ecriture: "2026-01-01", debit: "99.00", credit: null },
    { numero: 4, bank_account_id: 2, date_ecriture: "2026-08-02", debit: "7.00", credit: null },
  ];

  it("ajoute au solde avant import les lignes cochées du compte, après l'ouverture", () => {
    const [bp] = soldesApresImport(comptes, lignes, new Set([1, 2, 3, 4]));
    expect(bp).toEqual({
      bank_account_id: 1,
      bank_code: "BP",
      journal: "5243",
      date: "2026-08-31",
      solde: "1499.80",
      raison: null,
    });
  });

  it("suit les cases : une ligne décochée ne compte plus", () => {
    expect(soldesApresImport(comptes, lignes, new Set([2]))[0].solde).toBe("999.70");
    expect(soldesApresImport(comptes, lignes, new Set())[0].solde).toBe("1000.00");
  });

  it("ne part jamais de 0 sans solde d'ouverture", () => {
    const [, awb, cih] = soldesApresImport(comptes, lignes, new Set([4]));
    expect([awb.solde, awb.raison]).toEqual([null, "ouverture"]);
    expect([cih.solde, cih.raison]).toEqual([null, "apres"]);
  });
});
