import { describe, expect, it } from "vitest";

import { brouillonDe, nombreSaisi, reglesModifiees } from "@/lib/parametres";
import type { Regle } from "@/types/parametres";

const regles: Regle[] = [
  {
    id: 1,
    code: "DATE",
    libelle: "Date",
    genre: "critere",
    poids: "30.00",
    tolerance: "3.000000",
    actif: true,
    updated_at: "",
  },
  {
    id: 2,
    code: "SEUIL_FORT",
    libelle: "Fort",
    genre: "seuil",
    poids: "80.00",
    tolerance: null,
    actif: true,
    updated_at: "",
  },
];

describe("paramètres", () => {
  it("affiche les nombres sans zéros inutiles", () => {
    expect(nombreSaisi("80.00")).toBe("80");
    expect(nombreSaisi("12.50")).toBe("12.5");
    expect(nombreSaisi("3.000000")).toBe("3");
    expect(nombreSaisi("100")).toBe("100");
    expect(nombreSaisi(null)).toBe("");
  });

  it("n'envoie que les règles modifiées", () => {
    const brouillon = brouillonDe(regles);
    expect(reglesModifiees(regles, brouillon)).toEqual([]);

    brouillon[1] = { ...brouillon[1], poids: "85" };
    expect(reglesModifiees(regles, brouillon).map((r) => r.code)).toEqual(["SEUIL_FORT"]);

    brouillon[0] = { ...brouillon[0], actif: false };
    expect(reglesModifiees(regles, brouillon)).toHaveLength(2);
  });
});
