import { describe, expect, it } from "vitest";

import type { Devises, Previsions } from "@/types/saisie";

import {
  ajouterLigne,
  cellKey,
  devisesToDraft,
  draftToDevisesInput,
  draftToPrevisionsInput,
  formuleKey,
  groupesParDate,
  lignesPrevisions,
  previsionsToDraft,
  sameDraft,
  supprimerLigne,
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

const vide = {
  libelle: null,
  banques: [],
  encaissement: null,
  escompte: null,
  douane: null,
  formule_encaissement: null,
  formule_escompte: null,
  formule_douane: null,
};

// Une date par ligne (décision du 30/10/2026), triées par date puis par rang
const previsions: Previsions = {
  company_id: 1,
  jour: "2026-09-30",
  lignes: [
    {
      ...vide,
      jour: "2026-09-30",
      ligne: 1,
      libelle: "Client A",
      banques: [{ bank_id: BP, montant: "1000.00", formule: null }],
      encaissement: "250000.00",
    },
    { ...vide, jour: "2026-09-30", ligne: 2, douane: "-50.00" },
    { ...vide, jour: "2026-10-05", ligne: 1, libelle: "Client B" },
  ],
};

describe("previsionsToDraft / draftToPrevisionsInput", () => {
  it("met chaque ligne avec sa date et ses cellules dans le brouillon", () => {
    expect(previsionsToDraft(previsions)).toEqual({
      "1|jour": "2026-09-30",
      "1|libelle": "Client A",
      "1|3": "1 000",
      "1|encaissement": "250 000",
      "2|jour": "2026-09-30",
      "2|douane": "-50",
      "3|jour": "2026-10-05",
      "3|libelle": "Client B",
    });
  });

  it("renvoie les lignes par date, avec leur date et sans rang, un libellé blanc devenant vide", () => {
    const draft = { ...previsionsToDraft(previsions), [cellKey(3, "libelle")]: "   " };

    const parsed = draftToPrevisionsInput(draft, [AWB, BP]);

    expect(parsed).toEqual({
      ok: true,
      value: {
        lignes: [
          {
            ...vide,
            jour: "2026-09-30",
            libelle: "Client A",
            banques: [{ bank_id: BP, montant: "1000", formule: null }],
            encaissement: "250000",
          },
          { ...vide, jour: "2026-09-30", douane: "-50" },
          { ...vide, jour: "2026-10-05" },
        ],
      },
    });
  });

  it("refuse un libellé de plus de 80 caractères et un montant invalide", () => {
    const parsed = draftToPrevisionsInput(
      { "4|jour": "2026-09-30", "4|libelle": "x".repeat(81), "4|douane": "1.2.3" },
      [],
    );

    expect(parsed).toEqual({ ok: false, invalid: ["4|libelle", "4|douane"] });
  });
});

describe("formules gardées des Prévisions (10/11/2026)", () => {
  const avecFormules: Previsions = {
    company_id: 1,
    jour: "2026-09-30",
    lignes: [
      {
        ...vide,
        jour: "2026-09-30",
        ligne: 1,
        banques: [{ bank_id: BP, montant: "1750.00", formule: "=1000+500+250" }],
        escompte: "3.00",
        formule_escompte: "=1+2",
      },
    ],
  };

  it("met la formule de chaque cellule à côté de son résultat", () => {
    expect(previsionsToDraft(avecFormules)).toEqual({
      "1|jour": "2026-09-30",
      "1|3": "1 750",
      "1|3|=": "=1000+500+250",
      "1|escompte": "3",
      "1|escompte|=": "=1+2",
    });
    expect(formuleKey(cellKey(1, BP))).toBe("1|3|=");
  });

  it("renvoie chaque formule avec son montant", () => {
    const parsed = draftToPrevisionsInput(previsionsToDraft(avecFormules), [AWB, BP]);

    expect(parsed).toEqual({
      ok: true,
      value: {
        lignes: [
          {
            ...vide,
            jour: "2026-09-30",
            banques: [{ bank_id: BP, montant: "1750", formule: "=1000+500+250" }],
            escompte: "3",
            formule_escompte: "=1+2",
          },
        ],
      },
    });
  });

  it("n'envoie pas la formule d'une cellule vidée, ni une formule vide", () => {
    const draft = {
      ...previsionsToDraft(avecFormules),
      "1|3": "",
      [formuleKey(cellKey(1, "escompte"))]: "",
    };

    const parsed = draftToPrevisionsInput(draft, [AWB, BP]);

    expect(parsed).toEqual({
      ok: true,
      value: { lignes: [{ ...vide, jour: "2026-09-30", escompte: "3" }] },
    });
  });

  it("une formule modifiée rend le tableau modifié, supprimer la ligne retire ses formules", () => {
    const saved = previsionsToDraft(avecFormules);

    expect(sameDraft(saved, { ...saved, "1|3|=": "=1000+750" })).toBe(false);
    expect(supprimerLigne(saved, 1)).toEqual({});
    expect(lignesPrevisions(saved)).toEqual([{ id: 1, jour: "2026-09-30" }]);
  });
});

describe("lignes du tableau Prévisions", () => {
  it("ajoute une ligne vide après les lignes de sa date, ou à une nouvelle date", () => {
    let draft = previsionsToDraft(previsions);

    draft = ajouterLigne(draft, "2026-09-30");
    draft = ajouterLigne(draft, "2026-10-01");

    expect(lignesPrevisions(draft)).toEqual([
      { id: 1, jour: "2026-09-30" },
      { id: 2, jour: "2026-09-30" },
      { id: 4, jour: "2026-09-30" },
      { id: 5, jour: "2026-10-01" },
      { id: 3, jour: "2026-10-05" },
    ]);
  });

  it("supprime une ligne avec toutes ses cellules", () => {
    const draft = supprimerLigne(previsionsToDraft(previsions), 1);

    expect(draft).toEqual({
      "2|jour": "2026-09-30",
      "2|douane": "-50",
      "3|jour": "2026-10-05",
      "3|libelle": "Client B",
    });
    // Le serveur renumérote : la ligne restante du 30/09 est envoyée seule pour cette date
    expect(draftToPrevisionsInput(draft, []).ok).toBe(true);
  });

  it("regroupe les lignes par date pour la cellule fusionnée", () => {
    const groupes = groupesParDate(lignesPrevisions(previsionsToDraft(previsions)));

    expect(groupes.map((groupe) => [groupe.jour, groupe.lignes.length])).toEqual([
      ["2026-09-30", 2],
      ["2026-10-05", 1],
    ]);
  });

  it("une ligne ajoutée sans valeur rend le tableau modifié", () => {
    const draft = previsionsToDraft(previsions);

    expect(sameDraft(draft, ajouterLigne(draft, "2026-10-01"))).toBe(false);
  });
});

describe("sameDraft", () => {
  it("ignore les espaces autour et les cellules vides", () => {
    expect(sameDraft({ a: "1", b: "" }, { a: " 1 " })).toBe(true);
    expect(sameDraft({ a: "1" }, { a: "2" })).toBe(false);
    expect(sameDraft({}, { a: "1" })).toBe(false);
  });
});
