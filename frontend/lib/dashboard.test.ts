import { describe, expect, it } from "vitest";

import {
  bornesAxe,
  heureRelative,
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

describe("heureRelative", () => {
  const maintenant = Date.parse("2026-10-29T12:00:00Z");

  it("dit l'âge d'une action en minutes, heures puis jours", () => {
    expect(heureRelative("2026-10-29T11:59:30Z", maintenant)).toBe("à l'instant");
    expect(heureRelative("2026-10-29T11:55:00Z", maintenant)).toBe("il y a 5 min");
    expect(heureRelative("2026-10-29T09:00:00Z", maintenant)).toBe("il y a 3 h");
    expect(heureRelative("2026-10-28T10:00:00Z", maintenant)).toBe("hier");
    expect(heureRelative("2026-10-25T12:00:00Z", maintenant)).toBe("il y a 4 j");
  });
});

describe("bornesAxe", () => {
  it("encadre la série avec 10 % de marge, sans partir de 0", () => {
    expect(bornesAxe([60_000_000, null, 80_000_000])).toEqual([58_000_000, 82_000_000]);
  });

  it("garde une marge pour une série plate et rien pour une série vide", () => {
    expect(bornesAxe([1000, 1000])).toEqual([950, 1050]);
    expect(bornesAxe([null])).toBeNull();
  });
});
