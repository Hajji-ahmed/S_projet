import { describe, expect, it } from "vitest";

import { journauxDuCompte, montantsSaisis } from "./saisie";

describe("montantsSaisis (24/10/2026)", () => {
  it("place le montant exact du côté choisi", () => {
    expect(montantsSaisis("debit", "1 250,50")).toEqual({ debit: "1250.50", credit: null });
    expect(montantsSaisis("credit", "1000")).toEqual({ debit: null, credit: "1000" });
  });

  it("refuse un montant illisible ou nul", () => {
    expect(montantsSaisis("debit", "abc")).toBeNull();
    expect(montantsSaisis("credit", "0,00")).toBeNull();
    expect(montantsSaisis("credit", "")).toBeNull();
  });
});

describe("journauxDuCompte", () => {
  it("lit la liste des journaux Sage du compte", () => {
    expect(journauxDuCompte("5243,5543")).toEqual(["5243", "5543"]);
    expect(journauxDuCompte(null)).toEqual([]);
  });
});
