import { describe, expect, it } from "vitest";

import { erreurPiece, libelleMois, prefixePiece, seriePieces } from "@/lib/piece";

describe("N° de la première pièce à l'export (09/11/2026)", () => {
  it("se construit avec la banque, l'année et le mois", () => {
    expect(prefixePiece("BP", "2026-10")).toBe("BP2610");
    expect(prefixePiece("AWB", "2027-01")).toBe("AW2701");
  });

  it("accepte le N° complet, même en minuscules ou avec des espaces", () => {
    expect(erreurPiece("BP2610001", "BP", "2026-10", 12)).toBeNull();
    expect(erreurPiece(" bp2610045 ", "BP", "2026-10", 1)).toBeNull();
  });

  it.each([
    ["AWB2610001", "autre banque"],
    ["BP2611001", "autre mois"],
    ["BP261001", "2 chiffres"],
    ["BP26100001", "4 chiffres"],
    ["BP2610000", "pièce 000"],
    ["", "vide"],
  ])("refuse %s (%s)", (texte) => {
    expect(erreurPiece(texte, "BP", "2026-10", 1)).toBe(
      "Le N° s'écrit BP2610 suivi de 3 chiffres (ex. BP2610001).",
    );
  });

  it("écrit AW pour AWB, sans le B (19/11/2026)", () => {
    expect(erreurPiece("AW2610098", "AWB", "2026-10", 1)).toBeNull();
    expect(erreurPiece("AWB2610098", "AWB", "2026-10", 1)).toBe(
      "Le N° s'écrit AW2610 suivi de 3 chiffres (ex. AW2610001).",
    );
    expect(seriePieces("AW2610098", "AWB", "2026-10", 2)).toEqual({
      premiere: "AW2610098",
      derniere: "AW2610099",
    });
  });

  it.each([
    ["CIH", "CI"],
    ["BMCE", "BM"],
  ])("écrit %s en %s (19/11/2026)", (banque, prefixe) => {
    expect(prefixePiece(banque, "2026-10")).toBe(`${prefixe}2610`);
    expect(erreurPiece(`${prefixe}2610001`, banque, "2026-10", 1)).toBeNull();
    expect(erreurPiece(`${banque}2610001`, banque, "2026-10", 1)).toBe(
      `Le N° s'écrit ${prefixe}2610 suivi de 3 chiffres (ex. ${prefixe}2610001).`,
    );
  });

  it("refuse une série qui dépasse la pièce 999", () => {
    expect(erreurPiece("BP2610998", "BP", "2026-10", 2)).toBeNull();
    expect(erreurPiece("BP2610999", "BP", "2026-10", 2)).toBe(
      "2 écritures à partir de BP2610999 dépassent BP2610999.",
    );
  });

  it("donne la première et la dernière pièce de la série", () => {
    expect(seriePieces("bp2610009", "BP", "2026-10", 3)).toEqual({
      premiere: "BP2610009",
      derniere: "BP2610011",
    });
  });

  it("écrit le mois en toutes lettres", () => {
    expect(libelleMois("2026-10")).toBe("octobre 2026");
  });
});
