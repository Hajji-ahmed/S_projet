import { describe, expect, it } from "vitest";

import { formatAmount } from "./format";

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
