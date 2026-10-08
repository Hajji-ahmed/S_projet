import { describe, expect, it } from "vitest";

import {
  accountsWithStatements,
  assignField,
  exportFilename,
  fieldsByColumn,
  fileProblem,
  formatDateTime,
  importForm,
  moveIndex,
  periodQuery,
  showFirst,
  showLast,
} from "./statements";

describe("lignes affichées d'une longue liste", () => {
  const rows = Array.from({ length: 120 }, (_, index) => index + 1);

  it("relevé : garde les dernières lignes, dans leur ordre, et masque les plus anciennes", () => {
    const view = showLast(rows, 50, 50);
    expect(view.rows).toHaveLength(50);
    expect(view.rows[0]).toBe(71);
    expect(view.rows[49]).toBe(120);
    expect(view.hidden).toBe(70);
    expect(view.next).toBe(50);
  });

  it("journal : garde les premières lignes (les plus récentes) et masque la suite", () => {
    const view = showFirst(rows, 10, 10);
    expect(view.rows).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(view.hidden).toBe(110);
    expect(view.next).toBe(10);
  });

  it("le prochain lot ne dépasse pas ce qui reste masqué", () => {
    expect(showLast(rows, 100, 50).next).toBe(20);
    expect(showFirst(rows, 110, 10).next).toBe(10);
    expect(showFirst(rows, 115, 10).next).toBe(5);
  });

  it("rien n'est masqué quand la liste est courte ou entièrement dépliée", () => {
    expect(showLast([1, 2, 3], 50, 50)).toEqual({ rows: [1, 2, 3], hidden: 0, next: 0 });
    expect(showFirst([1, 2, 3], 10, 10)).toEqual({ rows: [1, 2, 3], hidden: 0, next: 0 });
    expect(showLast(rows, 150, 50).hidden).toBe(0);
    expect(showLast([], 50, 50)).toEqual({ rows: [], hidden: 0, next: 0 });
  });
});

describe("fileProblem", () => {
  it("accepte un .xlsx de taille raisonnable", () => {
    expect(fileProblem({ name: "Relevé CIH.XLSX", size: 2048 })).toBeNull();
    // L'ancien format Excel est accepté aussi (décision du 08/10/2026)
    expect(fileProblem({ name: "RELEVE_BP.XLS", size: 2048 })).toBeNull();
  });

  it("refuse les autres formats, le fichier vide et le fichier trop gros", () => {
    expect(fileProblem({ name: "releve.csv", size: 10 })).toBe(
      "Seuls les fichiers Excel .xlsx ou .xls sont acceptés.",
    );
    expect(fileProblem({ name: "releve.xlsx", size: 0 })).toBe("Le fichier est vide.");
    expect(fileProblem({ name: "releve.xlsx", size: 20 * 1024 * 1024 })).toBeNull();
    expect(fileProblem({ name: "releve.xlsx", size: 20 * 1024 * 1024 + 1 })).toMatch(/20 Mo/);
  });
});

describe("correspondance des colonnes", () => {
  const mapping = { date_operation: 0, libelle: 2, debit: 3, credit: null };

  it("donne le champ de chaque colonne", () => {
    expect(fieldsByColumn(mapping)).toEqual({ 0: "date_operation", 2: "libelle", 3: "debit" });
  });

  it("associe un champ à une colonne", () => {
    expect(assignField(mapping, 4, "credit")).toEqual({
      date_operation: 0,
      libelle: 2,
      debit: 3,
      credit: 4,
    });
  });

  it("retire le champ de la colonne qui l'avait, et l'ancien champ de la colonne choisie", () => {
    expect(assignField(mapping, 3, "libelle")).toEqual({
      date_operation: 0,
      libelle: 3,
      credit: null,
    });
  });

  it("ignore une colonne", () => {
    expect(assignField(mapping, 3, null)).toEqual({ date_operation: 0, libelle: 2, credit: null });
  });
});

describe("importForm", () => {
  const file = new File(["x"], "releve.xlsx");

  it("envoie le fichier et le compte, sans correspondance s'il n'y en a pas", () => {
    const form = importForm({ file, accountId: 7 });

    expect(form.get("bank_account_id")).toBe("7");
    expect((form.get("fichier") as File).name).toBe("releve.xlsx");
    expect(form.has("mapping")).toBe(false);
    expect(form.has("ecarter_erreurs")).toBe(false);
  });

  it("envoie la correspondance sans les champs vides, la feuille et les options", () => {
    const form = importForm(
      { file, accountId: 7, mapping: { date_operation: 0, credit: null }, feuille: "Sept" },
      { garderDoublons: [9, 4], ecarterErreurs: true },
    );

    expect(form.get("mapping")).toBe('{"date_operation":0}');
    expect(form.get("feuille")).toBe("Sept");
    expect(form.get("garder_doublons")).toBe("[4,9]");
    expect(form.get("ecarter_erreurs")).toBe("true");
  });

  it("n'envoie pas de liste vide de doublons gardés", () => {
    const form = importForm({ file, accountId: 7 }, { garderDoublons: [], ecarterErreurs: false });

    expect(form.has("garder_doublons")).toBe(false);
    expect(form.get("ecarter_erreurs")).toBe("false");
  });

  it("envoie les lignes de l'aperçu à la place des anciennes options", async () => {
    const ligne = {
      numero: 2,
      date_operation: "2026-09-24",
      date_valeur: null,
      libelle: "VIR",
      reference: null,
      debit: null,
      credit: "10.00",
      solde: null,
      pointage_type_id: 1,
      lettrage_escompte: null,
      commentaire: null,
    };

    const form = importForm({ file, accountId: 7 }, { lignes: [ligne] });

    // Envoyées comme un fichier JSON : un champ de formulaire est limité à 1 Mo côté serveur
    const part = form.get("lignes") as File;
    expect(part.type).toBe("application/json");
    expect(JSON.parse(await part.text())).toEqual([ligne]);
    expect(form.has("garder_doublons")).toBe(false);
    expect(form.has("ecarter_erreurs")).toBe(false);
  });
});

describe("exportFilename", () => {
  it("nomme le fichier par banque, devise et période, comme l'API", () => {
    expect(
      exportFilename({
        bank_code: "CIH",
        devise: "MAD",
        periode_debut: "2026-09-24",
        periode_fin: "2026-09-26",
      }),
    ).toBe("releve_CIH_MAD_2026-09-24_2026-09-26.xlsx");
  });
});

describe("periodQuery", () => {
  it("n'envoie que les bornes renseignées", () => {
    expect(periodQuery({})).toBe("");
    expect(periodQuery({ from: "2026-09-01", to: "" })).toBe("?from=2026-09-01");
    expect(periodQuery({ from: "2026-09-01", to: "2026-09-30" })).toBe(
      "?from=2026-09-01&to=2026-09-30",
    );
  });
});

describe("accountsWithStatements", () => {
  it("garde chaque compte une fois, trié par banque puis devise", () => {
    const rows = [
      { id: 3, bank_account_id: 4, bank_code: "CIH", devise: "MAD" },
      { id: 2, bank_account_id: 9, bank_code: "BP", devise: "MAD" },
      { id: 1, bank_account_id: 4, bank_code: "CIH", devise: "MAD" },
      { id: 0, bank_account_id: 7, bank_code: "CIH", devise: "EUR" },
    ];

    expect(accountsWithStatements(rows).map((row) => row.bank_account_id)).toEqual([9, 7, 4]);
  });
});

describe("moveIndex", () => {
  it("descend et monte sans sortir de la liste", () => {
    expect(moveIndex(0, "ArrowDown", 5)).toBe(1);
    expect(moveIndex(4, "ArrowDown", 5)).toBe(4);
    expect(moveIndex(2, "ArrowUp", 5)).toBe(1);
    expect(moveIndex(0, "ArrowUp", 5)).toBe(0);
  });

  it("va au début ou à la fin, et ignore les autres touches", () => {
    expect(moveIndex(3, "Home", 5)).toBe(0);
    expect(moveIndex(1, "End", 5)).toBe(4);
    expect(moveIndex(1, "a", 5)).toBeNull();
    expect(moveIndex(0, "ArrowDown", 0)).toBeNull();
  });
});

describe("formatDateTime", () => {
  it("affiche la date et l'heure du Maroc", () => {
    // Date passée : l'heure légale du Maroc en 2026 dépend de la version des données de fuseaux
    // (tzdata 2026c : UTC+0 en octobre 2026). Le navigateur et le serveur font foi.
    expect(formatDateTime("2025-10-01T09:30:00+00:00")).toBe("01/10/2025 10:30");
  });
});
