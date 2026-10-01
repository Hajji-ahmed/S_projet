import { describe, expect, it } from "vitest";

import { DEFAULT_PATH, loginPathFor, safeNextPath } from "./redirect";

describe("safeNextPath", () => {
  it("suit un chemin interne, avec ses paramètres", () => {
    expect(safeNextPath("/ecarts?statut=ouvert")).toBe("/ecarts?statut=ouvert");
  });

  it.each([
    ["absent", null],
    ["vide", ""],
    ["adresse complète", "https://faux-simtis.com"],
    ["adresse sans protocole", "//faux-simtis.com/login"],
    ["barre oblique inversée", "/\\faux-simtis.com"],
    ["schéma javascript", "javascript:alert(1)"],
    ["chemin relatif", "dashboard"],
    ["retour à la ligne", "/dashboard\nSet-Cookie: x"],
    ["boucle vers la connexion", "/login"],
    ["boucle vers la connexion avec paramètres", "/login?next=/ecarts"],
  ])("refuse : %s", (_label, value) => {
    expect(safeNextPath(value)).toBe(DEFAULT_PATH);
  });
});

describe("loginPathFor", () => {
  it("mémorise la page demandée", () => {
    expect(loginPathFor("/ecarts?statut=ouvert")).toBe("/login?next=%2Fecarts%3Fstatut%3Douvert");
  });

  it("n'ajoute rien pour une page dangereuse", () => {
    expect(loginPathFor("//faux-simtis.com")).toBe("/login");
  });
});
