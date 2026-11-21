import { describe, expect, it } from "vitest";

import { estAnniversaire, jourAuMaroc } from "@/lib/anniversaire";

// Midi UTC : la date au Maroc ne dépend pas de son décalage 2026 (UTC+0 ou UTC+1)
const LE_24 = new Date("2026-11-24T12:00:00Z");
const LE_23 = new Date("2026-11-23T12:00:00Z");
const LE_25 = new Date("2026-11-25T12:00:00Z");

describe("jourAuMaroc", () => {
  it("donne la date au format AAAA-MM-JJ", () => {
    expect(jourAuMaroc(LE_24)).toBe("2026-11-24");
  });
});

describe("estAnniversaire", () => {
  it("s'affiche pour Salma le 24/11/2026", () => {
    expect(estAnniversaire("simtis.jeid.s@softgroup.ma", LE_24)).toBe(true);
    expect(estAnniversaire("  Simtis.Jeid.S@softgroup.ma ", LE_24)).toBe(true);
  });

  it("ne s'affiche pas un autre jour", () => {
    expect(estAnniversaire("simtis.jeid.s@softgroup.ma", LE_23)).toBe(false);
    expect(estAnniversaire("simtis.jeid.s@softgroup.ma", LE_25)).toBe(false);
  });

  it("ne s'affiche pas pour un autre utilisateur", () => {
    expect(estAnniversaire("simtis.hajji.a@softgroup.ma", LE_24)).toBe(false);
    expect(estAnniversaire("", LE_24)).toBe(false);
    expect(estAnniversaire(null, LE_24)).toBe(false);
  });
});
