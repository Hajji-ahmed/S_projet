import { describe, expect, it } from "vitest";

import { cochesParDefaut, comptesAValider, formatCopie, periodeParDefaut } from "./sage";

describe("periodeParDefaut", () => {
  it("va du 1er du mois à aujourd'hui", () => {
    expect(periodeParDefaut("2026-11-21")).toEqual({ du: "2026-11-01", au: "2026-11-21" });
    expect(periodeParDefaut("2026-12-01")).toEqual({ du: "2026-12-01", au: "2026-12-01" });
  });
});

describe("formatCopie", () => {
  it("garde l'heure écrite dans la base, sans fuseau", () => {
    expect(formatCopie("2026-11-21T00:33:00.113000")).toBe("21/11/2026 à 00:33");
    expect(formatCopie("2026-11-20T23:05:00")).toBe("20/11/2026 à 23:05");
  });

  it("ne montre rien sans date", () => {
    expect(formatCopie(null)).toBeNull();
    expect(formatCopie("")).toBeNull();
  });
});

describe("cochesParDefaut", () => {
  it("coche les nouvelles lignes, ni les doublons déjà importés ni les erreurs", () => {
    const lignes = [
      { numero: 2, statut: "Valide", doublon_de: null },
      { numero: 3, statut: "Doublon", doublon_de: null },
      { numero: 4, statut: "Erreur", doublon_de: null },
      { numero: 5, statut: "Valide", doublon_de: null },
      { numero: 6, statut: "Doublon", doublon_de: 5 },
    ];
    expect([...cochesParDefaut(lignes)].sort()).toEqual([2, 5, 6]);
  });

  it("laisse décochée une copie d'un frais SIMTIS", () => {
    const lignes = [{ numero: 2, statut: "Valide", doublon_de: null, piece_repetee: true }];
    expect(cochesParDefaut(lignes).size).toBe(0);
  });
});

describe("comptesAValider", () => {
  it("garde les comptes ni importés ni bloqués, dans l'ordre", () => {
    const comptes = [{ bank_account_id: 1 }, { bank_account_id: 2 }, { bank_account_id: 3 }];
    const etat = new Map([
      [1, { importe: false, bloque: false }],
      [2, { importe: true, bloque: false }],
      [3, { importe: false, bloque: true }],
    ]);
    expect(comptesAValider(comptes, etat)).toEqual([{ bank_account_id: 1 }]);
    expect(comptesAValider(comptes, new Map())).toEqual([]);
  });
});
