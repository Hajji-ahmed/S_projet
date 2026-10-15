"""Comptabilisation des frais bancaires par SIMTIS (décision du 13/10/2026).

Deux familles, une écriture par jour et par compte bancaire, comme Sage les passe déjà :

- Droits de timbre (« DROIT DE TIMBRE SUR VERSEMENT », « DROITS DE TIMBRE SUR REMISE LCN N… ») :
  écriture « DT D'ENREGISTREMENT » ;
- Commissions (même jour) : écriture « COM » avec une ligne par type — « COMMISSION »,
  « TAXE SUR VALEUR AJOUTEE », « COMMISSION EFFET N … REMIS PAR … », « TVA COM EFFET N … REMIS
  PAR … ». Seuls ces libellés exacts sont pris : COMMISSION VIR. RTGS…, COMMISSION REGLEMENT
  PRELEVEMENT…, COMMISSION COTISATIONS CNSS… restent manuels.

Le parcours :

1. Préparer : les écritures sont CALCULÉES à l'affichage, rien n'est écrit en base ;
2. Valider (permission `accounting.prepare`) : l'écriture (ligne banque, origine SIMTIS) est
   enregistrée et rapprochée tout de suite de ses opérations ; le code du rapprochement
   (« BP-26-000123 ») est son N° de pièce ;
3. Exporter pour Sage : une ligne par type, AU CRÉDIT du compte bancaire (option 2 du
   13/10/2026 : la contrepartie est passée par la comptabilité dans Sage) ; une écriture exportée
   ne se supprime plus.

Un jour où Sage a déjà l'écriture de la famille n'est jamais proposé (pas de double
comptabilisation) ; un export Sage qui ramène une écriture SIMTIS la reconnaît comme doublon
(`accounting_import_service`). Les autres frais restent manuels.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AccountingEntry, BankAccount, BankTransaction
from app.repositories import frais_repository, reconciliation_repository
from app.services import audit_service, reconciliation_service
from app.services.account_service import journal_des_frais
from app.services.errors import ConflictError, NotFoundError
from app.services.normalization_service import line_hash
from app.services.position_service import business_today
from app.services.reconciliation_groupes import operations_couvertes
from app.services.reconciliation_scoring import _plain as reconciliation_scoring_plain

LIBELLE_TIMBRE = "DT D'ENREGISTREMENT"
LIBELLE_COMMISSION = "COM"
LIBELLE_FRAIS = "FRAIS"
ENTITE = "accounting_entry"
# Garde-fou contre une année mal saisie, comme le moteur de rapprochement
PERIODE_MAX_JOURS = 1827
EXPORT_HEADERS = ("Journal", "Date", "Compte", "N° pièce", "Libellé", "Débit", "Crédit")
ZERO = Decimal("0.00")

# Libellés reconnus, sur le libellé en majuscules aux espaces réduits
_TIMBRE = re.compile(r"^DROITS? DE TIMBRE\b")
_COMMISSIONS = (
    ("commission", re.compile(r"^COMMISSION$")),
    ("tva", re.compile(r"^TAXE SUR VALEUR AJOUTEE$")),
    ("commission_effet", re.compile(r"^COMMISSION EFFET N\b.*\bREMIS PAR\b")),
    ("tva_commission_effet", re.compile(r"^TVA COM EFFET N\b.*\bREMIS PAR\b")),
)
# Frais à TVA comprise de 10 % (14/10/2026), sur le libellé sans ponctuation ni accents
# Le début du libellé décide de l'écriture du jour : COMMISSION… → « COM », FRAIS… → « FRAIS »
_COMMISSIONS_TVA = (
    ("commission_rtgs", re.compile(r"^COMMISSION VIR RTGS\b")),
    ("commission_prelevement", re.compile(r"^COMMISSION REGLEMENT PRELEVEMENT\b")),
    ("commission_bancaire", re.compile(r"^COMMISSION BANCAIRE\b")),
    ("commission_tenue", re.compile(r"^COMMISSION TENUE DE COMPTE\b")),
)
_FRAIS_RECUPERES = (("frais_recuperes", re.compile(r"^FRAIS RECUPERES PAR LA BANQUE\b")),)
_FRAIS_TVA = _COMMISSIONS_TVA + _FRAIS_RECUPERES
TAUX_TVA_FRAIS = Decimal("10")
# FRAIS RECUPERES PAR LA BANQUE de 77,50 : droit de timbre 50 + commission 25 + TVA 2,50
FRAIS_RECUPERES_AVEC_TIMBRE = Decimal("77.50")
TIMBRE_FRAIS_RECUPERES = Decimal("50.00")
# Libellé de chaque type et champ du compte bancaire qui donne son compte Sage à l'export
TYPES = {
    "timbre": ("Droits de timbre", "compte_timbre", "compte de charge des timbres"),
    "commission": ("Commission", "compte_commission", "compte de charge des commissions"),
    "tva": ("TVA de la commission", "compte_tva", "compte de TVA récupérable"),
    "commission_effet": (
        "Commission effet",
        "compte_commission_effet",
        "compte de charge des commissions effet",
    ),
    "tva_commission_effet": (
        "TVA de la commission effet",
        "compte_tva",
        "compte de TVA récupérable",
    ),
    # Écriture « FRAIS » (14/10/2026) : le hors taxe puis la TVA calculée de chaque type
    "commission_rtgs": ("Commission RTGS", "compte_commission", "compte de charge"),
    "commission_rtgs_tva": ("TVA commission RTGS", "compte_tva", "compte de TVA"),
    "commission_prelevement": ("Commission prélèvement", "compte_commission", "compte de charge"),
    "commission_prelevement_tva": ("TVA commission prélèvement", "compte_tva", "compte de TVA"),
    "commission_bancaire": ("Commission bancaire", "compte_commission", "compte de charge"),
    "commission_bancaire_tva": ("TVA commission bancaire", "compte_tva", "compte de TVA"),
    "commission_tenue": ("Commission tenue de compte", "compte_commission", "compte de charge"),
    "commission_tenue_tva": ("TVA commission tenue de compte", "compte_tva", "compte de TVA"),
    "frais_recuperes": ("Frais récupérés", "compte_commission", "compte de charge"),
    "frais_recuperes_tva": ("TVA frais récupérés", "compte_tva", "compte de TVA"),
    "frais_recuperes_timbre": ("Timbre frais récupérés", "compte_timbre", "compte de timbre"),
}


# --- Règles pures ---------------------------------------------------------------------------------


def _plain(libelle: str | None) -> str:
    return " ".join((libelle or "").upper().split())


def type_timbre(libelle: str | None) -> str | None:
    """« DROIT DE TIMBRE SUR VERSEMENT », « DROITS DE TIMBRE SUR REMISE LCN N 2600114 »…"""
    return "timbre" if _TIMBRE.match(_plain(libelle)) else None


def est_timbre(libelle: str | None) -> bool:
    return type_timbre(libelle) is not None


def type_commission(libelle: str | None) -> str | None:
    """Type d'une commission reprise par SIMTIS, ou None (à passer à la main)."""
    texte = _plain(libelle)
    exacte = next((code for code, regle in _COMMISSIONS if regle.match(texte)), None)
    if exacte:
        return exacte
    # Commissions à TVA comprise (RTGS, prélèvement, bancaire, tenue de compte, 14/10/2026)
    sans = _sans_ponctuation(libelle)
    return next((code for code, regle in _COMMISSIONS_TVA if regle.match(sans)), None)


def type_frais_tva(libelle: str | None) -> str | None:
    """Frais à TVA comprise comptabilisés en automatique dans l'écriture « FRAIS » (14/10/2026),
    ou None. La ponctuation et les accents ne comptent pas (« COMMISSION VIR. RTGS »)."""
    texte = _sans_ponctuation(libelle)
    # Seulement FRAIS RECUPERES PAR LA BANQUE : les commissions à TVA comprise vont dans « COM »
    return next((code for code, regle in _FRAIS_RECUPERES if regle.match(texte)), None)


def _sans_ponctuation(libelle: str | None) -> str:
    return reconciliation_scoring_plain(libelle)


def ventilation(code: str, montant: Decimal) -> list[tuple[str, Decimal]]:
    """Parts d'une opération (montant positif) dans l'écriture : (type, montant), dont la somme
    vaut toujours le montant. Un frais à TVA comprise donne son hors taxe et sa TVA de 10 %
    (arrondie au centime, comme la banque) ; FRAIS RECUPERES PAR LA BANQUE de 77,50 contient en plus
    un droit de timbre de 50. Les autres types restent entiers."""
    if code not in dict(_FRAIS_TVA):
        return [(code, montant)]
    parts: list[tuple[str, Decimal]] = []
    reste = montant
    if code == "frais_recuperes" and montant == FRAIS_RECUPERES_AVEC_TIMBRE:
        parts.append((f"{code}_timbre", TIMBRE_FRAIS_RECUPERES))
        reste = montant - TIMBRE_FRAIS_RECUPERES
    ht = (reste / (1 + TAUX_TVA_FRAIS / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return [(code, ht), (f"{code}_tva", reste - ht), *parts]


@dataclass(frozen=True)
class Famille:
    code: str  # « timbres », « commissions »
    nom: str  # pour les messages : « droits de timbre », « commissions »
    libelle: str  # libellé de l'écriture, comme dans Sage
    type_de: Callable[[str | None], str | None]
    libelle_sql: str
    ecriture_sql: str


TIMBRES = Famille(
    "timbres",
    "droits de timbre",
    LIBELLE_TIMBRE,
    type_timbre,
    frais_repository.LIBELLE_TIMBRE_SQL,
    frais_repository.ECRITURE_TIMBRE_SQL,
)
COMMISSIONS = Famille(
    "commissions",
    "commissions",
    LIBELLE_COMMISSION,
    type_commission,
    frais_repository.LIBELLE_COMMISSION_SQL,
    frais_repository.ECRITURE_COMMISSION_SQL,
)
FRAIS_TVA = Famille(
    "frais",
    "frais bancaires",
    LIBELLE_FRAIS,
    type_frais_tva,
    frais_repository.LIBELLE_FRAIS_SQL,
    frais_repository.ECRITURE_FRAIS_SQL,
)
FAMILLES = {famille.code: famille for famille in (TIMBRES, COMMISSIONS, FRAIS_TVA)}
# Écriture saisie à la main (13/10/2026) : libellé libre, pas de règle de libellé ni de type
MANUELLE = Famille("manuelle", "frais", "", lambda _libelle: None, "", "")
PAR_LIBELLE = {famille.libelle: famille for famille in FAMILLES.values()}


def famille(code: str) -> Famille:
    found = FAMILLES.get(code)
    if found is None:
        raise NotFoundError("Famille de frais inconnue.")
    return found


@dataclass
class Detail:
    type: str
    nb: int = 0
    total: Decimal = ZERO  # positif

    @property
    def libelle(self) -> str:
        return TYPES[self.type][0]


@dataclass
class JourFrais:
    """L'écriture d'un jour et d'un compte : ses opérations et leur type."""

    bank_account_id: int
    jour: date
    lignes: list[tuple[BankTransaction, str]] = field(default_factory=list)

    @property
    def operations(self) -> list[BankTransaction]:
        return [tx for tx, _ in self.lignes]

    @property
    def total(self) -> Decimal:
        """Montant de l'écriture, positif (somme des débits de la banque)."""
        return -sum((tx.montant for tx, _ in self.lignes), ZERO)

    @property
    def details(self) -> list[Detail]:
        """Total par type, dans l'ordre des types."""
        return details_par_type(self.lignes)


# Compatibilité : les droits de timbre d'un jour
JourTimbres = JourFrais


def details_par_type(lignes: list[tuple[BankTransaction, str]]) -> list[Detail]:
    """Total par type, dans l'ordre des types ; un frais à TVA comprise est ventilé (hors taxe,
    TVA, timbre). Le total des détails vaut toujours celui des opérations."""
    par_type: dict[str, Detail] = {}
    for tx, code in lignes:
        for part, montant in ventilation(code, -tx.montant):
            detail = par_type.setdefault(part, Detail(part))
            detail.nb += 1
            detail.total += montant
    return [par_type[code] for code in TYPES if code in par_type]


def regrouper(
    famille: Famille,
    operations: list[BankTransaction],
    jours_dans_sage: set[tuple[int, date]] | None = None,
) -> list[JourFrais]:
    """Un groupe par (compte, jour) : seulement des frais débités de la famille ; un jour déjà
    passé dans Sage est écarté. Trié par jour puis compte."""
    jours_dans_sage = jours_dans_sage or set()
    groupes: dict[tuple[int, date], JourFrais] = {}
    for tx in operations:
        code = famille.type_de(tx.libelle)
        if tx.montant >= 0 or code is None:
            continue
        cle = (tx.bank_account_id, tx.date_operation)
        if cle in jours_dans_sage:
            continue
        groupes.setdefault(cle, JourFrais(*cle)).lignes.append((tx, code))
    return [groupes[cle] for cle in sorted(groupes, key=lambda cle: (cle[1], cle[0]))]


def regrouper_timbres(
    operations: list[BankTransaction], jours_dans_sage: set[tuple[int, date]] | None = None
) -> list[JourFrais]:
    return regrouper(TIMBRES, operations, jours_dans_sage)


# --- Préparer -------------------------------------------------------------------------------------


@dataclass
class Proposition:
    jour: JourFrais
    account: BankAccount
    bank_code: str
    famille: Famille = field(default_factory=lambda: TIMBRES)


def _periode(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    date_to = date_to or business_today()
    date_from = date_from or date(date_to.year, 1, 1)
    if date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    if (date_to - date_from).days > PERIODE_MAX_JOURS:
        raise ConflictError("La période ne peut pas dépasser 5 ans.")
    return date_from, date_to


def _accounts(db: Session, company_id: int, bank_account_id: int | None) -> list[BankAccount]:
    accounts = reconciliation_repository.company_accounts(db, company_id, bank_account_id)
    if bank_account_id is not None and not accounts:
        raise NotFoundError("Compte bancaire introuvable.")
    return accounts


def _jours(
    db: Session,
    famille: Famille,
    company_id: int,
    account_ids: list[int],
    date_from: date,
    date_to: date,
    inclus: "dict[int, AccountingEntry] | None" = None,
) -> list[JourFrais]:
    """Jours à comptabiliser, sans les frais déjà inclus dans une écriture Sage libre."""
    if inclus is None:
        inclus = frais_inclus(db, company_id, account_ids, date_from, date_to)
    return regrouper(
        famille,
        [
            tx
            for tx in frais_repository.frais_libres(
                db, account_ids, date_from, date_to, famille.libelle_sql
            )
            if tx.id not in inclus
        ],
        frais_repository.jours_dans_sage(
            db, company_id, account_ids, date_from, date_to, famille.ecriture_sql
        ),
    )


def _frais_a_controler(
    db: Session, company_id: int, account_ids: list[int], date_from: date, date_to: date
) -> list[BankTransaction]:
    """Frais que SIMTIS proposerait ou listerait sans le contrôle « inclus dans Sage » : seuls
    ceux-là sont contrôlés (les autres ne risquent rien)."""
    automatiques = [
        tx
        for famille in FAMILLES.values()
        for jour in _jours(db, famille, company_id, account_ids, date_from, date_to, {})
        for tx in jour.operations
    ]
    manuels = [
        tx
        for tx, _ in frais_repository.autres_frais(db, account_ids, date_from, date_to)
        if not est_automatique(tx.libelle, tx.montant)
    ]
    return automatiques + manuels


def frais_inclus(
    db: Session, company_id: int, account_ids: list[int], date_from: date, date_to: date
) -> dict[int, AccountingEntry]:
    """Frais à comptabiliser qu'une écriture Sage libre couvre déjà : {opération : écriture}
    (13/10/2026). Mêmes règles que le moteur de rapprochement (groupe d'une opération principale
    et de ses frais du jour, frais d'un jour…), ou montant exactement opposé à 3 jours près : un
    tel frais se rapproche, il ne se comptabilise jamais dans SIMTIS.

    Seuls les jours de ces frais sont examinés : leurs opérations libres, et les écritures Sage
    libres dont la date ou l'échéance tombe à moins de `fenetre_jours` de l'un d'eux.
    """
    if not account_ids:
        return {}
    frais = _frais_a_controler(db, company_id, account_ids, date_from, date_to)
    if not frais:
        return {}
    jours = {(tx.bank_account_id, tx.date_operation) for tx in frais}
    regles = reconciliation_service.grille(db)
    fenetre = regles.fenetre_jours
    lecture = timedelta(days=max(regles.fenetre_jours, regles.fenetre_numero_jours))

    def proche(entry: AccountingEntry) -> bool:
        return any(
            (entry.bank_account_id, base + timedelta(days=decalage)) in jours
            for base in {entry.date_ecriture, entry.echeance or entry.date_ecriture}
            for decalage in range(-fenetre, fenetre + 1)
        )

    operations = [
        tx
        for tx in reconciliation_repository.free_transactions(db, account_ids, date_from, date_to)
        if (tx.bank_account_id, tx.date_operation) in jours
    ]
    ecritures = [
        entry
        for entry in reconciliation_repository.free_entries(
            db, company_id, account_ids, date_from - lecture, date_to + lecture
        )
        if entry.origine == "Sage" and proche(entry)
    ]
    if not ecritures:
        return {}
    couvertes = operations_couvertes(
        [reconciliation_service._operation(tx) for tx in operations],
        [reconciliation_service._ecriture(entry) for entry in ecritures],
        regles,
        reconciliation_repository.rejected_pairs(db, company_id),
        cibles={tx.id for tx in frais},
    )
    par_id = {entry.id: entry for entry in ecritures}
    a_controler = {tx.id for tx in frais}
    return {
        tx_id: par_id[entry_id] for tx_id, entry_id in couvertes.items() if tx_id in a_controler
    }


def propositions(
    db: Session,
    company_id: int,
    *,
    famille: Famille | None = None,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    inclus: dict[int, AccountingEntry] | None = None,
) -> list[Proposition]:
    """Écritures à passer, calculées (rien n'est écrit), de la plus récente à la plus ancienne ;
    toutes les familles sans `famille` (un seul tableau, 13/10/2026), timbres puis commissions
    pour un même jour et un même compte."""
    date_from, date_to = _periode(date_from, date_to)
    accounts = {a.id: a for a in _accounts(db, company_id, bank_account_id)}
    familles = [famille] if famille else list(FAMILLES.values())
    if inclus is None:
        inclus = frais_inclus(db, company_id, list(accounts), date_from, date_to)
    rang = {code: index for index, code in enumerate(FAMILLES)}
    items = [
        Proposition(
            jour, accounts[jour.bank_account_id], accounts[jour.bank_account_id].bank.code, regle
        )
        for regle in familles
        for jour in _jours(db, regle, company_id, list(accounts), date_from, date_to, inclus)
    ]
    items.sort(
        key=lambda item: (item.jour.jour, -item.jour.bank_account_id, -rang[item.famille.code])
    )
    return list(reversed(items))


# --- Valider --------------------------------------------------------------------------------------


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ConflictError(reconciliation_service.CONCURRENT) from error


def _snapshot(entry: AccountingEntry, code: str | None, operations: list[int]) -> dict:
    return {
        "origine": entry.origine,
        "journal": entry.journal,
        "compte": entry.compte,
        "date": entry.date_ecriture,
        "libelle": entry.libelle,
        "montant": entry.montant,
        "code": code,
        "operations": sorted(operations),
        "exportee_le": entry.exportee_le,
    }


def _explication(famille: Famille, jour: JourFrais) -> str:
    parts = " + ".join(
        f"{detail.libelle} {detail.total:.2f} ({detail.nb})" for detail in jour.details
    )
    return (
        f"{famille.nom.capitalize()} du {jour.jour:%d/%m/%Y} comptabilisés par SIMTIS "
        f"({famille.libelle}) : {parts} = {jour.total:.2f}."
    )


def _retenus(
    db: Session,
    famille: Famille,
    company_id: int,
    company_accounts: dict[int, BankAccount],
    choix: list[tuple[int, date]],
) -> list[tuple[BankAccount, str, JourFrais]]:
    """Jours d'une famille à écrire, recalculés ; 409 si l'un n'est plus à comptabiliser."""
    account_ids = sorted({account_id for account_id, _ in choix})
    calcules = {
        (jour.bank_account_id, jour.jour): jour
        for jour in _jours(db, famille, company_id, account_ids, choix[0][1], choix[-1][1])
    }
    retenus = []
    for cle in choix:
        account = company_accounts[cle[0]]
        jour = calcules.get(cle)
        if jour is None:
            raise ConflictError(
                f"{account.bank.code}, {cle[1]:%d/%m/%Y} : plus de {famille.nom} à "
                "comptabiliser ce jour-là. Rien n'a été comptabilisé, rechargez la liste."
            )
        journal = journal_des_frais(account)
        if journal is None or not account.compte_comptable:
            raise ConflictError(
                f"Compte {account.bank.code} {account.devise} : renseignez son compte comptable et "
                "son journal des frais (écran Comptes). Rien n'a été comptabilisé."
            )
        retenus.append((account, journal, jour))
    return retenus


def valider(
    db: Session,
    company_id: int,
    jours: list[tuple[Famille, int, date]],
    *,
    acteur_id: int,
    ip: str | None,
) -> list[AccountingEntry]:
    """Comptabilise les jours choisis, toutes familles, tous ou aucun : pour chacun, l'écriture de
    sa famille est créée et rapprochée de ses opérations, recalculées par le serveur."""
    if not jours:
        raise ConflictError("Choisissez au moins un jour à comptabiliser.")
    reconciliation_repository.lock_company(db, company_id)
    company_accounts = {a.id: a for a in _accounts(db, company_id, None)}
    par_famille: dict[str, set[tuple[int, date]]] = {}
    for regle, account_id, jour in jours:
        if account_id not in company_accounts:
            raise NotFoundError("Compte bancaire introuvable.")
        par_famille.setdefault(regle.code, set()).add((account_id, jour))
    # Tout est contrôlé avant d'écrire : tous les jours, ou aucun
    retenus = [
        (FAMILLES[code], account, journal, jour)
        for code in FAMILLES
        if code in par_famille
        for account, journal, jour in _retenus(
            db,
            FAMILLES[code],
            company_id,
            company_accounts,
            sorted(par_famille[code], key=lambda cle: (cle[1], cle[0])),
        )
    ]
    retenus.sort(key=lambda item: (item[3].jour, item[1].id))

    entries = []
    for famille, account, journal, jour in retenus:
        ids = [tx.id for tx in jour.operations]
        entry = AccountingEntry(
            company_id=company_id,
            bank_account_id=account.id,
            journal=journal,
            compte=account.compte_comptable,
            date_ecriture=jour.jour,
            libelle=famille.libelle,
            debit=ZERO,
            credit=jour.total,
            montant=jour.total,
            hash_ligne=line_hash(
                company_id, ("SIMTIS", famille.code.upper(), account.id, jour.jour, *ids), 1
            ),
            origine="SIMTIS",
            famille_frais=famille.code,
        )
        db.add(entry)
        db.flush()
        match = reconciliation_service.create_validated(
            db,
            company_id=company_id,
            transactions=jour.operations,
            entry=entry,
            origine="Frais",
            detail={"explication": _explication(famille, jour)},
            acteur_id=acteur_id,
        )
        entry.numero_piece = match.code
        audit_service.log(
            db,
            user_id=acteur_id,
            action=f"comptabilisation_{famille.code}",
            entite=ENTITE,
            entite_id=entry.id,
            apres={
                **_snapshot(entry, match.code, ids),
                "par_type": {detail.type: detail.total for detail in jour.details},
            },
            ip=ip,
        )
        entries.append(entry)
    _commit(db)
    return entries


# --- Écritures validées, suppression -------------------------------------------------------------


@dataclass
class EcritureSimtis:
    entry: AccountingEntry
    bank_code: str
    code: str | None
    nb_operations: int
    lignes: list["LigneGL"] = field(default_factory=list)
    famille: Famille = field(default_factory=lambda: TIMBRES)


def famille_de(entry: AccountingEntry) -> Famille:
    return FAMILLES.get(entry.famille_frais or "", MANUELLE)


def ecritures(
    db: Session,
    company_id: int,
    *,
    famille: Famille | None = None,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[EcritureSimtis]:
    """Écritures comptabilisées par SIMTIS (automatiques et manuelles), de la plus récente à la plus
    ancienne ; seulement celles d'une famille automatique avec `famille`."""
    accounts = {a.id: a for a in _accounts(db, company_id, bank_account_id)}
    rows = frais_repository.ecritures_simtis(
        db,
        company_id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        libelle=famille.libelle if famille else None,
    )
    operations = frais_repository.operations_of_entries(db, [entry.id for entry, _, _ in rows])
    result = []
    for entry, code, nb in rows:
        regle = famille_de(entry)
        account = accounts[entry.bank_account_id]
        lignes = lignes_ecriture(regle, account, entry, operations.get(entry.id, []))
        result.append(EcritureSimtis(entry, account.bank.code, code, nb, lignes, regle))
    return result


def supprimer(
    db: Session, entry_id: int, *, motif: str | None, acteur_id: int, ip: str | None
) -> None:
    """Supprime une écriture SIMTIS pas encore exportée : son rapprochement disparaît (l'audit le
    garde) et ses opérations redeviennent à comptabiliser. Son code n'est jamais redonné."""
    texte = " ".join((motif or "").split())
    if not texte:
        raise ConflictError("Indiquez le motif de la suppression.")
    if len(texte) > reconciliation_service.COMMENTAIRE_MAX:
        raise ConflictError(
            f"Le motif ne peut pas dépasser {reconciliation_service.COMMENTAIRE_MAX} caractères."
        )
    entry = db.get(AccountingEntry, entry_id)
    if entry is None or entry.origine != "SIMTIS":
        raise NotFoundError("Écriture SIMTIS introuvable.")
    reconciliation_repository.lock_company(db, entry.company_id)
    db.refresh(entry)
    if entry.exportee_le is not None:
        raise ConflictError(
            "Cette écriture a déjà été exportée pour Sage : elle ne se supprime plus dans SIMTIS. "
            "Corrigez-la dans Sage."
        )
    match = frais_repository.active_match_of_entry(db, entry.id)
    tx_ids = (
        sorted(item.bank_transaction_id for item in match.items if item.bank_transaction_id)
        if match
        else []
    )
    avant = _snapshot(entry, match.code if match else None, tx_ids)
    if match is not None:
        db.delete(match)
    db.flush()
    reconciliation_repository.set_transaction_status(db, set(tx_ids), "Non rapprochée")
    db.delete(entry)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="suppression_ecriture_frais",
        entite=ENTITE,
        entite_id=entry_id,
        avant={**avant, "motif": texte},
        ip=ip,
    )
    _commit(db)


# --- Lignes du grand livre (format Sage) ---------------------------------------------------------


@dataclass
class LigneGL:
    """Une ligne de l'écriture, au format du grand livre Sage (13/10/2026)."""

    type: str | None  # type du frais, None pour la ligne banque
    type_libelle: str  # « Commission effet », « Banque »…
    compte: str | None  # None : compte à renseigner (écran Comptes)
    debit: Decimal | None
    credit: Decimal | None
    nom_compte: str | None = None  # pour le message d'un compte manquant

    @property
    def banque(self) -> bool:
        return self.type is None


def est_ligne_tva(type_ligne: str | None) -> bool:
    """Ligne de TVA d'une écriture : « tva », « tva_commission_effet », « commission_rtgs_tva »…"""
    return bool(type_ligne) and (
        type_ligne == "tva" or type_ligne.startswith("tva_") or type_ligne.endswith("_tva")
    )


def libelle_ligne(libelle_ecriture: str, type_ligne: str | None) -> str:
    """Libellé d'une ligne dans Sage (14/10/2026) : celui de l'écriture, précédé de « TVA » pour
    une ligne de TVA (« COM » → « TVA COM », « FRAIS » → « TVA FRAIS »)."""
    return f"TVA {libelle_ecriture}" if est_ligne_tva(type_ligne) else libelle_ecriture


def lignes_gl(account: BankAccount, details: list[Detail], total: Decimal) -> list[LigneGL]:
    """Une ligne par type, AU CRÉDIT du compte bancaire (13/10/2026, option 2 : la contrepartie
    est passée dans Sage) ; les deux TVA restent deux lignes. Le total des lignes vaut `total`."""
    return [
        LigneGL(detail.type, TYPES[detail.type][0], account.compte_comptable, None, detail.total)
        for detail in details
    ]


def _lignes_de(
    famille: Famille,
    account: BankAccount,
    entry: AccountingEntry,
    operations: list[BankTransaction],
) -> list[LigneGL]:
    details = details_par_type(
        [(tx, code) for tx in operations if (code := famille.type_de(tx.libelle))]
    )
    lignes = lignes_gl(account, details, entry.montant)
    for ligne in lignes:
        ligne.compte = entry.compte
    return lignes


def lignes_manuelle(
    compte: str | None, montant: Decimal, montant_tva: Decimal | None
) -> list[LigneGL]:
    """Écriture manuelle : le frais (hors taxe si la TVA est séparée) puis sa TVA. Un frais
    (montant positif côté Sage) va au crédit du compte bancaire, un remboursement au débit."""
    total = abs(montant)
    parts = (
        [("frais", "Frais", total - montant_tva), ("tva", "TVA", montant_tva)]
        if montant_tva
        else [("frais", "", total)]
    )
    return [
        LigneGL(code, libelle, compte, None if montant > 0 else part, part if montant > 0 else None)
        for code, libelle, part in parts
    ]


def lignes_ecriture(
    famille: Famille,
    account: BankAccount,
    entry: AccountingEntry,
    operations: list[BankTransaction],
) -> list[LigneGL]:
    if famille is MANUELLE:
        return lignes_manuelle(entry.compte, entry.montant, entry.montant_tva)
    return _lignes_de(famille, account, entry, operations)


def _equilibree(entry: AccountingEntry, lignes: list[LigneGL]) -> None:
    credit = sum((ligne.credit or ZERO for ligne in lignes), ZERO)
    debit = sum((ligne.debit or ZERO for ligne in lignes), ZERO)
    if credit - debit != entry.montant:
        raise ConflictError(
            f"Écriture {entry.numero_piece} : ses opérations ne font plus son montant. "
            "Rien n'a été exporté."
        )


# --- Export pour Sage -----------------------------------------------------------------------------


def exporter(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None,
    date_from: date | None,
    date_to: date | None,
    inclure_exportees: bool,
    acteur_id: int,
    ip: str | None,
) -> tuple[str, bytes, int]:
    """UN classeur Excel à intégrer dans Sage, toutes familles (droits de timbre et commissions),
    par date : par écriture, une ligne par type au crédit du compte bancaire. Les écritures sont
    marquées exportées."""
    reconciliation_repository.lock_company(db, company_id)
    accounts = {a.id: a for a in _accounts(db, company_id, bank_account_id)}
    rows = [
        row
        for row in frais_repository.ecritures_simtis(
            db,
            company_id,
            bank_account_id=bank_account_id,
            date_from=date_from,
            date_to=date_to,
            non_exportees=not inclure_exportees,
        )
    ]
    if not rows:
        raise ConflictError("Aucune écriture de frais à exporter sur cette période.")
    rows.sort(key=lambda row: (row[0].date_ecriture, row[0].id))
    operations = frais_repository.operations_of_entries(db, [entry.id for entry, _, _ in rows])
    lignes = {}
    manquants: dict[str, set[str]] = {}
    for entry, _, _ in rows:
        account = accounts[entry.bank_account_id]
        lignes[entry.id] = lignes_ecriture(
            famille_de(entry), account, entry, operations.get(entry.id, [])
        )
        _equilibree(entry, lignes[entry.id])
        absents = {ligne.nom_compte for ligne in lignes[entry.id] if not ligne.compte}
        if absents:
            manquants.setdefault(f"{account.bank.code} {account.devise}", set()).update(
                nom or "compte comptable" for nom in absents
            )
    if manquants:
        raise ConflictError(
            "Renseignez dans l'écran Comptes : "
            + " ; ".join(
                f"{compte} : {', '.join(sorted(noms))}"
                for compte, noms in sorted(manquants.items())
            )
            + "."
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Écritures Sage"
    sheet.append(EXPORT_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    maintenant = datetime.now(UTC)
    for entry, code, _ in rows:
        piece = entry.numero_piece or code
        for ligne in lignes[entry.id]:
            sheet.append(
                [entry.journal, entry.date_ecriture, ligne.compte, piece,
                 libelle_ligne(entry.libelle, ligne.type),
                 ligne.debit, ligne.credit]
            )  # fmt: skip
        avant = entry.exportee_le
        if avant is None:
            entry.exportee_le = maintenant
        audit_service.log(
            db,
            user_id=acteur_id,
            action="export_ecriture_frais",
            entite=ENTITE,
            entite_id=entry.id,
            avant={"exportee_le": avant},
            apres={"exportee_le": entry.exportee_le, "reexport": avant is not None},
            ip=ip,
        )
    for row in sheet.iter_rows(min_row=2):
        row[1].number_format = "DD/MM/YYYY"
        for cell in row[5:7]:
            cell.number_format = "#,##0.00"
    for index, width in enumerate((10, 12, 14, 16, 26, 14, 14), start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    buffer = BytesIO()
    workbook.save(buffer)
    _commit(db)
    nom = f"ecritures-frais-{business_today():%Y%m%d}.xlsx"
    return nom, buffer.getvalue(), len(rows)


# --- Comptabilisation manuelle (13/10/2026) -------------------------------------------------------

LIBELLE_MAX = 60
OPERATIONS_MAX = 500
CENT = Decimal("0.01")
CENT_POUR_CENT = Decimal("100")


def ventiler_tva(total: Decimal, taux_pct: Decimal) -> tuple[Decimal, Decimal]:
    """(Frais HT, TVA) d'un total TTC : HT = total ÷ (1 + taux), arrondi au centime (au plus près,
    0,5 vers le haut) ; la TVA est le reste, si bien que HT + TVA = total exactement."""
    ht = (total / (1 + taux_pct / CENT_POUR_CENT)).quantize(CENT, rounding=ROUND_HALF_UP)
    return ht, total - ht


@dataclass
class AutreFrais:
    transaction: BankTransaction
    bank_code: str
    bank_logo: str | None
    pointage: str | None


def autres_frais(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    inclus: dict[int, AccountingEntry] | None = None,
) -> list[AutreFrais]:
    """Frais de « À comptabiliser » que SIMTIS ne comptabilise pas en automatique : à passer à la
    main, du plus récent au plus ancien. Un droit de timbre ou une commission d'une famille
    automatique n'en fait jamais partie : soit SIMTIS le propose, soit Sage a déjà l'écriture du jour
    et il se rapproche d'elle (le passer à la main le compterait deux fois)."""
    date_from, date_to = _periode(date_from, date_to)
    accounts = {a.id: a for a in _accounts(db, company_id, bank_account_id)}
    if inclus is None:
        inclus = frais_inclus(db, company_id, list(accounts), date_from, date_to)
    return [
        AutreFrais(
            tx,
            accounts[tx.bank_account_id].bank.code,
            accounts[tx.bank_account_id].bank.logo,
            pointage,
        )
        for tx, pointage in frais_repository.autres_frais(db, list(accounts), date_from, date_to)
        if not est_automatique(tx.libelle, tx.montant) and tx.id not in inclus
    ]


@dataclass
class FraisInclus:
    """Frais encore « à comptabiliser » mais déjà dans une écriture Sage libre : à rapprocher."""

    transaction: BankTransaction
    bank_code: str
    bank_logo: str | None
    ecriture: AccountingEntry


@dataclass
class TableauFrais:
    propositions: list[Proposition]
    ecritures: list["EcritureSimtis"]
    autres: list[AutreFrais]
    inclus: list[FraisInclus]


def tableau(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> TableauFrais:
    """Le bloc « Frais bancaires » en une lecture : le contrôle des frais inclus dans Sage n'est
    calculé qu'une fois."""
    date_from, date_to = _periode(date_from, date_to)
    accounts = {a.id: a for a in _accounts(db, company_id, bank_account_id)}
    inclus = frais_inclus(db, company_id, list(accounts), date_from, date_to)
    filtre = {"bank_account_id": bank_account_id, "date_from": date_from, "date_to": date_to}
    return TableauFrais(
        propositions=propositions(db, company_id, inclus=inclus, **filtre),
        ecritures=ecritures(db, company_id, **filtre),
        autres=autres_frais(db, company_id, inclus=inclus, **filtre),
        inclus=[
            FraisInclus(
                tx,
                accounts[tx.bank_account_id].bank.code,
                accounts[tx.bank_account_id].bank.logo,
                inclus[tx.id],
            )
            for tx, _ in frais_repository.autres_frais(db, list(accounts), date_from, date_to)
            if tx.id in inclus
        ],
    )


def _message_inclus(tx: BankTransaction, entry: AccountingEntry) -> str:
    return (
        f"« {tx.libelle} » est inclus dans l'écriture Sage « {entry.libelle} » du "
        f"{entry.date_ecriture:%d/%m/%Y} ({abs(entry.montant):.2f}) : lancez le rapprochement, "
        "il ne se comptabilise pas dans SIMTIS."
    )


def est_automatique(libelle: str | None, montant: Decimal | None = None) -> bool:
    """Libellé d'une famille comptabilisée en automatique (droits de timbre, commissions, frais à
    TVA comprise). Un remboursement (montant positif) ne l'est jamais : il se passe à la main."""
    if montant is not None and montant >= 0:
        return False
    return any(famille.type_de(libelle) for famille in FAMILLES.values())


def _libelle_manuel(libelle: str) -> str:
    texte = " ".join(libelle.split()).upper()
    if not texte:
        raise ConflictError("Indiquez le libellé de l'écriture.")
    if len(texte) > LIBELLE_MAX:
        raise ConflictError(f"Le libellé ne peut pas dépasser {LIBELLE_MAX} caractères.")
    return texte


def comptabiliser_manuellement(
    db: Session,
    company_id: int,
    *,
    transaction_ids: list[int],
    libelle: str,
    date_ecriture: date | None,
    taux_tva: Decimal | None,
    montant_tva: Decimal | None,
    acteur_id: int,
    ip: str | None,
) -> AccountingEntry:
    """Une écriture saisie à la main pour des frais d'un même compte, créée et rapprochée d'emblée.

    Le total est recalculé sur les opérations (jamais repris de l'écran). Avec de la TVA, le frais
    hors taxe est le total moins la TVA saisie, ou la ventilation au taux donné.
    """
    texte = _libelle_manuel(libelle)
    ids = sorted(set(transaction_ids))
    if not ids:
        raise ConflictError("Cochez au moins une opération.")
    if len(ids) > OPERATIONS_MAX:
        raise ConflictError(f"{OPERATIONS_MAX} opérations au plus par écriture.")
    reconciliation_repository.lock_company(db, company_id)
    accounts = {a.id: a for a in _accounts(db, company_id, None)}
    operations = frais_repository.frais_libres_par_ids(db, list(accounts), ids)
    if len(operations) != len(ids):
        raise ConflictError(
            "Une opération cochée n'est plus à comptabiliser (déjà rapprochée, proposée ou "
            "supprimée) : rien n'a été comptabilisé, rechargez la liste."
        )
    debut = min(tx.date_operation for tx in operations)
    fin = max(tx.date_operation for tx in operations)
    inclus = frais_inclus(
        db, company_id, sorted({tx.bank_account_id for tx in operations}), debut, fin
    )
    for tx in operations:
        if tx.id in inclus:
            raise ConflictError(_message_inclus(tx, inclus[tx.id]))
    automatiques = [tx for tx in operations if est_automatique(tx.libelle, tx.montant)]
    if automatiques:
        raise ConflictError(
            f"« {automatiques[0].libelle} » se comptabilise en automatique (droits de timbre, "
            "commissions) : il ne se passe pas à la main."
        )
    comptes = {tx.bank_account_id for tx in operations}
    if len(comptes) != 1:
        raise ConflictError(
            "Une écriture ne regroupe que des opérations d'un même compte bancaire."
        )
    account = accounts[comptes.pop()]
    journal = journal_des_frais(account)
    if journal is None or not account.compte_comptable:
        raise ConflictError(
            f"Compte {account.bank.code} {account.devise} : renseignez son compte comptable et "
            "son journal des frais (écran Comptes)."
        )
    somme = sum((tx.montant for tx in operations), ZERO)
    if somme == 0:
        raise ConflictError("Les opérations cochées s'annulent : il n'y a rien à comptabiliser.")
    montant = -somme  # au sens de Sage : un frais (débit en banque) est un crédit du compte
    total = abs(montant)
    premier = min(tx.date_operation for tx in operations)
    date_ecriture = date_ecriture or max(tx.date_operation for tx in operations)
    if date_ecriture < premier or date_ecriture > business_today():
        raise ConflictError(
            f"La date de l'écriture doit être comprise entre le {premier:%d/%m/%Y} (première "
            "opération) et aujourd'hui."
        )
    if montant_tva is None and taux_tva is not None:
        montant_tva = ventiler_tva(total, taux_tva)[1]
    if montant_tva is not None and not ZERO < montant_tva < total:
        raise ConflictError(
            "La TVA doit être positive et inférieure au total : frais hors taxe + TVA = total."
        )
    entry = AccountingEntry(
        company_id=company_id,
        bank_account_id=account.id,
        journal=journal,
        compte=account.compte_comptable,
        date_ecriture=date_ecriture,
        libelle=texte,
        debit=total if montant < 0 else ZERO,
        credit=total if montant > 0 else ZERO,
        montant=montant,
        hash_ligne=line_hash(company_id, ("SIMTIS", "MANUELLE", account.id, *ids), 1),
        origine="SIMTIS",
        famille_frais=MANUELLE.code,
        montant_tva=montant_tva,
        taux_tva=taux_tva if montant_tva is not None else None,
    )
    db.add(entry)
    db.flush()
    tva = f" dont TVA {montant_tva:.2f}" if montant_tva else ""
    match = reconciliation_service.create_validated(
        db,
        company_id=company_id,
        transactions=operations,
        entry=entry,
        origine="Frais",
        detail={
            "explication": f"{texte} saisie à la main : {len(ids)} opération"
            f"{'s' if len(ids) > 1 else ''} = {total:.2f}{tva}."
        },
        acteur_id=acteur_id,
    )
    entry.numero_piece = match.code
    audit_service.log(
        db,
        user_id=acteur_id,
        action="comptabilisation_manuelle",
        entite=ENTITE,
        entite_id=entry.id,
        apres={
            **_snapshot(entry, match.code, ids),
            "frais_ht": total - (montant_tva or ZERO),
            "montant_tva": montant_tva,
            "taux_tva": entry.taux_tva,
        },
        ip=ip,
    )
    _commit(db)
    return entry
