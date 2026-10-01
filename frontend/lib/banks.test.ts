import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { BANK_LOGOS, parseOrder, validateBankForm, type BankFormValues } from "./banks";

const valid: BankFormValues = { code: "CDM", nom: "Crédit du Maroc", logo: "", ordre: "" };

describe("validateBankForm", () => {
  it("accepte une banque valide, avec un code saisi en minuscules", () => {
    expect(validateBankForm({ ...valid, code: " cdm " }, "create")).toEqual({});
  });

  it.each([
    ["trop court", "A"],
    ["trop long", "TROPLONGCODE"],
    ["caractère interdit", "AB-C"],
    ["vide", ""],
  ])("refuse un code %s", (_label, code) => {
    expect(validateBankForm({ ...valid, code }, "create").code).toBeDefined();
  });

  it("ne vérifie pas le code en modification (il n'est pas modifiable)", () => {
    expect(validateBankForm({ ...valid, code: "" }, "edit").code).toBeUndefined();
  });

  it("refuse un nom vide ou trop court", () => {
    expect(validateBankForm({ ...valid, nom: "  " }, "create").nom).toBeDefined();
    expect(validateBankForm({ ...valid, nom: "X" }, "create").nom).toBeDefined();
  });

  it.each(["-1", "1000", "2.5", "abc"])("refuse l'ordre %s", (ordre) => {
    expect(validateBankForm({ ...valid, ordre }, "create").ordre).toBeDefined();
  });

  it("accepte un ordre vide à la création, mais pas en modification", () => {
    expect(validateBankForm({ ...valid, ordre: "" }, "create").ordre).toBeUndefined();
    expect(validateBankForm({ ...valid, ordre: "" }, "edit").ordre).toBeDefined();
  });

  it("refuse un logo hors de la liste", () => {
    expect(
      validateBankForm({ ...valid, logo: "https://exemple.com/x.png" }, "create").logo,
    ).toBeDefined();
  });
});

describe("parseOrder", () => {
  it("convertit le texte saisi", () => {
    expect(parseOrder(" 7 ")).toBe(7);
    expect(parseOrder("")).toBeNull();
  });
});

describe("BANK_LOGOS", () => {
  it("ne propose que des fichiers qui existent dans public/banques", () => {
    for (const logo of BANK_LOGOS) {
      const file = fileURLToPath(new URL(`../public${logo.value}`, import.meta.url));
      expect(existsSync(file), logo.value).toBe(true);
    }
  });
});
