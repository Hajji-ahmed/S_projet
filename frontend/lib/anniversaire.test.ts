import { describe, expect, it } from "vitest";

import { cleCelebrationVue, estAnniversaire, jourAuMaroc } from "@/lib/anniversaire";

// Midi UTC : la date au Maroc ne dépend pas de son décalage 2026 (UTC+0 ou UTC+1)
const LE_21 = new Date("2026-11-21T12:00:00Z");
const LE_23 = new Date("2026-11-23T12:00:00Z");
const LE_24 = new Date("2026-11-24T12:00:00Z");
const LE_25 = new Date("2026-11-25T12:00:00Z");

const SALMA = "simtis.jeid.s@softgroup.ma";
const AHMED = "simtis.hajji.a@softgroup.ma";

describe("jourAuMaroc", () => {
  it("donne la date au format AAAA-MM-JJ", () => {
    expect(jourAuMaroc(LE_24)).toBe("2026-11-24");
  });
});

describe("estAnniversaire", () => {
  it("s'affiche pour Salma le 24/11/2026 seulement", () => {
    expect(estAnniversaire(SALMA, LE_24)).toBe(true);
    expect(estAnniversaire("  Simtis.Jeid.S@softgroup.ma ", LE_24)).toBe(true);
    expect(estAnniversaire(SALMA, LE_21)).toBe(false);
    expect(estAnniversaire(SALMA, LE_23)).toBe(false);
    expect(estAnniversaire(SALMA, LE_25)).toBe(false);
  });

  it("s'affiche pour le compte de test le 21 et le 24", () => {
    expect(estAnniversaire(AHMED, LE_21)).toBe(true);
    expect(estAnniversaire(AHMED, LE_24)).toBe(true);
    expect(estAnniversaire(AHMED, LE_23)).toBe(false);
  });

  it("ne s'affiche pas pour un autre utilisateur", () => {
    expect(estAnniversaire("tresorerie.demo@example.com", LE_24)).toBe(false);
    expect(estAnniversaire("", LE_24)).toBe(false);
    expect(estAnniversaire(null, LE_24)).toBe(false);
  });
});

describe("cleCelebrationVue", () => {
  it("change chaque jour, pour que l'écran repasse le 24 après le test du 21", () => {
    expect(cleCelebrationVue(LE_21)).toBe("simtis.anniversaire.2026-11-21.vue");
    expect(cleCelebrationVue(LE_24)).not.toBe(cleCelebrationVue(LE_21));
  });
});
