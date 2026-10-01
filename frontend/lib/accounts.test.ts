import { describe, expect, it } from "vitest";

import {
  amountForInput,
  formatPercent,
  normalizeAmountInput,
  normalizeNumero,
  normalizePercentInput,
  validateAccountForm,
  type AccountFormValues,
} from "./accounts";

const valid: AccountFormValues = {
  bank_id: "4",
  devise: "MAD",
  type_compte: "Courant",
  libelle: "Compte courant",
  numero: "230 780 0001234567890123 45",
  compte_comptable: "5141",
  credit_autorise: "500 000",
  taux: "4,5",
};

describe("normalizeAmountInput", () => {
  it.each([
    ["500 000", "500000"],
    ["500 000,50", "500000.50"],
    ["1 234 567,8", "1234567.8"],
    ["0", "0"],
    ["9999999999999999.99", "9999999999999999.99"], // 16 chiffres + 2 : le maximum, sans perte
  ])("%s → %s", (input, expected) => {
    expect(normalizeAmountInput(input)).toBe(expected);
  });

  it.each(["", "-5", "12,345", "1.2.3", "abc", "1e5", "12345678901234567"])(
    "refuse « %s »",
    (input) => {
      expect(normalizeAmountInput(input)).toBeNull();
    },
  );
});

describe("normalizePercentInput", () => {
  it.each([
    ["4,5", "4.5"],
    ["0", "0"],
    ["100", "100"],
    ["100,0000", "100.0000"],
    ["3,1415", "3.1415"],
  ])("%s → %s", (input, expected) => {
    expect(normalizePercentInput(input)).toBe(expected);
  });

  it.each(["100,01", "101", "-1", "4,12345", "abc", ""])("refuse « %s »", (input) => {
    expect(normalizePercentInput(input)).toBeNull();
  });
});

describe("affichage", () => {
  it("prépare un montant de l'API pour la saisie", () => {
    expect(amountForInput("500000.00")).toBe("500 000");
    expect(amountForInput("1234.50")).toBe("1 234,50");
  });

  it("affiche un taux en pourcentage", () => {
    expect(formatPercent("4.5")).toBe("4,5 %");
    expect(formatPercent(null)).toBe("-");
  });

  it("nettoie un numéro de compte", () => {
    expect(normalizeNumero(" 230 780 abc ")).toBe("230780ABC");
  });
});

describe("validateAccountForm", () => {
  it("accepte un compte valide", () => {
    expect(validateAccountForm(valid, "create")).toEqual({});
  });

  it("exige banque et devise à la création seulement", () => {
    expect(validateAccountForm({ ...valid, bank_id: "", devise: "" }, "create")).toMatchObject({
      bank_id: expect.any(String),
      devise: expect.any(String),
    });
    expect(validateAccountForm({ ...valid, bank_id: "" }, "edit").bank_id).toBeUndefined();
  });

  it("refuse un compte DH convertible hors MAD", () => {
    expect(
      validateAccountForm({ ...valid, type_compte: "DH convertible", devise: "EUR" }, "create")
        .type_compte,
    ).toBeDefined();
  });

  it.each([
    ["libelle", { libelle: " " }],
    ["numero", { numero: "AB" }],
    ["numero", { numero: "RIB/123456" }],
    ["compte_comptable", { compte_comptable: "51-41" }],
    ["credit_autorise", { credit_autorise: "" }],
    ["credit_autorise", { credit_autorise: "-1" }],
    ["taux", { taux: "120" }],
  ])("signale le champ %s", (field, over) => {
    expect(validateAccountForm({ ...valid, ...over }, "create")).toHaveProperty(field);
  });

  it("accepte un taux vide et un compte comptable vide", () => {
    expect(validateAccountForm({ ...valid, taux: "", compte_comptable: "" }, "create")).toEqual({});
  });
});
