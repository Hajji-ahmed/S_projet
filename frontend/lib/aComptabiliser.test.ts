import { describe, expect, it, vi } from "vitest";

import { abonnerAComptabiliser, signalerAComptabiliser, texteBadge } from "@/lib/aComptabiliser";

describe("texteBadge", () => {
  it("cache le badge sans frais à comptabiliser", () => {
    expect(texteBadge(0)).toBeNull();
    expect(texteBadge(null)).toBeNull();
    expect(texteBadge(undefined)).toBeNull();
  });

  it("affiche le nombre jusqu'à 99, puis « 99+ »", () => {
    expect(texteBadge(5)).toBe("5");
    expect(texteBadge(99)).toBe("99");
    expect(texteBadge(120)).toBe("99+");
  });
});

describe("signalerAComptabiliser", () => {
  it("prévient les abonnés jusqu'à leur désabonnement", () => {
    const listener = vi.fn();
    const desabonner = abonnerAComptabiliser(listener);
    signalerAComptabiliser();
    expect(listener).toHaveBeenCalledTimes(1);
    desabonner();
    signalerAComptabiliser();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
