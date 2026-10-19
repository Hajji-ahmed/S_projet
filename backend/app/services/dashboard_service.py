"""Dashboard (P15, décision du 14/10/2026) : la vue d'ensemble d'une société sur une période.

Aucun calcul n'est refait ici : les soldes suivent la règle du tableau Banques (solde de clôture du
relevé, sinon solde saisi : `position_banques_service.soldes_par_compte`), les frais celle de
« À comptabiliser » (`reconciliation_repository.frais_bancaire`). Les montants additionnés sont
ceux des comptes courants MAD : une devise n'est jamais ajoutée à une autre ; un compte EUR / USD
n'apparaît que dans la liste des comptes, dans sa devise.
"""

import re
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models import BankAccount, BankTransaction, Company
from app.repositories import (
    account_repository,
    dashboard_repository,
    position_repository,
    reconciliation_repository,
)
from app.services.errors import ConflictError, NotFoundError
from app.services.position_banques_service import soldes_par_compte
from app.services.position_service import business_today
from app.services.reconciliation_service import _ecritures_a_egalite, grille

ZERO = Decimal("0.00")
PERIODE_MAX_JOURS = 366
NB_DERNIERES = 5
# Frais en hausse : alerte au-delà de +10 % par rapport à la période précédente
SEUIL_HAUSSE_FRAIS = Decimal("10")

# Catégories de la « Répartition des frais bancaires », dans l'ordre d'affichage
CATEGORIES_FRAIS = (
    ("tenue", "Frais de tenue de compte", re.compile(r"TENUE\W+DE\W+COMPTE")),
    ("recuperes", "Frais récupérés par la banque", re.compile(r"FRAIS\W+R.CUP.R.S")),
    ("agios", "Agios et intérêts", re.compile(r"AGIOS|INTERET|INTÉRÊT")),
    ("timbres", "Droits de timbre", re.compile(r"TIMBRE|DT\W+D.?\W*ENREGISTREMENT")),
    (
        "commissions",
        "Commissions et TVA",
        re.compile(r"COMMISSION|TAXE\W+SUR\W+VALEUR|^\W*TVA\b|^\W*COM\b"),
    ),
)
AUTRES = ("autres", "Autres")


# --- Règles pures ---------------------------------------------------------------------------------


def variation(actuel: Decimal | None, precedent: Decimal | None) -> Decimal | None:
    """Variation en % (1 décimale), ou None quand elle n'a pas de sens (rien avant, ou zéro)."""
    if actuel is None or precedent is None or precedent == 0:
        return None
    pct = (actuel - precedent) / abs(precedent) * 100
    return pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def categorie_frais(libelle: str | None) -> tuple[str, str]:
    """(code, libellé) de la catégorie d'un frais, lue sur son libellé ; sinon « Autres »."""
    texte = (libelle or "").upper()
    for code, nom, regle in CATEGORIES_FRAIS:
        if regle.search(texte):
            return code, nom
    return AUTRES


def solde_au(soldes: Sequence[tuple[date, Decimal]], jour: date) -> Decimal | None:
    """Dernier solde connu au plus tard le `jour` ; None si aucun."""
    connus = [solde for date_solde, solde in soldes if date_solde <= jour]
    return connus[-1] if connus else None


def evolution(
    soldes: dict[int, Sequence[tuple[date, Decimal]]], debut: date, fin: date
) -> list[tuple[date, Decimal | None]]:
    """Solde total de chaque jour (dernier solde connu de chaque compte) ; None un jour où aucun
    compte n'a encore de solde."""
    points = []
    jour = debut
    while jour <= fin:
        valeurs = [v for v in (solde_au(s, jour) for s in soldes.values()) if v is not None]
        points.append((jour, sum(valeurs, ZERO) if valeurs else None))
        jour += timedelta(days=1)
    return points


def flux(
    par_jour: dict[date, tuple[Decimal, Decimal]], debut: date, fin: date
) -> list[tuple[date, Decimal, Decimal]]:
    """(jour, encaissements, décaissements) de chaque jour de la période ; 0 un jour sans
    mouvement (un mouvement nul est un fait, pas une valeur inconnue)."""
    points = []
    jour = debut
    while jour <= fin:
        encaissements, decaissements = par_jour.get(jour, (ZERO, ZERO))
        points.append((jour, encaissements, decaissements))
        jour += timedelta(days=1)
    return points


def repartition(frais: Iterable[tuple[str, Decimal]]) -> list[tuple[str, str, Decimal]]:
    """(code, libellé, total) par catégorie non vide, dans l'ordre des catégories."""
    totaux: OrderedDict[str, tuple[str, Decimal]] = OrderedDict(
        (code, (nom, ZERO)) for code, nom, _ in CATEGORIES_FRAIS
    )
    totaux[AUTRES[0]] = (AUTRES[1], ZERO)
    for libelle, montant in frais:
        code, nom = categorie_frais(libelle)
        totaux[code] = (nom, totaux[code][1] + montant)
    return [(code, nom, total) for code, (nom, total) in totaux.items() if total]


@dataclass(frozen=True)
class Alerte:
    niveau: str  # danger, warning, info
    message: str
    lien: str


def _pluriel(n: int, mot: str) -> str:
    return f"{n} {mot}{'s' if n > 1 else ''}"


def alertes(
    *,
    depassements: Sequence[tuple[str, Decimal]],
    a_rapprocher: int,
    a_comptabiliser: int,
    a_exporter: int,
    hausse_frais: Decimal | None,
) -> list[Alerte]:
    """Alertes du dashboard, la plus grave d'abord. `depassements` : (banque, montant au-delà de
    la LIGNE, négatif)."""
    liste = [
        Alerte(
            "danger",
            f"Dépassement de ligne : {banque} ({montant:.2f} DH)",
            "/position-bancaire",
        )
        for banque, montant in depassements
    ]
    if a_rapprocher:
        liste.append(
            Alerte(
                "warning", f"{_pluriel(a_rapprocher, 'opération')} à rapprocher", "/rapprochement"
            )
        )
    if a_comptabiliser:
        liste.append(
            Alerte(
                "warning",
                f"{a_comptabiliser} frais bancaire{'s' if a_comptabiliser > 1 else ''}"
                " à comptabiliser",
                "/rapprochement",
            )
        )
    if a_exporter:
        liste.append(
            Alerte(
                "info",
                f"{_pluriel(a_exporter, 'écriture')} de frais à exporter pour Sage",
                "/rapprochement",
            )
        )
    if hausse_frais is not None and hausse_frais > SEUIL_HAUSSE_FRAIS:
        liste.append(
            Alerte(
                "warning",
                f"Frais bancaires en hausse (+{str(hausse_frais).replace('.', ',')} %)",
                "/rapprochement",
            )
        )
    return liste


# --- Assemblage -----------------------------------------------------------------------------------


@dataclass
class CompteDashboard:
    account: BankAccount
    solde: Decimal | None
    variation: Decimal | None
    # LIGNE (crédit autorisé) d'un compte courant MAD ; None pour un compte en devise
    ligne: Decimal | None = None

    @property
    def disponible(self) -> Decimal | None:
        """Solde + LIGNE d'un compte courant MAD ; None sans solde ou sans LIGNE."""
        if self.solde is None or self.ligne is None:
            return None
        return self.solde + self.ligne


@dataclass(frozen=True)
class Taches:
    """Travail en attente (onglet « Suivi », 19/10/2026)."""

    propositions_fortes: int
    propositions_a_verifier: int
    operations_ambigues: int
    ecritures_ambigues: int
    a_comptabiliser: int
    a_exporter: int


@dataclass(frozen=True)
class Banque:
    """Avancement du rapprochement et frais d'une banque sur la période."""

    code: str
    logo: str | None
    rapprochees: int
    a_rapprocher: int
    total: int
    frais: Decimal


@dataclass
class Dashboard:
    company: Company
    date_from: date
    date_to: date
    solde_total: Decimal | None
    solde_total_variation: Decimal | None
    # Somme des LIGNES des comptes courants MAD ; disponible = solde total + LIGNE totale
    ligne_totale: Decimal
    disponible: Decimal | None
    encaissements: Decimal
    encaissements_variation: Decimal | None
    decaissements: Decimal
    decaissements_variation: Decimal | None
    rapprochees: int
    a_rapprocher: int
    total_operations: int
    evolution: list[tuple[date, Decimal | None]]
    flux: list[tuple[date, Decimal, Decimal]]
    a_comptabiliser: int
    frais: list[tuple[str, str, Decimal]]
    frais_total: Decimal
    comptes: list[CompteDashboard]
    dernieres: list[tuple[BankTransaction, BankAccount]]
    ecritures_exportees: int
    ecritures_a_exporter: int
    alertes: list[Alerte] = field(default_factory=list)
    bank_id: int | None = None
    # Banques de la société qui ont un compte actif (liste du filtre), dans l'ordre d'affichage
    banques_societe: list[tuple[int, str, str | None]] = field(default_factory=list)
    taches: Taches | None = None
    banques: list[Banque] = field(default_factory=list)


def _periode(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = business_today()
    date_to = min(date_to or today, today)
    date_from = date_from or date_to.replace(day=1)
    if date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    if (date_to - date_from).days >= PERIODE_MAX_JOURS:
        raise ConflictError("La période du dashboard ne peut pas dépasser un an.")
    return date_from, date_to


def _company(db: Session, company_id: int) -> Company:
    company = account_repository.get_company(db, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    return company


def dashboard(
    db: Session,
    company_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    bank_id: int | None = None,
    avec_taches: bool = True,
) -> Dashboard:
    """`bank_id` (19/10/2026) : tous les chiffres pour cette banque seulement ; None = toutes."""
    company = _company(db, company_id)
    date_from, date_to = _periode(date_from, date_to)
    duree = date_to - date_from
    prec_to = date_from - timedelta(days=1)
    prec_from = prec_to - duree

    actifs = [a for a in reconciliation_repository.company_accounts(db, company.id) if a.actif]
    banques_societe = sorted(
        {(a.bank.ordre_affichage, a.bank_id, a.bank.code, a.bank.logo) for a in actifs}
    )
    comptes = [account for account in actifs if bank_id is None or account.bank_id == bank_id]
    tous = [account.id for account in comptes]
    mad = [
        account.id
        for account in position_repository.current_mad_accounts(db, company.id)
        if bank_id is None or account.bank_id == bank_id
    ]
    soldes = soldes_par_compte(db, tous, date_to)

    def total_mad(jour: date) -> Decimal | None:
        valeurs = [v for v in (solde_au(soldes[i], jour) for i in mad) if v is not None]
        return sum(valeurs, ZERO) if valeurs else None

    solde_total = total_mad(date_to)
    encaissements, decaissements = dashboard_repository.mouvements(db, mad, date_from, date_to)
    enc_prec, dec_prec = dashboard_repository.mouvements(db, mad, prec_from, prec_to)

    par_statut = dashboard_repository.statuts(db, tous, date_from, date_to)
    a_rapprocher = sum(
        par_statut.get(statut, 0) for statut in dashboard_repository.STATUTS_A_RAPPROCHER
    )

    frais = dashboard_repository.frais_debites(db, mad, date_from, date_to)
    frais_total = sum((montant for _, montant in frais), ZERO)
    frais_prec = sum(
        (m for _, m in dashboard_repository.frais_debites(db, mad, prec_from, prec_to)), ZERO
    )
    exportees, a_exporter = dashboard_repository.ecritures_simtis(db, tous, date_from, date_to)

    lignes = {account.id: account for account in comptes}
    # LIGNE des seuls comptes au solde connu, comme le TOTAL du tableau Banques : la LIGNE d'un
    # compte sans solde gonflerait le disponible
    ligne_totale = sum(
        (
            lignes[i].credit_autorise
            for i in mad
            if i in lignes and solde_au(soldes[i], date_to) is not None
        ),
        ZERO,
    )
    a_comptabiliser = dashboard_repository.frais_a_comptabiliser(db, tous, date_from, date_to)
    depassements = []
    for account_id in mad:
        solde = solde_au(soldes[account_id], date_to)
        account = lignes.get(account_id)
        if solde is not None and account is not None and solde + account.credit_autorise < 0:
            depassements.append((account.bank.code, solde + account.credit_autorise))

    taches = None
    banques: list[Banque] = []
    if avec_taches:
        regles = grille(db)
        fortes, a_verifier = dashboard_repository.propositions(
            db, tous, date_from, date_to, regles.seuil_fort
        )
        operations_ambigues = sum(
            reconciliation_repository.ambiguous_transactions(
                db, company.id, bank_account_id=i, date_from=date_from, date_to=date_to,
                offset=0, limit=0,
            )[0]
            for i in tous
        )  # fmt: skip
        # Écritures ambiguës : seulement celles qui ont au moins deux opérations à égalité, la
        # règle de la liste « Écritures ambiguës » (sans calculer le détail de ses cartes)
        a_verifier_ec = [
            entry
            for i in tous
            for entry in reconciliation_repository.ambiguous_entries(
                db, company.id, bank_account_id=i, date_from=date_from, date_to=date_to,
                offset=0, limit=None,
            )[1]
        ]  # fmt: skip
        ecritures_ambigues = len(
            _ecritures_a_egalite(
                db, a_verifier_ec, regles, reconciliation_repository.rejected_pairs(db, company.id)
            )
        )
        taches = Taches(
            propositions_fortes=fortes,
            propositions_a_verifier=a_verifier,
            operations_ambigues=operations_ambigues,
            ecritures_ambigues=ecritures_ambigues,
            a_comptabiliser=a_comptabiliser,
            a_exporter=a_exporter,
        )
        frais_banque = dict(dashboard_repository.frais_par_banque(db, mad, date_from, date_to))
        banques = [
            Banque(code, logo, rapprochees, a_rapp, total, frais_banque.get(code, ZERO))
            for code, logo, rapprochees, a_rapp, total in dashboard_repository.par_banque(
                db, tous, date_from, date_to
            )
        ]

    return Dashboard(
        company=company,
        date_from=date_from,
        date_to=date_to,
        solde_total=solde_total,
        solde_total_variation=variation(solde_total, total_mad(prec_to)),
        ligne_totale=ligne_totale,
        disponible=None if solde_total is None else solde_total + ligne_totale,
        encaissements=encaissements,
        encaissements_variation=variation(encaissements, enc_prec),
        decaissements=decaissements,
        decaissements_variation=variation(decaissements, dec_prec),
        rapprochees=par_statut.get("Rapprochée", 0),
        a_rapprocher=a_rapprocher,
        total_operations=sum(par_statut.values()),
        evolution=evolution({i: soldes[i] for i in mad}, date_from, date_to),
        flux=flux(
            dashboard_repository.flux_par_jour(db, mad, date_from, date_to), date_from, date_to
        ),
        a_comptabiliser=a_comptabiliser,
        frais=repartition(frais),
        frais_total=frais_total,
        comptes=[
            CompteDashboard(
                account,
                solde_au(soldes[account.id], date_to),
                variation(
                    solde_au(soldes[account.id], date_to), solde_au(soldes[account.id], prec_to)
                ),
                account.credit_autorise if account.id in mad else None,
            )
            for account in sorted(comptes, key=lambda a: (a.bank.ordre_affichage, a.devise, a.id))
        ],
        dernieres=[
            (tx, lignes[tx.bank_account_id])
            for tx in dashboard_repository.dernieres_operations(db, tous, date_to, NB_DERNIERES)
        ],
        ecritures_exportees=exportees,
        ecritures_a_exporter=a_exporter,
        alertes=alertes(
            depassements=depassements,
            a_rapprocher=a_rapprocher,
            a_comptabiliser=a_comptabiliser,
            a_exporter=a_exporter,
            hausse_frais=variation(frais_total, frais_prec),
        ),
        bank_id=bank_id,
        banques_societe=[(i, code, logo) for _, i, code, logo in banques_societe],
        taches=taches,
        banques=banques,
    )
