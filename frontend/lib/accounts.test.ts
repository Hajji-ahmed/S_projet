import { describe, expect, it } from "vitest";

import {
  amountForInput,
  formatPercent,
  normalizeAmountInput,
  normalizeNumero,
  normalizePercentInput,
  validateAccountForm,
  type AccountFormValues,
  finNumero,
} from "./accounts";

const valid: AccountFormValues = {
  bank_id: "4",
  devise: "MAD",
  type_compte: "Courant",
  libelle: "Compte courant",
  numero: "230 780 0001234567890123 45",
  compte_comptable: "5141",
  journal_sage: "",
  journal_frais: "",
  compte_timbre: "",
  compte_commission: "",
  compte_commission_effet: "",
  compte_tva: "",
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

  it("refuse un journal Sage avec un tiret ou trop long, accepte « bq1 »", () => {
    expect(
      validateAccountForm({ ...valid, journal_sage: "BQ-1" }, "create").journal_sage,
    ).toBeDefined();
    expect(
      validateAccountForm({ ...valid, journal_sage: "TROPLONGJOURNAL" }, "create").journal_sage,
    ).toBeDefined();
    expect(validateAccountForm({ ...valid, journal_sage: " bq1 " }, "create")).toEqual({});
  });

  it("accepte plusieurs journaux séparés par des virgules", () => {
    expect(validateAccountForm({ ...valid, journal_sage: "5243, 5543" }, "create")).toEqual({});
    expect(
      validateAccountForm({ ...valid, journal_sage: "5243, 55-43" }, "create").journal_sage,
    ).toBeDefined();
  });

  it("accepte plusieurs comptes comptables, jusqu'à 9", () => {
    expect(
      validateAccountForm({ ...valid, compte_comptable: "51410000, 51410100" }, "create"),
    ).toEqual({});
    expect(
      validateAccountForm({ ...valid, compte_comptable: "5141, 51-42" }, "create").compte_comptable,
    ).toBeDefined();
    const dix = Array.from({ length: 10 }, (_, i) => `514${i}`).join(", ");
    expect(
      validateAccountForm({ ...valid, compte_comptable: dix }, "create").compte_comptable,
    ).toBeDefined();
  });

  it("accepte un taux vide et un compte comptable vide", () => {
    expect(validateAccountForm({ ...valid, taux: "", compte_comptable: "" }, "create")).toEqual({});
  });
});

describe("comptabilisation des droits de timbre", () => {
  it("le journal des frais est l'un des journaux Sage du compte", () => {
    const bp = { ...valid, journal_sage: "5243, 5543" };
    expect(validateAccountForm({ ...bp, journal_frais: "5543" }, "create")).toEqual({});
    expect(validateAccountForm({ ...bp, journal_frais: "9000" }, "create").journal_frais).toBe(
      "Doit être l'un des journaux Sage du compte.",
    );
    expect(
      validateAccountForm({ ...bp, compte_timbre: "6167-00" }, "create").compte_timbre,
    ).toBeDefined();
  });
});

describe("finNumero", () => {
  it("garde les 4 derniers caractères du numéro, sans les espaces", () => {
    expect(finNumero("230 780 0001234567890123 45")).toBe("…2345");
    expect(finNumero("RIB-USD-8830")).toBe("…8830");
    expect(finNumero("123")).toBe("123");
  });
});
