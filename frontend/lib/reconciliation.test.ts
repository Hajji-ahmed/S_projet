import { describe, expect, it } from "vitest";

import {
  avecDevise,
  fusionnerLignes,
  resteALire,
  bornerPeriode,
  dateCourte,
  montantVolet,
  montantEcriture,
  unite,
  uniteEcriture,
  lettrageFilename,
  montantBanque,
  nbEcritures,
  nbOperations,
  operationsDe,
  A_COMPTABILISER,
  STATUTS_VOLET,
  trierCandidats,
  absolute,
  aRejeter,
  aValider,
  defaultPeriod,
  defaultSelection,
  ecartManuel,
  compteFiltre,
  filterProposals,
  formatScore,
  rapprochable,
  reconciliationQuery,
  rejetable,
  selectionSummary,
  datesEcriture,
  periodeAStocker,
  periodeMemorisee,
  periodeRapprochement,
  sensBanque,
  sensSage,
  statutsVolet,
  toggleStatut,
  compteurStatut,
  validable,
} from "./reconciliation";
import type { Candidat, Correspondance } from "@/types/reconciliation";

describe("defaultPeriod", () => {
  it("part du 1er du mois précédent", () => {
    expect(defaultPeriod("2026-10-06")).toEqual({ from: "2026-09-01", to: "2026-10-06" });
    expect(defaultPeriod("2026-01-15")).toEqual({ from: "2025-12-01", to: "2026-01-15" });
  });
});

describe("datesEcriture", () => {
  it("montre la date et l'échéance, un tiret sans échéance", () => {
    expect(datesEcriture({ date_ecriture: "2026-08-03", echeance: "2026-08-05" })).toBe(
      "Date 03/08/2026 · Échéance 05/08/2026",
    );
    expect(datesEcriture({ date_ecriture: "2026-08-03", echeance: null })).toBe(
      "Date 03/08/2026 · Échéance —",
    );
  });
});

describe("periodeRapprochement", () => {
  it("part du 1er janvier de l'année en cours", () => {
    expect(periodeRapprochement("2026-10-27")).toEqual({ from: "2026-01-01", to: "2026-10-27" });
    expect(periodeRapprochement("2027-01-01")).toEqual({ from: "2027-01-01", to: "2027-01-01" });
  });
});

describe("periodeMemorisee", () => {
  const today = "2026-10-27";

  it("reprend la période choisie, le « Au » du jour même avance à aujourd'hui", () => {
    const hier = periodeAStocker({ from: "2026-03-01", to: "2026-10-26" }, "2026-10-26");
    expect(periodeMemorisee(hier, today)).toEqual({ from: "2026-03-01", to: today });
  });

  it("garde un « Au » choisi dans le passé", () => {
    const stockee = periodeAStocker({ from: "2026-03-01", to: "2026-06-30" }, "2026-10-26");
    expect(periodeMemorisee(stockee, today)).toEqual({ from: "2026-03-01", to: "2026-06-30" });
  });

  it.each([
    ["absente", null],
    ["illisible", "{pas du json"],
    ["incomplète", JSON.stringify({ from: "2026-03-01" })],
    ["inversée", JSON.stringify({ from: "2026-09-01", to: "2026-03-01", jour: "2026-10-20" })],
    [
      "de plus de 5 ans",
      JSON.stringify({ from: "2020-01-01", to: "2026-03-01", jour: "2026-10-20" }),
    ],
  ])("revient au 1er janvier quand elle est %s", (_cas, brut) => {
    expect(periodeMemorisee(brut, today)).toEqual({ from: "2026-01-01", to: today });
  });
});

describe("reconciliationQuery", () => {
  it("n'envoie que les filtres renseignés", () => {
    expect(reconciliationQuery(1, { from: "2026-09-01", to: "" })).toBe(
      "?company_id=1&from=2026-09-01",
    );
    expect(
      reconciliationQuery(2, {
        bankAccountId: 5,
        from: "2026-09-01",
        to: "2026-09-30",
        statut: "À vérifier",
        q: " abc ",
        page: 2,
      }),
    ).toBe(
      "?company_id=2&bank_account_id=5&from=2026-09-01&to=2026-09-30&statut=%C3%80+v%C3%A9rifier&q=abc&page=2",
    );
  });
});

describe("ecartManuel et rapprochable", () => {
  it("un crédit en banque se compense avec un débit Sage du même montant", () => {
    expect(ecartManuel("50000.00", "-50000.00")).toBe("0.00");
    expect(rapprochable("50000.00", "-50000.00")).toBe(true);
  });

  it("refuse un montant différent ou un même sens", () => {
    expect(ecartManuel("12500.00", "-12450.00")).toBe("50.00");
    expect(rapprochable("12500.00", "-12450.00")).toBe(false);
    expect(rapprochable("100.00", "100.00")).toBe(false);
    expect(rapprochable("0.00", "0.00")).toBe(false);
  });

  it("reste exact au centime", () => {
    expect(ecartManuel("0.10", "-0.30")).toBe("-0.20");
  });
});

describe("formats", () => {
  it("affiche le score sans zéros inutiles", () => {
    expect(formatScore("92.50")).toBe("92,5");
    expect(formatScore("100.00")).toBe("100");
    expect(formatScore(null)).toBe("-");
  });

  it("donne le montant absolu et le sens bancaire", () => {
    expect(absolute("-80.00")).toBe("80.00");
    expect(sensBanque("-80.00")).toBe("Débit");
    expect(sensBanque("80.00")).toBe("Crédit");
  });
});

describe("toggleStatut", () => {
  it("filtre sur le compteur cliqué, et retire le filtre au second clic", () => {
    expect(toggleStatut("", "À vérifier")).toBe("À vérifier");
    expect(toggleStatut("Rapprochée", "À vérifier")).toBe("À vérifier");
    expect(toggleStatut("À vérifier", "À vérifier")).toBe("");
  });
});

describe("compteurStatut", () => {
  it("compte les opérations en proposition parmi les non rapprochées (28/10/2026)", () => {
    const parStatut = { "Non rapprochée": 10, "À vérifier": 4, Rapprochée: 7 };
    expect(compteurStatut(parStatut, "Non rapprochée")).toBe(14);
    expect(compteurStatut(parStatut, "Rapprochée")).toBe(7);
    expect(compteurStatut({ Rapprochée: 2 }, "Non rapprochée")).toBe(0);
    expect(compteurStatut(null, "Non rapprochée")).toBeUndefined();
  });
});

function proposal(
  id: number,
  score: string,
  forte: boolean,
  montant = "100.00",
  ecriture = "-100.00",
) {
  return {
    id,
    statut: "Proposée",
    score,
    forte,
    operation: { montant },
    ecriture: { montant: ecriture },
  } as unknown as Correspondance;
}

describe("propositions en attente", () => {
  const strong = proposal(1, "95.00", true, "-250.50", "250.50");
  const weak = proposal(2, "60.00", false);
  const unequal = proposal(3, "92.00", true, "100.00", "-90.00");
  const items = [weak, unequal, strong];

  it("ne valide que les propositions équilibrées", () => {
    expect(validable(strong)).toBe(true);
    expect(validable(unequal)).toBe(false);
    expect(validable({ ...weak, statut: "Validée" })).toBe(false);
  });

  it("rejette aussi une proposition aux montants différents, jamais une décidée", () => {
    expect(rejetable(unequal)).toBe(true);
    expect(rejetable({ ...weak, statut: "Rejetée" })).toBe(false);
  });

  it("ne valide que les cochées validables, ne rejette que les cochées affichées", () => {
    const coches = new Set([1, 2, 3]);
    // La 3 (montants différents) ne part jamais à la validation
    expect(aValider(items, coches).map((p) => p.id)).toEqual([2, 1]);
    // Filtre « Fortes » : la faible (2), cochée mais cachée, n'est pas rejetée
    expect(aRejeter(filterProposals(items, "fortes"), coches).map((p) => p.id)).toEqual([1, 3]);
  });

  it("coche d'office les seules fortes validables", () => {
    expect([...defaultSelection(items)]).toEqual([1]);
  });

  it("ne coche jamais d'office une forte qui a une concurrente proche", () => {
    const close = { ...strong, id: 4, concurrente_proche: true, score_second: "88.00" };
    expect([...defaultSelection([strong, close])]).toEqual([1]);
  });

  it("filtre fortes / à vérifier, la plus forte d'abord", () => {
    expect(filterProposals(items, "toutes").map((p) => p.id)).toEqual([1, 3, 2]);
    expect(filterProposals(items, "fortes").map((p) => p.id)).toEqual([1, 3]);
    expect(filterProposals(items, "a_verifier").map((p) => p.id)).toEqual([2]);
    // Le filtre « Ambiguës » ne montre que les opérations sans proposition
    expect(filterProposals(items, "ambigues")).toEqual([]);
  });

  it("résume la sélection en centimes exacts", () => {
    expect(selectionSummary(items, new Set([1, 2]))).toEqual({
      nb: 2,
      faibles: 1,
      total: "350.50",
    });
    expect(selectionSummary(items, new Set())).toEqual({ nb: 0, faibles: 0, total: "0.00" });
  });
});

describe("sensSage", () => {
  it("lit le montant Sage : positif = crédit (sortie de banque), négatif = débit", () => {
    // Droit de timbre : 1 DH au débit en banque, 1 DH au crédit du compte banque dans Sage
    expect(sensSage("1.00")).toBe("crédit Sage");
    expect(sensSage("-50000.00")).toBe("débit Sage");
  });
});

describe("reconciliationQuery sans À vérifier", () => {
  it("ajoute sans_a_verifier seulement quand il est demandé", () => {
    expect(reconciliationQuery(1, { sansAVerifier: true, page: 1 })).toBe(
      "?company_id=1&sans_a_verifier=true&page=1",
    );
    expect(reconciliationQuery(1, { page: 1 })).toBe("?company_id=1&page=1");
  });
});

describe("statutsVolet", () => {
  it("ne propose « Écart » que si la fonction Écarts est active", () => {
    expect(statutsVolet(false)).toEqual(["Non rapprochée", "Rapprochée"]);
    expect(statutsVolet(true)).toEqual(["Non rapprochée", "Rapprochée", "Écart"]);
  });
});

describe("trierCandidats", () => {
  const candidat = (id: number, montant: string, score: string) =>
    ({ score, ecriture: { id, montant } }) as unknown as Candidat;

  it("garde le même montant ou un score au seuil, replie les autres", () => {
    const { utiles, autres } = trierCandidats(
      "88976.64",
      [
        candidat(1, "-88976.64", "40.00"),
        candidat(2, "-500.00", "55.00"),
        candidat(3, "-77.50", "35.79"),
        candidat(4, "-2.50", "34.57"),
      ],
      "50.00",
    );

    expect(utiles.map((c) => c.ecriture.id)).toEqual([1, 2]);
    expect(autres.map((c) => c.ecriture.id)).toEqual([3, 4]);
  });
});

describe("filtre À comptabiliser", () => {
  it("devient un paramètre a_comptabiliser, jamais un statut", () => {
    const query = reconciliationQuery(3, { statut: A_COMPTABILISER, page: 1 });

    expect(query).toContain("a_comptabiliser=true");
    expect(query).not.toContain("statut=");
    expect(STATUTS_VOLET).toContain(A_COMPTABILISER);
  });
});

describe("groupe N → 1", () => {
  it("utilise le total des opérations pour valider et sommer la sélection", () => {
    const groupe = {
      id: 7,
      statut: "Proposée",
      forte: true,
      operation: { montant: "-10000.00" },
      operations: [{ montant: "-10000.00" }, { montant: "-50.00" }, { montant: "-10.00" }],
      total_operations: "-10060.00",
      ecriture: { montant: "10060.00" },
    } as unknown as Correspondance;

    expect(operationsDe(groupe)).toHaveLength(3);
    expect(montantBanque(groupe)).toBe("-10060.00");
    expect(validable(groupe)).toBe(true);
    expect(selectionSummary([groupe], new Set([7])).total).toBe("10060.00");
  });
});

describe("export du lettrage", () => {
  it("nomme le fichier d'après la période", () => {
    expect(lettrageFilename({ from: "2026-09-01", to: "2026-10-14" })).toBe(
      "lettrage-2026-09-01-2026-10-14.xlsx",
    );
  });
});

describe("filtre Type d'opération", () => {
  it("passe le type à l'API", () => {
    expect(
      reconciliationQuery(3, { from: "2026-09-01", to: "2026-09-30", typeOperation: "Chèque" }),
    ).toContain("type_operation=Ch%C3%A8que");
    expect(reconciliationQuery(3, { from: "2026-09-01", to: "2026-09-30" })).not.toContain(
      "type_operation",
    );
  });
});

describe("comptes en devise", () => {
  it("rapproche le relevé du montant devise de Sage et affiche la devise", () => {
    const ecriture = { montant: "-10850.00", montant_devise: "-1000.00", devise: "EUR" };

    expect(montantEcriture(ecriture)).toBe("-1000.00");
    expect(uniteEcriture(ecriture)).toBe("EUR");
    expect(montantEcriture({ montant: "50.00" })).toBe("50.00");
    expect(uniteEcriture({ montant_devise: null, devise: "MAD" })).toBe("DH");
    expect(unite("USD")).toBe("USD");
    expect(unite("MAD")).toBe("DH");
  });
});

describe("dates propres à un volet (19/10/2026)", () => {
  const periode = { from: "2026-08-01", to: "2026-08-31" };

  it("garde la période quand les dates sont vides", () => {
    expect(bornerPeriode(periode, "", "")).toEqual({ ...periode, ajustee: false });
  });

  it("réduit la période sans en sortir", () => {
    expect(bornerPeriode(periode, "2026-08-10", "2026-08-12")).toEqual({
      from: "2026-08-10",
      to: "2026-08-12",
      ajustee: false,
    });
    expect(bornerPeriode(periode, "2026-07-20", "2026-09-05")).toEqual({
      ...periode,
      ajustee: true,
    });
  });

  it("revient à la période quand Du est après Au", () => {
    expect(bornerPeriode(periode, "2026-08-20", "2026-08-10")).toEqual({
      ...periode,
      ajustee: true,
    });
  });
});

describe("propositions éloignées (20/10/2026)", () => {
  it("ne coche jamais d'office une proposition éloignée et la filtre à part", () => {
    const eloignee = { ...proposal(1, "90.00", true), elargie: true, ecart_jours: 200 };
    const normale = proposal(2, "95.00", true);

    expect([...defaultSelection([eloignee, normale])]).toEqual([2]);
    expect(filterProposals([eloignee, normale], "eloignees").map((item) => item.id)).toEqual([1]);
  });

  it("compte sur chaque filtre exactement ce que le filtre liste", () => {
    const normale = proposal(2, "95.00", true);
    const faible = proposal(3, "60.00", false);
    // Aucune éloignée mais une écriture ambiguë : « Éloignées » doit valoir 0 (il valait 1)
    expect(compteFiltre([normale, faible], "eloignees", 4, 1)).toBe(0);
    expect(compteFiltre([normale, faible], "fortes", 4, 1)).toBe(1);
    expect(compteFiltre([normale, faible], "a_verifier", 4, 1)).toBe(1);
    expect(compteFiltre([normale, faible], "ambigues", 4, 1)).toBe(4);
    expect(compteFiltre([normale, faible], "ecritures_ambigues", 4, 1)).toBe(1);
    expect(compteFiltre([normale, faible], "toutes", 4, 1)).toBe(7);
  });
});

describe("rapprochement de reprise (27/10/2026)", () => {
  it("compte toutes les lignes, même celles que l'API ne renvoie pas", () => {
    const reprise = {
      id: 9,
      statut: "Validée",
      origine: "Reprise",
      operation: { montant: "500.00" },
      operations: [{ montant: "500.00" }, { montant: "-20.00" }],
      total_operations: "10363118.52",
      nb_operations: 10190,
      ecriture: { montant: "-500.00" },
      ecritures: [{ montant: "-500.00" }],
      total_ecritures: "-10363118.52",
      nb_ecritures: 10114,
    } as unknown as Correspondance;

    expect(nbOperations(reprise)).toBe(10190);
    expect(nbEcritures(reprise)).toBe(10114);
    expect(montantBanque(reprise)).toBe("10363118.52");
  });

  it("sans nombre envoyé, compte les lignes reçues", () => {
    const simple = { operation: { montant: "1.00" }, ecriture: { montant: "-1.00" } };

    expect(nbOperations(simple as unknown as Correspondance)).toBe(1);
    expect(nbEcritures(simple as unknown as Correspondance)).toBe(1);
  });
});

describe("volets compacts (28/10/2026)", () => {
  it("raccourcit l'année de la date", () => {
    expect(dateCourte("2026-10-20")).toBe("20/10/26");
    expect(dateCourte(null)).toBe("-");
  });

  it("retire « DH » des montants MAD et garde l'unité d'une devise", () => {
    expect(montantVolet("65638.18", "MAD")).toBe("65 638,18");
    expect(montantVolet("1000000.00")).toBe("1 000 000");
    expect(montantVolet("2891.83", "USD")).toBe("2 891,83 USD");
    expect(montantVolet("0.00", "MAD")).toBe("-");
  });

  it("ne montre la colonne Devise que si une écriture a un montant en devise", () => {
    expect(avecDevise([{ montant_devise: null }, {}])).toBe(false);
    expect(avecDevise([{ montant_devise: null }, { montant_devise: "-950.00" }])).toBe(true);
  });
});

describe("chargement au défilement (28/10/2026)", () => {
  it("ajoute les lignes de la page suivante sans doublon, dans l'ordre", () => {
    const deja = [{ id: 1 }, { id: 2 }];
    expect(fusionnerLignes(deja, [{ id: 2 }, { id: 3 }])).toEqual([
      { id: 1 },
      { id: 2 },
      { id: 3 },
    ]);
    expect(fusionnerLignes([], [{ id: 5 }])).toEqual([{ id: 5 }]);
  });

  it("s'arrête quand toutes les lignes sont chargées", () => {
    expect(resteALire(50, 8487)).toBe(true);
    expect(resteALire(8487, 8487)).toBe(false);
    expect(resteALire(0, 0)).toBe(false);
  });
});
