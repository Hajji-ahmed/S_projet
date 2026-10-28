import { describe, expect, it } from "vitest";

import { colonnesFiltrees, FILTRES_VIDES, filtresActifs } from "@/lib/reconciliation";

describe("colonnesFiltrees", () => {
  it("n'allume aucun entonnoir sans filtre", () => {
    expect(colonnesFiltrees(FILTRES_VIDES)).toEqual({
      date: false,
      libelle: false,
      debit: false,
      credit: false,
      statut: false,
    });
    expect(filtresActifs(FILTRES_VIDES)).toBe(false);
  });

  it("allume la Date pour une seule borne", () => {
    expect(colonnesFiltrees({ ...FILTRES_VIDES, au: "2026-10-20" }).date).toBe(true);
  });

  it("allume le Libellé pour la recherche ou le type", () => {
    expect(colonnesFiltrees({ ...FILTRES_VIDES, q: "CHEQUE" }).libelle).toBe(true);
    expect(colonnesFiltrees({ ...FILTRES_VIDES, typeOperation: "Effet" }).libelle).toBe(true);
  });

  it("allume seulement la colonne du sens choisi", () => {
    const debit = colonnesFiltrees({ ...FILTRES_VIDES, sens: "Débit" });
    expect([debit.debit, debit.credit]).toEqual([true, false]);
    const credit = colonnesFiltrees({ ...FILTRES_VIDES, sens: "Crédit" });
    expect([credit.debit, credit.credit]).toEqual([false, true]);
  });

  it("compte le statut comme un filtre actif", () => {
    expect(filtresActifs({ ...FILTRES_VIDES, statut: "Rapprochée" })).toBe(true);
  });
});
