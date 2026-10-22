import { describe, expect, it } from "vitest";

import { formatAmount, formatCompact } from "./format";

describe("formatAmount", () => {
  it("sépare les milliers par une espace et ajoute la devise", () => {
    expect(formatAmount(2450000, "DH")).toBe("2 450 000 DH");
  });

  it("n'affiche pas de décimales pour un montant entier", () => {
    expect(formatAmount(1200)).toBe("1 200");
    expect(formatAmount("12500.00")).toBe("12 500");
  });

  it("affiche toujours 2 décimales quand il y a des centimes", () => {
    expect(formatAmount(12500.5)).toBe("12 500,50");
    expect(formatAmount("1234.56", "DH")).toBe("1 234,56 DH");
  });

  it("garde le signe des montants négatifs", () => {
    expect(formatAmount(-30000, "DH")).toBe("-30 000 DH");
  });

  it("affiche « - » pour une valeur absente ou non numérique", () => {
    expect(formatAmount(null)).toBe("-");
    expect(formatAmount(undefined, "DH")).toBe("-");
    expect(formatAmount("")).toBe("-");
    expect(formatAmount("abc")).toBe("-");
  });

  it("affiche 0 pour zéro, sauf avec dashForZero", () => {
    expect(formatAmount(0, "DH")).toBe("0 DH");
    expect(formatAmount(0, undefined, { dashForZero: true })).toBe("-");
    expect(formatAmount(50000, undefined, { dashForZero: true })).toBe("50 000");
  });

  it("n'utilise jamais d'espace insécable", () => {
    expect(formatAmount(1234567.89, "DH")).not.toMatch(/[  ]/);
  });
});

describe("formatCompact", () => {
  const sans = (texte: string) => texte.replace(/ /g, " ");

  it("raccourcit les grands montants pour les axes", () => {
    expect(sans(formatCompact(18_000_000))).toBe("18 M");
    expect(sans(formatCompact(1_500_000))).toBe("1,5 M");
    expect(sans(formatCompact(-250_400))).toBe("-250 k");
    expect(sans(formatCompact(2_300_000_000))).toBe("2,3 Md");
    expect(sans(formatCompact(840))).toBe("840");
    expect(sans(formatCompact("839889.38", "DH"))).toBe("840 k DH");
    expect(formatCompact(null)).toBe("-");
  });

  it("n'a que des espaces insécables, qu'un axe ne coupe pas", () => {
    expect(formatCompact(100_000_000, "DH")).not.toMatch(/ /);
  });
});
