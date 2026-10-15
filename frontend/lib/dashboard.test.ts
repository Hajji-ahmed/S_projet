import { describe, expect, it } from "vitest";

import {
  formatVariation,
  jourCourt,
  libellePeriode,
  moisEnCours,
  partFrais,
  pourcentage,
  tendance,
} from "@/lib/dashboard";

describe("dashboard", () => {
  it("propose le mois en cours", () => {
    expect(moisEnCours("2026-10-14")).toEqual({ from: "2026-10-01", to: "2026-10-14" });
  });

  it("écrit une variation avec son signe", () => {
    expect(formatVariation("2.5")).toBe("+2,5 %");
    expect(formatVariation("-10.0")).toBe("-10,0 %");
    expect(formatVariation(null)).toBeNull();
    expect(tendance("-0.5")).toBe("down");
    expect(tendance("0.0")).toBe("up");
  });

  it("calcule des parts sans float", () => {
    expect(pourcentage(847, 865)).toBe(98);
    expect(pourcentage(1, 0)).toBe(0);
    expect(partFrais("60471.79", "216899.00")).toBe("27,9");
    expect(partFrais("10", "0")).toBe("0,0");
  });

  it("écrit les jours et la période à la française", () => {
    expect(jourCourt("2026-10-01")).toBe("1 oct.");
    expect(jourCourt("2026-02-28")).toBe("28 févr.");
    expect(libellePeriode("2026-10-01", "2026-10-14")).toBe("1 oct. 2026 - 14 oct. 2026");
    expect(libellePeriode("", "2026-10-14")).toBe("Choisir une période");
  });
});
