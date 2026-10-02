import { describe, expect, it } from "vitest";

import type { Devises, Previsions } from "@/types/saisie";

import {
  cellKey,
  devisesToDraft,
  draftToDevisesInput,
  draftToPrevisionsInput,
  previsionsToDraft,
  sameDraft,
} from "./saisies";

const AWB = 1;
const BP = 3;

const devises: Devises = {
  company_id: 1,
  jour: "2026-09-30",
  lignes: [
    {
      ligne: "EUR",
      banques: [{ bank_id: AWB, montant: "1250000.50" }],
      total: null,
      depassement: "-200.00",
    },
    { ligne: "USD", banques: [], total: null, depassement: null },
    { ligne: "Exp DH convertible", banques: [], total: "999.00", depassement: null },
  ],
};

describe("devisesToDraft / draftToDevisesInput", () => {
  it("affiche les montants au format de saisie et laisse vides les cellules jamais saisies", () => {
    const draft = devisesToDraft(devises);

    expect(draft).toEqual({
      "EUR|1": "1 250 000,50",
      "EUR|depassement": "-200",
      "Exp DH convertible|total": "999",
    });
  });

  it("renvoie la grille complète, montants en texte exact", () => {
    const parsed = draftToDevisesInput(devisesToDraft(devises), [AWB, BP]);

    expect(parsed).toEqual({
      ok: true,
      value: {
        lignes: [
          {
            ligne: "EUR",
            banques: [{ bank_id: AWB, montant: "1250000.50" }],
            total: null,
            depassement: "-200",
          },
          { ligne: "USD", banques: [], total: null, depassement: null },
          { ligne: "Exp DH convertible", banques: [], total: "999", depassement: null },
        ],
      },
    });
  });

  it("n'envoie que les banques affichées, et accepte le signe moins typographique", () => {
    const draft = { "USD|3": "−15 000,5", "USD|99": "1" };

    const parsed = draftToDevisesInput(draft, [AWB, BP]);

    expect(parsed.ok && parsed.value.lignes[1].banques).toEqual([
      { bank_id: BP, montant: "-15000.5" },
    ]);
  });

  it("signale chaque cellule invalide", () => {
    const parsed = draftToDevisesInput({ "EUR|1": "abc", "USD|total": "1,234" }, [AWB]);

    expect(parsed).toEqual({ ok: false, invalid: ["EUR|1", "USD|total"] });
  });
});

const previsions: Previsions = {
  company_id: 1,
  jour: "2026-09-30",
  lignes: Array.from({ length: 14 }, (_, index) => ({
    ligne: index + 1,
    libelle: index === 0 ? "Client A" : null,
    banques: index === 0 ? [{ bank_id: BP, montant: "1000.00" }] : [],
  })),
  encaissement: "250000.00",
  escompte: null,
  douane: null,
};

describe("previsionsToDraft / draftToPrevisionsInput", () => {
  it("garde le libellé tel quel et les trois cellules de la journée", () => {
    expect(previsionsToDraft(previsions)).toEqual({
      "1|libelle": "Client A",
      "1|3": "1 000",
      encaissement: "250 000",
    });
  });

  it("renvoie les 14 lignes, un libellé blanc devenant vide", () => {
    const draft = { ...previsionsToDraft(previsions), [cellKey(2, "libelle")]: "   " };

    const parsed = draftToPrevisionsInput(draft, [AWB, BP]);

    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.value.lignes).toHaveLength(14);
    expect(parsed.value.lignes[0]).toEqual({
      ligne: 1,
      libelle: "Client A",
      banques: [{ bank_id: BP, montant: "1000" }],
    });
    expect(parsed.value.lignes[1]).toEqual({ ligne: 2, libelle: null, banques: [] });
    expect(parsed.value).toMatchObject({ encaissement: "250000", escompte: null, douane: null });
  });

  it("refuse un libellé de plus de 80 caractères et un montant invalide", () => {
    const parsed = draftToPrevisionsInput({ "4|libelle": "x".repeat(81), douane: "1.2.3" }, []);

    expect(parsed).toEqual({ ok: false, invalid: ["4|libelle", "douane"] });
  });
});

describe("sameDraft", () => {
  it("ignore les espaces autour et les cellules vides", () => {
    expect(sameDraft({ a: "1", b: "" }, { a: " 1 " })).toBe(true);
    expect(sameDraft({ a: "1" }, { a: "2" })).toBe(false);
    expect(sameDraft({}, { a: "1" })).toBe(false);
  });
});
