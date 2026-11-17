import { describe, expect, it } from "vitest";

import { codeDepuisNom, nomPropre, validateSocieteForm } from "@/lib/societes";

describe("codeDepuisNom", () => {
  it("retire les accents, les espaces et la ponctuation, en majuscules", () => {
    expect(codeDepuisNom("Société Atlas")).toBe("SOCIETEATL");
    expect(codeDepuisNom("Tefil")).toBe("TEFIL");
    expect(codeDepuisNom("  l'Étoile & Co 2  ")).toBe("LETOILECO2");
  });

  it("donne une chaîne vide sans lettre ni chiffre", () => {
    expect(codeDepuisNom(" -- ")).toBe("");
  });
});

describe("validateSocieteForm", () => {
  it("accepte un nom et un code valides", () => {
    expect(validateSocieteForm({ code: "atlas", nom: "Atlas" }, "create")).toEqual({});
  });

  it("exige le nom", () => {
    expect(validateSocieteForm({ code: "ATLAS", nom: "   " }, "create").nom).toBeDefined();
  });

  it("refuse un code trop court ou avec un espace", () => {
    expect(validateSocieteForm({ code: "A", nom: "Atlas" }, "create").code).toBeDefined();
    expect(validateSocieteForm({ code: "AT LAS", nom: "Atlas" }, "create").code).toBeDefined();
    expect(
      validateSocieteForm({ code: "X".repeat(21), nom: "Atlas" }, "create").code,
    ).toBeDefined();
  });

  it("ne contrôle pas le code d'une société existante (non modifiable)", () => {
    expect(validateSocieteForm({ code: "", nom: "Tefil SA" }, "edit")).toEqual({});
  });
});

describe("nomPropre", () => {
  it("réduit les espaces", () => {
    expect(nomPropre("  Société   Atlas ")).toBe("Société Atlas");
  });
});
