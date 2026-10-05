import { describe, expect, it } from "vitest";

import {
  businessToday,
  currencySuffix,
  formatDate,
  normalizeSignedAmountInput,
  validateBalanceForm,
  type BalanceFormValues,
} from "./balances";

const TODAY = "2026-10-01";
const valid: BalanceFormValues = {
  jour: TODAY,
  solde: "1 200 000",
  credit_utilise: "300 000",
  commentaire: "",
};

describe("businessToday", () => {
  it("donne la date au format AAAA-MM-JJ, calculée dans le fuseau du Maroc", () => {
    expect(businessToday(new Date("2026-09-30T12:00:00Z"))).toBe("2026-09-30");
    expect(businessToday(new Date("2026-12-31T12:00:00Z"))).toBe("2026-12-31");
  });
});

describe("formatDate", () => {
  it("affiche au format français sans décalage de fuseau", () => {
    expect(formatDate("2026-09-30")).toBe("30/09/2026");
    expect(formatDate(null)).toBe("-");
  });
});

describe("currencySuffix", () => {
  it("affiche DH pour le dirham", () => {
    expect(currencySuffix("MAD")).toBe("DH");
    expect(currencySuffix("EUR")).toBe("EUR");
  });
});

describe("normalizeSignedAmountInput", () => {
  it.each([
    ["1 200 000", "1200000"],
    ["-15 000,50", "-15000.50"],
    ["0", "0"],
  ])("%s → %s", (input, expected) => {
    expect(normalizeSignedAmountInput(input)).toBe(expected);
  });

  it.each(["--1", "1,234", "abc", ""])("refuse « %s »", (input) => {
    expect(normalizeSignedAmountInput(input)).toBeNull();
  });
});

describe("validateBalanceForm", () => {
  it("accepte une saisie complète", () => {
    expect(validateBalanceForm(valid, TODAY)).toEqual({});
  });

  it("accepte le solde seul ou le crédit utilisé seul", () => {
    expect(validateBalanceForm({ ...valid, credit_utilise: "" }, TODAY)).toEqual({});
    expect(validateBalanceForm({ ...valid, solde: "" }, TODAY)).toEqual({});
  });

  it("exige au moins un montant", () => {
    expect(
      validateBalanceForm({ ...valid, solde: "", credit_utilise: " " }, TODAY).global,
    ).toBeDefined();
  });

  it("refuse une date future, accepte une date passée", () => {
    expect(validateBalanceForm({ ...valid, jour: "2026-10-02" }, TODAY).jour).toBeDefined();
    expect(validateBalanceForm({ ...valid, jour: "2026-09-28" }, TODAY)).toEqual({});
  });

  it("refuse une date avant le 01/01/2000 (année mal saisie), comme l'API", () => {
    expect(validateBalanceForm({ ...valid, jour: "0026-09-30" }, TODAY).jour).toBe(
      "Impossible de saisir un solde avant le 01/01/2000 : vérifiez l'année.",
    );
    expect(validateBalanceForm({ ...valid, jour: "1999-12-31" }, TODAY).jour).toBeDefined();
    expect(validateBalanceForm({ ...valid, jour: "2000-01-01" }, TODAY)).toEqual({});
  });

  it("accepte un solde négatif mais pas un crédit utilisé négatif", () => {
    expect(validateBalanceForm({ ...valid, solde: "-5 000" }, TODAY)).toEqual({});
    expect(
      validateBalanceForm({ ...valid, credit_utilise: "-5" }, TODAY).credit_utilise,
    ).toBeDefined();
  });

  it("limite le commentaire à 500 caractères", () => {
    expect(
      validateBalanceForm({ ...valid, commentaire: "x".repeat(501) }, TODAY).commentaire,
    ).toBeDefined();
  });
});
