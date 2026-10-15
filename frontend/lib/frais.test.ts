import { describe, expect, it } from "vitest";

import { cleJour, selectionTimbres, sommeMontants, ventilerTva } from "@/lib/frais";
import type { PropositionTimbres } from "@/types/frais";

const jour = (bank_account_id: number, date: string, total: string, famille = "timbres") =>
  ({ famille, bank_account_id, date, total }) as PropositionTimbres;

describe("droits de timbre", () => {
  it("additionne exactement les jours cochés", () => {
    const items = [
      jour(3, "2026-04-23", "222.00"),
      jour(3, "2026-04-24", "0.10"),
      jour(4, "2026-04-23", "0.20"),
    ];
    const selection = new Set([cleJour(items[1]), cleJour(items[2])]);

    expect(selectionTimbres(items, selection)).toEqual({ nb: 2, total: "0.30" });
    expect(selectionTimbres(items, new Set())).toEqual({ nb: 0, total: "0.00" });
  });

  it("distingue les timbres et la COM d'un même jour", () => {
    const timbre = jour(3, "2026-04-23", "222.00");
    const com = jour(3, "2026-04-23", "66.00", "commissions");

    expect(cleJour(timbre)).not.toBe(cleJour(com));
    expect(selectionTimbres([timbre, com], new Set([cleJour(com)]))).toEqual({
      nb: 1,
      total: "66.00",
    });
  });
});

describe("comptabilisation manuelle", () => {
  it("sépare la TVA comme le serveur, et HT + TVA = total", () => {
    expect(ventilerTva("165.00", "10")).toEqual({ ht: "150.00", tva: "15.00" });
    expect(ventilerTva("100.00", "10")).toEqual({ ht: "90.91", tva: "9.09" });
    expect(ventilerTva("0.05", "20")).toEqual({ ht: "0.04", tva: "0.01" });
    expect(ventilerTva("110.00", "7,5")).toEqual({ ht: "102.33", tva: "7.67" });
  });

  it("refuse un taux invalide", () => {
    expect(ventilerTva("165.00", "")).toBeNull();
    expect(ventilerTva("165.00", "0")).toBeNull();
    expect(ventilerTva("165.00", "abc")).toBeNull();
    expect(ventilerTva("165.00", "120")).toBeNull();
  });

  it("additionne exactement des montants signés", () => {
    expect(sommeMontants(["-165.00", "-0.10", "0.05"])).toBe("-165.05");
  });
});
