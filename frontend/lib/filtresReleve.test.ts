import { describe, expect, it } from "vitest";

import {
  colonnesFiltreesReleve,
  filtrerOperations,
  FILTRES_RELEVE_VIDES,
  type LigneFiltrable,
} from "@/lib/filtresReleve";

function ligne(modif: Partial<LigneFiltrable> & { id: number }): LigneFiltrable {
  return {
    libelle: "VIREMENT",
    reference: null,
    pointage: "Encaissement",
    debit: "0.00",
    credit: "100.00",
    statut: "Non rapprochée",
    ...modif,
  };
}

const LIGNES = [
  ligne({
    id: 1,
    libelle: "Frais tenue de compte",
    pointage: "Frais bancaires",
    debit: "12.00",
    credit: "0.00",
  }),
  ligne({ id: 2, libelle: "VIR RECU SOCIÉTÉ", credit: "12500.50", statut: "Rapprochée" }),
  ligne({
    id: 3,
    libelle: "CHEQUE",
    reference: "CHQ 4521",
    pointage: null,
    debit: "500.00",
    credit: "0.00",
    statut: "À vérifier",
  }),
  ligne({ id: 4, libelle: "Remise LCN", credit: "500.00" }),
];

const ids = (lignes: readonly LigneFiltrable[]) => lignes.map((l) => l.id);

describe("filtrerOperations", () => {
  it("garde toutes les lignes sans filtre", () => {
    expect(ids(filtrerOperations(LIGNES, FILTRES_RELEVE_VIDES))).toEqual([1, 2, 3, 4]);
  });

  it("cherche dans le libellé sans tenir compte des majuscules ni des accents", () => {
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, q: "societe" }))).toEqual([2]);
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, q: "FRAIS" }))).toEqual([1]);
  });

  it("cherche aussi dans la référence", () => {
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, q: "4521" }))).toEqual([3]);
  });

  it("cherche dans le pointage sans tenir compte des majuscules ni des accents", () => {
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, pointage: "frais" }))).toEqual([
      1,
    ]);
    expect(
      ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, pointage: " ENCAISS " })),
    ).toEqual([2, 4]);
  });

  it("trouve les lignes sans pointage par « À choisir »", () => {
    expect(
      ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, pointage: "a choisir" })),
    ).toEqual([3]);
  });

  it("filtre un montant exact au centime, débit ou crédit", () => {
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, exact: "12500.50" }))).toEqual([
      2,
    ]);
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, exact: "500" }))).toEqual([
      3, 4,
    ]);
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, exact: "12500.5" }))).toEqual([
      2,
    ]);
  });

  it("filtre une fourchette, bornes comprises", () => {
    expect(
      ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, min: "100", max: "500" })),
    ).toEqual([3, 4]);
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, min: "501" }))).toEqual([2]);
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, max: "12" }))).toEqual([1]);
  });

  it("ignore la fourchette quand un montant exact est saisi", () => {
    expect(
      ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, exact: "12.00", min: "100" })),
    ).toEqual([1]);
  });

  it("limite le montant au sens choisi", () => {
    expect(
      ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, sens: "Débit", exact: "500" })),
    ).toEqual([3]);
    expect(
      ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, sens: "Crédit", exact: "500" })),
    ).toEqual([4]);
    expect(ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, sens: "Débit" }))).toEqual([
      1, 3,
    ]);
  });

  it("compte « À vérifier » comme « Non rapprochée »", () => {
    expect(
      ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, statut: "Non rapprochée" })),
    ).toEqual([1, 3, 4]);
    expect(
      ids(filtrerOperations(LIGNES, { ...FILTRES_RELEVE_VIDES, statut: "Rapprochée" })),
    ).toEqual([2]);
  });

  it("combine les filtres", () => {
    expect(
      ids(
        filtrerOperations(LIGNES, {
          ...FILTRES_RELEVE_VIDES,
          pointage: "Encaissement",
          exact: "500",
          statut: "Non rapprochée",
        }),
      ),
    ).toEqual([4]);
  });
});

describe("colonnesFiltreesReleve", () => {
  it("n'allume aucun entonnoir sans filtre", () => {
    expect(colonnesFiltreesReleve(FILTRES_RELEVE_VIDES)).toEqual({
      pointage: false,
      libelle: false,
      debit: false,
      credit: false,
      statut: false,
    });
  });

  it("allume Débit et Crédit pour un montant sans sens, une seule colonne avec un sens", () => {
    const deux = colonnesFiltreesReleve({ ...FILTRES_RELEVE_VIDES, min: "10" });
    expect([deux.debit, deux.credit]).toEqual([true, true]);
    const debit = colonnesFiltreesReleve({ ...FILTRES_RELEVE_VIDES, sens: "Débit" });
    expect([debit.debit, debit.credit]).toEqual([true, false]);
  });

  it("allume Pointage, Libellé et Statut", () => {
    const allumees = colonnesFiltreesReleve({
      ...FILTRES_RELEVE_VIDES,
      pointage: "choisir",
      q: "CHQ",
      statut: "Rapprochée",
    });
    expect([allumees.pointage, allumees.libelle, allumees.statut]).toEqual([true, true, true]);
  });
});
