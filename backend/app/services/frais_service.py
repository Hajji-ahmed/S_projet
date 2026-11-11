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

import csv
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO, StringIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AccountingEntry,
    BankAccount,
    BankTransaction,
    FraisJourEcarte,
    FraisLigne,
)
from app.repositories import frais_repository, reconciliation_repository
from app.services import audit_service, reconciliation_service
from app.services.account_service import compte_principal, journal_des_frais
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
# Format d'import paramétrable de Sage (15/10/2026), dans l'ordre de l'écran Sage ; les colonnes
# marquées d'une étoile sont obligatoires pour Sage. Le fichier n'a PAS de ligne d'en-tête
# (11/11/2026, Sage l'importe ainsi) : cette liste ne sert que de référence pour l'ordre des colonnes
COLONNES_SAGE = (
    "* Date de pièce",
    "N° pièce",
    "* Code journal",
    "* N° compte général",
    "N° compte tiers",
    "Libellé écriture",
    "Montant",
    "Sens",
    "Mode de règlement",
    "Date d'échéance",
    "Référence",
    "Numéro facture",
    "Montant devise",
    "Cours de la devise",
    "Code ISO devise",
)
SENS_DEBIT = "Débit"
# N° pièce d'une écriture de frais (16/10/2026) : BANQUE AA MM NNN (« BP2610123 »), un compteur
# par société, banque et mois
PIECE_MAX = 999
SENS_CREDIT = "Crédit"
# Fichier pour Sage (16/10/2026) : CSV au point-virgule, en Windows-1252 (accents de « Débit »)
CSV_SEPARATEUR = ";"
CSV_ENCODAGE = "cp1252"
# Colonne Sens du fichier (11/11/2026) : « D » / « C », comme le modèle de Mustapha
SENS_CSV = {SENS_DEBIT: "D", SENS_CREDIT: "C"}
ZERO = Decimal("0.00")

# Libellés reconnus, sur le libellé en majuscules aux espaces réduits
# Droits de timbre ; les autres banques (09/11/2026) : « FRAIS DE TIMBRE/DOMICILIATION TITRE
# IMPORTATION » (BMCE, BMCI), « FRAIS DE TIMBRE DOMICILIATION TITRES… », « FRAIS TIMBRE DU MOIS »
# (AWB)
_TIMBRE = re.compile(
    r"^(DROITS? DE TIMBRE\b|FRAIS DE TIMBRE ?/? ?DOMICILIATION\b|FRAIS TIMBRE DU MOIS\b)"
)
_COMMISSIONS = (
    ("commission", re.compile(r"^COMMISSION$")),
    ("tva", re.compile(r"^TAXE SUR VALEUR AJOUTEE$")),
    ("commission_effet", re.compile(r"^COMMISSION EFFET N\b.*\bREMIS PAR\b")),
    ("tva_commission_effet", re.compile(r"^TVA COM EFFET N\b.*\bREMIS PAR\b")),
    # Autres banques (09/11/2026), commission et TVA sur deux lignes comme chez BP (BMCE, BMCI)
    ("commission", re.compile(r"^TRANSFERT EMIS,? COMMISSION DE TRANSFERT\b")),
    ("commission", re.compile(r"^COMMISSION SUR VIREMENT SRBM\b")),
    ("tva", re.compile(r"^TVA 10 ?% SUR COMMISSION TRF")),
    ("tva", re.compile(r"^TVA COMMISSION SUR VIREMENT SRBM\b")),
)
# Frais à TVA comprise de 10 % (14/10/2026), sur le libellé sans ponctuation ni accents
# Le début du libellé décide de l'écriture du jour : COMMISSION… → « COM », FRAIS… → « FRAIS »
_COMMISSIONS_TVA = (
    ("commission_rtgs", re.compile(r"^COMMISSION VIR RTGS\b")),
    ("commission_prelevement", re.compile(r"^COMMISSION REGLEMENT PRELEVEMENT\b")),
    ("commission_bancaire", re.compile(r"^COMMISSION BANCAIRE\b")),
    # « DE TENUE » chez AWB (09/11/2026)
    ("commission_tenue", re.compile(r"^COMMISSION (DE )?TENUE DE COMPTE\b")),
    # Autres banques (09/11/2026) : AWB, CIH
    ("commission_lcn", re.compile(r"^COMMISSION REJET PAIEMENT LCN\b")),
    ("commission_lcn", re.compile(r"^COM FRAIS (REGLEMENT \d+ LCN|\d+ LCN (PAYEES|IMPAYEES))\b")),
    ("commission_domiciliation", re.compile(r"^COMMISSION DOMICILIATION TITRES?\b")),
)
_FRAIS_RECUPERES = (
    ("frais_recuperes", re.compile(r"^FRAIS RECUPERES PAR LA BANQUE\b")),
    # Autres banques (09/11/2026) : AWB, CIH
    ("frais_swift", re.compile(r"^FRAIS SWIFT CREDOC IMPORT\b")),
    ("frais_cheques", re.compile(r"^FRAIS ENCAISSEMENT DE CHEQUES\b")),
)
_FRAIS_TVA = _COMMISSIONS_TVA + _FRAIS_RECUPERES
TAUX_TVA_FRAIS = Decimal("10")
# Décision du 19/10/2026 : une opération de frais de plus de 200 DH (hors droits de timbre) n'est
# jamais comptabilisée en automatique ; elle se passe à la main et se justifie auprès de la banque
SEUIL_MANUEL = Decimal("200")
# Décision du 11/11/2026 : une commission dont la TVA est sur une ligne à part (« COMMISSION » +
# « TAXE SUR VALEUR AJOUTEE » de BP, et les mêmes paires des autres banques) passe en automatique
# même au-dessus de `SEUIL_MANUEL`, et sort du fichier des frais à justifier ; les commissions à TVA
# comprise et les autres frais suivent toujours le seuil
TYPES_SANS_SEUIL = frozenset({"commission", "tva", "commission_effet", "tva_commission_effet"})
# FRAIS RECUPERES PAR LA BANQUE de 77,50 : droit de timbre 50 + commission 25 + TVA 2,50
FRAIS_RECUPERES_AVEC_TIMBRE = Decimal("77.50")
TIMBRE_FRAIS_RECUPERES = Decimal("50.00")
# Comptes généraux Sage des lignes de frais (16/10/2026, donnés par le métier) : chaque ligne
# de frais va au débit de son compte, le total au crédit du compte bancaire
# 61671000 depuis le 11/11/2026 (61671 avant ; migration 0050 pour les lignes non exportées)
COMPTE_TIMBRE = "61671000"
COMPTE_FRAIS_BANCAIRES = "61473000"  # FRAIS COMMISSIONS BANCAIRE
# Commissions (COM) : 61473000 depuis le 11/11/2026 (61714000 avant ; migration 0052 pour les
# lignes saisies non exportées)
COMPTE_COMMISSION = COMPTE_FRAIS_BANCAIRES
COMPTE_TVA = "34552142"  # TVA BANQUE 10 %
COMPTES_AGIOS = {
    "BMCE": "63111000",
    "BP": "63112000",
    "AWB": "63113000",
    "BMCI": "63116000",
    "CIH": "63116300",
}

# Comptes de charge des frais et intérêts bancaires (05/11/2026, liste du plan comptable donnée par
# le métier) : (numéro, intitulé, banque réservée). Une écriture manuelle dont le libellé commence
# par l'intitulé va sur ce compte ; on peut aussi le choisir dans la saisie.
COMPTES_FRAIS: tuple[tuple[str, str, str | None], ...] = (
    # Aussi le compte des commissions (COM) depuis le 11/11/2026 : « 61714000 COMMISSIONS » retiré
    ("61473000", "FRAIS COMMISSIONS BANCAIRE", None),
    ("63110001", "INTERET CREDOC", None),
    ("63110002", "INTERET RELANCE", None),
    ("63110004", "INTERET CMT / OXYGENE", None),
    ("63111000", "AGIOS B.M.C.E", "BMCE"),
    ("63112000", "AGIOS BP", "BP"),
    ("63113000", "AGIOS AWB", "AWB"),
    ("63115200", "INTERET DE RETARD/ OP FINANCIERE", None),
    ("63116000", "AGIOS BMCI", "BMCI"),
    ("63116300", "AGIOS CIH", "CIH"),
    ("63117000", "FRAIS D'ESCOMPTE", None),
    ("63118000", "INTERETS CREDIT ENLEVEMENT", None),
    ("63119400", "INTERET CRED SPOT", None),
    ("63119410", "INTERET ACNE/MCNE", None),
    ("63119420", "INTERETS CREDIT AFFACTURAGE", None),
    ("63119500", "FRAIS DE REFINANCEMENT", None),
    ("63119700", "INTERET CMT", None),
    ("63119710", "INTERETS CMT BP 10.728 KMAD", "BP"),
    ("63119800", "INTERETS EMPRUNTS GROUPE", None),
    ("63119901", "COMPTE D'ATTENTE / INTERETS", None),
    ("63180000", "CHARGES D'INTERET EXER ANTERIEURS", None),
)
# Compte de charge saisi à la main (« Autre », 07/11/2026) : des chiffres seulement
COMPTE_LIBRE = re.compile(r"\d{4,20}")
COMPTE_PAR_TYPE = {
    "timbre": COMPTE_TIMBRE,
    "frais_recuperes_timbre": COMPTE_TIMBRE,
    "commission": COMPTE_COMMISSION,
    "commission_effet": COMPTE_COMMISSION,
    "commission_rtgs": COMPTE_FRAIS_BANCAIRES,
    "commission_prelevement": COMPTE_FRAIS_BANCAIRES,
    "commission_bancaire": COMPTE_FRAIS_BANCAIRES,
    "commission_tenue": COMPTE_FRAIS_BANCAIRES,
    "frais_recuperes": COMPTE_FRAIS_BANCAIRES,
    # Autres banques (09/11/2026), TVA comprise comme les commissions RTGS de BP
    "commission_lcn": COMPTE_FRAIS_BANCAIRES,
    "commission_domiciliation": COMPTE_FRAIS_BANCAIRES,
    "frais_swift": COMPTE_FRAIS_BANCAIRES,
    "frais_cheques": COMPTE_FRAIS_BANCAIRES,
}
# Libellé de chaque type (le champ du compte bancaire n'est plus utilisé depuis le 16/10/2026)
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
    # Autres banques (09/11/2026)
    "commission_lcn": ("Commission LCN", "compte_commission", "compte de charge"),
    "commission_lcn_tva": ("TVA commission LCN", "compte_tva", "compte de TVA"),
    "commission_domiciliation": (
        "Commission domiciliation",
        "compte_commission",
        "compte de charge",
    ),
    "commission_domiciliation_tva": ("TVA commission domiciliation", "compte_tva", "compte de TVA"),
    "frais_recuperes": ("Frais récupérés", "compte_commission", "compte de charge"),
    "frais_recuperes_tva": ("TVA frais récupérés", "compte_tva", "compte de TVA"),
    "frais_recuperes_timbre": ("Timbre frais récupérés", "compte_timbre", "compte de timbre"),
    "frais_swift": ("Frais SWIFT credoc", "compte_commission", "compte de charge"),
    "frais_swift_tva": ("TVA frais SWIFT credoc", "compte_tva", "compte de TVA"),
    "frais_cheques": ("Frais encaissement chèques", "compte_commission", "compte de charge"),
    "frais_cheques_tva": ("TVA frais encaissement chèques", "compte_tva", "compte de TVA"),
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


# TVA sur une ligne à part et la commission qu'elle suit
_TVA_DE = {"tva": "commission", "tva_commission_effet": "commission_effet"}


def details_commissions(lignes: list[tuple[BankTransaction, str]]) -> list[Detail]:
    """Lignes d'une écriture « COM » (11/11/2026) : dans l'ordre du relevé, chaque commission puis
    sa TVA de 10 % (la première encore libre de ce montant), un frais à TVA comprise en hors taxe
    puis TVA ; une TVA sans commission vient à la fin. Le total vaut celui des opérations."""
    ordonnees = sorted(
        lignes, key=lambda item: (item[0].date_operation, item[0].ordre or 0, item[0].id)
    )
    libres: dict[tuple[str, Decimal], list[BankTransaction]] = {}
    for tx, code in ordonnees:
        if code in _TVA_DE:
            libres.setdefault((_TVA_DE[code], -tx.montant), []).append(tx)
    prises: set[int] = set()
    details: list[Detail] = []
    for tx, code in ordonnees:
        if code in _TVA_DE:
            continue
        details.extend(
            Detail(part, 1, montant + ZERO) for part, montant in ventilation(code, -tx.montant)
        )
        candidates = libres.get((code, tva_attendue(-tx.montant)))
        if candidates:
            tva = candidates.pop(0)
            prises.add(tva.id)
            details.append(Detail(TVA_DE_COMMISSION[code], 1, -tva.montant + ZERO))
    details.extend(
        Detail(code, 1, -tx.montant + ZERO)
        for tx, code in ordonnees
        if code in _TVA_DE and tx.id not in prises
    )
    return details


TVA_DE_COMMISSION = {commission: tva for tva, commission in _TVA_DE.items()}


def details_ecriture(famille: "Famille", lignes: list[tuple[BankTransaction, str]]) -> list[Detail]:
    """Lignes de charge d'une écriture automatique : une paire commission + TVA par commission pour
    « COM » (11/11/2026), un total par type sinon."""
    if famille.code == "commissions":
        return details_commissions(lignes)
    return details_par_type(lignes)


def tva_attendue(commission: Decimal) -> Decimal:
    """TVA de 10 % d'une commission (montant positif), arrondie au centime comme la banque."""
    return (commission * TAUX_TVA_FRAIS / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def tva_a_la_main(operations: list[BankTransaction]) -> set[int]:
    """« TAXE SUR VALEUR AJOUTEE » qui n'entrent pas dans l'écriture « COM » (09/11/2026).

    Par compte et par jour, chaque TVA (dans l'ordre du relevé) prend une « COMMISSION » encore
    libre dont la TVA de 10 % vaut exactement son montant ; une commission ne prend qu'une TVA.
    Reste à la main : une TVA sans commission (celle d'un INTERET REMISE LCN A L'ESCOMPTE…). Une
    commission de plus de `SEUIL_MANUEL` passe avec sa TVA depuis le 11/11/2026."""
    par_jour: dict[tuple[int, date], list[BankTransaction]] = {}
    for tx in operations:
        if tx.montant < 0 and type_commission(tx.libelle) in ("commission", "tva"):
            par_jour.setdefault((tx.bank_account_id, tx.date_operation), []).append(tx)
    a_la_main: set[int] = set()
    for lignes in par_jour.values():
        lignes.sort(key=lambda tx: (tx.ordre or 0, tx.id))
        libres: dict[Decimal, list[BankTransaction]] = {}
        for tx in lignes:
            if type_commission(tx.libelle) == "commission":
                libres.setdefault(tva_attendue(-tx.montant), []).append(tx)
        for tx in lignes:
            if type_commission(tx.libelle) != "tva":
                continue
            candidates = libres.get(-tx.montant)
            if not candidates:
                a_la_main.add(tx.id)
                continue
            candidates.pop(0)
    return a_la_main


def regrouper(
    famille: Famille,
    operations: list[BankTransaction],
    jours_dans_sage: set[tuple[int, date]] | None = None,
    hors_famille: set[int] | None = None,
) -> list[JourFrais]:
    """Un groupe par (compte, jour) : seulement des frais débités de la famille ; un jour déjà
    passé dans Sage est écarté. Trié par jour puis compte. `hors_famille` : opérations du libellé
    de la famille qui se passent pourtant à la main (TVA sans sa commission, 09/11/2026)."""
    jours_dans_sage = jours_dans_sage or set()
    hors_famille = hors_famille or set()
    groupes: dict[tuple[int, date], JourFrais] = {}
    for tx in operations:
        code = famille.type_de(tx.libelle)
        if (
            tx.montant >= 0
            or code is None
            or au_dessus_du_seuil(famille, tx.montant, tx.libelle)
            or tx.id in hors_famille
        ):
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
    """Jours à comptabiliser, sans les frais déjà inclus dans une écriture Sage libre, ni les
    journées écartées par l'utilisateur (19/10/2026)."""
    if inclus is None:
        inclus = frais_inclus(db, company_id, account_ids, date_from, date_to)
    ecartes = {
        (a, j) for a, j, f in _ecartes(db, account_ids, date_from, date_to) if f == famille.code
    }
    libres = frais_repository.frais_libres(db, account_ids, date_from, date_to, famille.libelle_sql)
    return regrouper(
        famille,
        [tx for tx in libres if tx.id not in inclus],
        frais_repository.jours_dans_sage(
            db, company_id, account_ids, date_from, date_to, famille.ecriture_sql
        )
        | ecartes,
        # Association TVA ↔ commission sur toutes les opérations libres, avant de retirer les frais
        # inclus dans Sage (09/11/2026)
        tva_a_la_main(libres) if famille is COMMISSIONS else None,
    )


def _tva_a_la_main(
    db: Session, company_id: int, account_ids: list[int], date_from: date, date_to: date
) -> set[int]:
    """TVA libres de la période qui se passent à la main (sans commission associée). Un jour où
    Sage a déjà son écriture « COM » n'est pas concerné : sa TVA y est déjà, la passer à la main
    la compterait deux fois."""
    libres = frais_repository.frais_libres(
        db, account_ids, date_from, date_to, COMMISSIONS.libelle_sql
    )
    dans_sage = frais_repository.jours_dans_sage(
        db, company_id, account_ids, date_from, date_to, COMMISSIONS.ecriture_sql
    )
    return tva_a_la_main(
        [tx for tx in libres if (tx.bank_account_id, tx.date_operation) not in dans_sage]
    )


def _ecartes(
    db: Session, account_ids: list[int], date_from: date, date_to: date
) -> set[tuple[int, date, str]]:
    """(compte, jour, famille) des journées écartées (19/10/2026)."""
    return {
        (row.bank_account_id, row.jour, row.famille)
        for row in frais_repository.jours_ecartes(db, account_ids, date_from, date_to)
    }


def sans_seuil(libelle: str | None) -> bool:
    """Commission ou TVA sur deux lignes (11/11/2026) : le seuil de 200 DH ne s'applique pas."""
    return type_commission(libelle) in TYPES_SANS_SEUIL


def au_dessus_du_seuil(famille: "Famille", montant: Decimal, libelle: str | None) -> bool:
    """Frais débité de plus de `SEUIL_MANUEL` (19/10/2026) : jamais en automatique, sauf un droit
    de timbre et, depuis le 11/11/2026, une commission ou sa TVA sur deux lignes."""
    return (
        famille.code != "timbres"
        and -montant > SEUIL_MANUEL
        and not (famille is COMMISSIONS and sans_seuil(libelle))
    )


def famille_automatique(libelle: str | None, montant: Decimal | None) -> str | None:
    """Code de la famille automatique d'un frais débité, ou None (frais à passer à la main, dont
    un frais de plus de 200 DH hors droits de timbre)."""
    if montant is None or montant >= 0:
        return None
    return next(
        (
            code
            for code, regle in FAMILLES.items()
            if regle.type_de(libelle) and not au_dessus_du_seuil(regle, montant, libelle)
        ),
        None,
    )


def a_la_main(
    tx: BankTransaction, ecartes: set[tuple[int, date, str]], tva_main: set[int] | None = None
) -> bool:
    """Frais qui se passe à la main : pas d'une famille automatique, d'une journée écartée, ou une
    TVA sans sa commission (`tva_main`, 09/11/2026)."""
    if tva_main and tx.id in tva_main:
        return True
    code = famille_automatique(tx.libelle, tx.montant)
    return code is None or (tx.bank_account_id, tx.date_operation, code) in ecartes


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
    ecartes = _ecartes(db, account_ids, date_from, date_to)
    tva_main = _tva_a_la_main(db, company_id, account_ids, date_from, date_to)
    manuels = [
        tx
        for tx, _ in frais_repository.autres_frais(db, account_ids, date_from, date_to)
        if a_la_main(tx, ecartes, tva_main)
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
        if entry.origine != "SIMTIS" and proche(entry)
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
        "numero_piece": entry.numero_piece,
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
        if journal is None or not compte_principal(account):
            raise ConflictError(
                f"Compte {account.bank.code} {account.devise} : renseignez son compte comptable et "
                "son journal des frais (écran Comptes). Rien n'a été comptabilisé."
            )
        retenus.append((account, journal, jour))
    return retenus


@dataclass(frozen=True)
class LigneSaisie:
    """Ligne d'une écriture saisie par l'utilisateur : montant positif et son sens."""

    compte: str
    libelle: str
    montant: Decimal
    sens: str


@dataclass(frozen=True)
class Modification:
    """Changements apportés à une proposition avant sa validation (19/10/2026)."""

    libelle: str | None = None
    date_ecriture: date | None = None
    lignes: tuple[LigneSaisie, ...] | None = None


LIGNES_MAX = 50
COMPTE_MAX = 20


def _lignes_valides(lignes: tuple[LigneSaisie, ...], total: Decimal, cle: str) -> list[LigneSaisie]:
    """Lignes saisies nettoyées ; 409 si l'une est invalide ou si elles ne font pas le total."""
    if not lignes:
        raise ConflictError(f"{cle} : l'écriture doit garder au moins une ligne.")
    if len(lignes) > LIGNES_MAX:
        raise ConflictError(f"{cle} : {LIGNES_MAX} lignes au plus par écriture.")
    propres = []
    for ligne in lignes:
        compte = "".join(ligne.compte.split())
        libelle = " ".join(ligne.libelle.split())
        if not compte or len(compte) > COMPTE_MAX:
            raise ConflictError(
                f"{cle} : chaque ligne a un N° compte général ({COMPTE_MAX} caractères au plus)."
            )
        if not libelle or len(libelle) > LIBELLE_MAX:
            raise ConflictError(
                f"{cle} : chaque ligne a un libellé ({LIBELLE_MAX} caractères au plus)."
            )
        if ligne.montant <= 0 or ligne.montant != ligne.montant.quantize(CENT):
            raise ConflictError(f"{cle} : chaque montant est positif, au centime près.")
        if ligne.sens not in (SENS_CREDIT, SENS_DEBIT):
            raise ConflictError(f"{cle} : le sens d'une ligne est « Crédit » ou « Débit ».")
        propres.append(LigneSaisie(compte, libelle, ligne.montant, ligne.sens))
    # Lignes de charge et de TVA, sans la banque : débits − crédits = total (11/11/2026)
    solde = sum(
        (ligne.montant if ligne.sens == SENS_DEBIT else -ligne.montant for ligne in propres),
        ZERO,
    )
    if solde != total:
        raise ConflictError(
            f"{cle} : les lignes font {solde:.2f}, les opérations {total:.2f} "
            f"(écart {total - solde:.2f}). Rien n'a été comptabilisé."
        )
    return propres


def valider(
    db: Session,
    company_id: int,
    jours: list[tuple[Famille, int, date]],
    *,
    acteur_id: int,
    ip: str | None,
    modifications: dict[tuple[str, int, date], Modification] | None = None,
) -> list[AccountingEntry]:
    """Comptabilise les jours choisis, toutes familles, tous ou aucun : pour chacun, l'écriture de
    sa famille est créée et rapprochée de ses opérations, recalculées par le serveur.

    `modifications` (19/10/2026) : libellé, date et lignes changés par l'utilisateur, contrôlés
    avant toute écriture ; les lignes saisies remplacent le calcul automatique."""
    modifications = modifications or {}
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

    # Modifications contrôlées avant la première écriture
    effectives: dict[tuple[str, int, date], tuple[str, date, list[LigneSaisie] | None]] = {}
    for famille, account, _, jour in retenus:
        cle = (famille.code, account.id, jour.jour)
        modif = modifications.get(cle, Modification())
        nom = f"{account.bank.code}, {jour.jour:%d/%m/%Y}"
        libelle = _libelle_manuel(modif.libelle) if modif.libelle else famille.libelle
        date_ecriture = modif.date_ecriture or jour.jour
        if date_ecriture < jour.jour or date_ecriture > business_today():
            raise ConflictError(
                f"{nom} : la date de l'écriture doit être comprise entre le "
                f"{jour.jour:%d/%m/%Y} (date des frais) et aujourd'hui."
            )
        lignes = (
            _lignes_valides(modif.lignes, jour.total, nom) if modif.lignes is not None else None
        )
        effectives[cle] = (libelle, date_ecriture, lignes)

    entries = []
    for famille, account, journal, jour in retenus:
        ids = [tx.id for tx in jour.operations]
        libelle, date_ecriture, lignes = effectives[(famille.code, account.id, jour.jour)]
        entry = AccountingEntry(
            company_id=company_id,
            bank_account_id=account.id,
            journal=journal,
            compte=compte_principal(account),
            date_ecriture=date_ecriture,
            libelle=libelle,
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
        # Pas de N° pièce : il est donné à l'export vers Sage (09/11/2026)
        for ordre, ligne in enumerate(lignes or [], start=1):
            db.add(
                FraisLigne(
                    accounting_entry_id=entry.id,
                    ordre=ordre,
                    compte=ligne.compte,
                    libelle=ligne.libelle,
                    montant=ligne.montant,
                    sens=ligne.sens,
                )
            )
        modifiee = libelle != famille.libelle or date_ecriture != jour.jour or lignes is not None
        audit_service.log(
            db,
            user_id=acteur_id,
            action=f"comptabilisation_{famille.code}",
            entite=ENTITE,
            entite_id=entry.id,
            apres={
                **_snapshot(entry, match.code, ids),
                "par_type": {detail.type: detail.total for detail in jour.details},
                **(
                    {
                        "modifiee": True,
                        "date_des_frais": jour.jour,
                        "lignes_saisies": [
                            {
                                "compte": ligne.compte,
                                "libelle": ligne.libelle,
                                "montant": ligne.montant,
                                "sens": ligne.sens,
                            }
                            for ligne in lignes or []
                        ],
                    }
                    if modifiee
                    else {}
                ),
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
    # Lignes saisies par l'utilisateur (19/10/2026) plutôt que calculées
    modifiee: bool = False


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
    ids = [entry.id for entry, _, _ in rows]
    operations = frais_repository.operations_of_entries(db, ids)
    saisies = frais_repository.lignes_saisies(db, ids)
    result = []
    for entry, code, nb in rows:
        regle = famille_de(entry)
        account = accounts[entry.bank_account_id]
        lignes = lignes_ecriture(
            regle, account, entry, operations.get(entry.id, []), saisies.get(entry.id)
        )
        modifiee = entry.id in saisies or (regle is not MANUELLE and entry.libelle != regle.libelle)
        result.append(EcritureSimtis(entry, account.bank.code, code, nb, lignes, regle, modifiee))
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
    # Libellé saisi par l'utilisateur (19/10/2026) ; None : celui de l'écriture (« TVA … »)
    libelle: str | None = None

    @property
    def banque(self) -> bool:
        return self.type is None


def est_ligne_tva(type_ligne: str | None) -> bool:
    """Ligne de TVA d'une écriture : « tva », « tva_commission_effet », « commission_rtgs_tva »…"""
    return bool(type_ligne) and (
        type_ligne == "tva" or type_ligne.startswith("tva_") or type_ligne.endswith("_tva")
    )


def texte_ligne(libelle_ecriture: str, ligne: "LigneGL") -> str:
    """Libellé d'une ligne dans Sage : le libellé saisi, sinon celui de l'écriture. La ligne banque
    d'une écriture « FRAIS » s'appelle « COM » (11/11/2026), ses lignes de détail restent FRAIS."""
    if ligne.libelle:
        return ligne.libelle
    if ligne.banque and libelle_ecriture == LIBELLE_FRAIS:
        return LIBELLE_COMMISSION
    return libelle_ligne(libelle_ecriture, ligne.type)


def libelle_ligne(libelle_ecriture: str, type_ligne: str | None) -> str:
    """Libellé d'une ligne dans Sage (14/10/2026) : celui de l'écriture, précédé de « TVA » pour
    une ligne de TVA (« COM » → « TVA COM », « FRAIS » → « TVA FRAIS »)."""
    return f"TVA {libelle_ecriture}" if est_ligne_tva(type_ligne) else libelle_ecriture


def numero_piece(banque: str, jour: date, numero: int) -> str:
    """« BP2610123 » (16/10/2026) : code de la banque, année et mois de la date d'écriture, puis
    le n° d'ordre du mois pour cette banque sur 3 chiffres."""
    if not 1 <= numero <= PIECE_MAX:
        raise ConflictError(
            f"Plus de {PIECE_MAX} écritures de frais {banque} en {jour:%m/%Y} : le n° de pièce "
            "sur 3 chiffres est épuisé."
        )
    return f"{banque}{jour:%y%m}{numero:03d}"


def premiere_piece(texte: str, banque: str, annee: int, mois: int, nb: int) -> int:
    """Rang de la première pièce saisie par le comptable à l'export (09/11/2026) : « BP2610001 »
    pour BP en octobre 2026 ; 409 si la banque, le mois ou les 3 chiffres ne vont pas, ou si les
    `nb` écritures dépassent la pièce 999 du mois."""
    numero = "".join((texte or "").split()).upper()
    prefixe = f"{banque}{annee % 100:02d}{mois:02d}"
    rang = numero[len(prefixe) :]
    if not numero.startswith(prefixe) or not re.fullmatch(r"\d{3}", rang) or int(rang) == 0:
        raise ConflictError(
            f"Le N° de la première pièce s'écrit {prefixe} suivi de 3 chiffres (ex. {prefixe}001) "
            f"pour {banque} en {mois:02d}/{annee}."
        )
    if int(rang) + nb - 1 > PIECE_MAX:
        raise ConflictError(
            f"{nb} écriture{'s' if nb > 1 else ''} à partir de {numero} dépassent {prefixe}"
            f"{PIECE_MAX} : choisissez un N° plus petit."
        )
    return int(rang)


def compte_charge(type_ligne: str | None, libelle_ecriture: str, banque: str) -> str | None:
    """Compte général Sage d'une ligne de frais (16/10/2026) : la TVA sur 34552142, chaque type
    automatique sur le sien ; une écriture manuelle par son libellé (AGIOS selon la banque, puis
    l'intitulé d'un compte de `COMPTES_FRAIS` (05/11/2026), COM / COMMISSION), sinon les frais
    bancaires."""
    if est_ligne_tva(type_ligne):
        return COMPTE_TVA
    if type_ligne in COMPTE_PAR_TYPE:
        return COMPTE_PAR_TYPE[type_ligne]
    texte = _sans_ponctuation(libelle_ecriture)
    premier = texte.split()[0] if texte else ""
    if premier == "AGIOS":
        return COMPTES_AGIOS.get(banque)
    if compte := compte_du_libelle(libelle_ecriture, banque):
        return compte
    if premier in ("COM", "COMMISSION", "COMMISSIONS"):
        return COMPTE_COMMISSION
    return COMPTE_FRAIS_BANCAIRES


def _cle_intitule(texte: str | None) -> str:
    """« Intérêts crédit affacturage » → « INTERET CREDIT AFFACTURAGE » : sans ponctuation ni
    accents, INTERETS = INTERET."""
    mots = _sans_ponctuation(texte).split()
    return " ".join("INTERET" if mot == "INTERETS" else mot for mot in mots)


def comptes_frais(banque: str | None = None) -> list[tuple[str, str]]:
    """(numéro, intitulé) des comptes de frais proposés pour un compte de cette banque (tous sans
    banque) ; un compte réservé à une banque n'est proposé que pour elle (05/11/2026)."""
    return [
        (numero, intitule)
        for numero, intitule, reservee in COMPTES_FRAIS
        if banque is None or reservee in (None, banque)
    ]


def compte_du_libelle(libelle: str, banque: str) -> str | None:
    """Compte de la liste dont l'intitulé commence le libellé (05/11/2026), le plus long gagnant
    (« INTERET CMT / OXYGENE » avant « INTERET CMT ») ; None si aucun."""
    texte = _cle_intitule(libelle)
    trouves = [
        (len(cle), numero)
        for numero, intitule in comptes_frais(banque)
        if (cle := _cle_intitule(intitule)) and (texte == cle or texte.startswith(cle + " "))
    ]
    return max(trouves)[1] if trouves else None


def ligne_banque(compte: str | None, montant: Decimal) -> LigneGL:
    """Contrepartie de l'écriture sur le compte comptable du compte bancaire (11/11/2026) : au
    crédit pour un frais (montant positif), au débit pour un remboursement."""
    return LigneGL(
        None,
        "Banque",
        compte,
        -montant if montant < 0 else None,
        montant if montant > 0 else None,
        nom_compte="compte comptable",
    )


def lignes_gl(account: BankAccount, details: list[Detail], total: Decimal) -> list[LigneGL]:
    """Une ligne par détail AU DÉBIT de son compte de charge ou de TVA, puis le total au crédit du
    compte bancaire (11/11/2026, remplace les lignes au crédit sans ligne banque du 17/10/2026)."""
    return [
        *(
            LigneGL(
                detail.type,
                TYPES[detail.type][0],
                compte_charge(detail.type, "", account.bank.code),
                detail.total,
                None,
            )
            for detail in details
        ),
        ligne_banque(account.compte_comptable, total),
    ]


def _lignes_de(
    famille: Famille,
    account: BankAccount,
    entry: AccountingEntry,
    operations: list[BankTransaction],
) -> list[LigneGL]:
    details = details_ecriture(
        famille, [(tx, code) for tx in operations if (code := famille.type_de(tx.libelle))]
    )
    return lignes_gl(account, details, entry.montant)


def lignes_manuelle(
    compte: str | None,
    montant: Decimal,
    montant_tva: Decimal | None,
    libelle: str = "",
    banque: str = "",
) -> list[LigneGL]:
    """Écriture manuelle : le frais (hors taxe si la TVA est séparée) puis sa TVA, sur leurs
    comptes (16/10/2026), puis la contrepartie sur `compte`, le compte comptable du compte bancaire
    (11/11/2026). Un frais (montant positif côté Sage) met ses lignes au débit et la banque au
    crédit, un remboursement l'inverse."""
    total = abs(montant)
    parts = (
        [("frais", "Frais", total - montant_tva), ("tva", "TVA", montant_tva)]
        if montant_tva
        else [("frais", "", total)]
    )
    return [
        *(
            LigneGL(
                code,
                nom,
                compte_charge(code, libelle, banque),
                part if montant > 0 else None,
                None if montant > 0 else part,
            )
            for code, nom, part in parts
        ),
        ligne_banque(compte, montant),
    ]


def lignes_ecriture(
    famille: Famille,
    account: BankAccount,
    entry: AccountingEntry,
    operations: list[BankTransaction],
    saisies: list[FraisLigne] | None = None,
) -> list[LigneGL]:
    if saisies:
        # Lignes saisies avant la validation (19/10/2026) : telles quelles, puis la banque
        return [
            *(
                LigneGL(
                    "saisie",
                    "",
                    ligne.compte,
                    ligne.montant if ligne.sens == SENS_DEBIT else None,
                    ligne.montant if ligne.sens == SENS_CREDIT else None,
                    libelle=ligne.libelle,
                )
                for ligne in saisies
            ),
            ligne_banque(account.compte_comptable, entry.montant),
        ]
    if famille is MANUELLE:
        return lignes_manuelle(
            account.compte_comptable,
            entry.montant,
            entry.montant_tva,
            entry.libelle,
            account.bank.code,
        )
    return _lignes_de(famille, account, entry, operations)


def _equilibree(entry: AccountingEntry, lignes: list[LigneGL]) -> None:
    """Écriture équilibrée (11/11/2026) : débits = crédits, et la ligne banque (crédit − débit)
    vaut le montant de l'écriture."""
    credit = sum((ligne.credit or ZERO for ligne in lignes), ZERO)
    debit = sum((ligne.debit or ZERO for ligne in lignes), ZERO)
    banque = sum(
        ((ligne.credit or ZERO) - (ligne.debit or ZERO) for ligne in lignes if ligne.banque), ZERO
    )
    if credit != debit or banque != entry.montant:
        raise ConflictError(
            f"Écriture « {entry.libelle} » du {entry.date_ecriture:%d/%m/%Y} : ses opérations ne "
            "font plus son montant. "
            "Rien n'a été exporté."
        )


# --- Export pour Sage -----------------------------------------------------------------------------


@dataclass(frozen=True)
class AExporter:
    """Écritures de frais pas encore exportées d'une banque et d'un mois (09/11/2026)."""

    bank_id: int
    bank_code: str
    bank_logo: str | None
    annee: int
    mois: int
    nb: int


def a_exporter(db: Session, company_id: int) -> list[AExporter]:
    """Ce qui reste à exporter vers Sage, par banque (ordre d'affichage) puis mois : un fichier
    par banque et par mois."""
    accounts = {a.id: a for a in _accounts(db, company_id, None)}
    nombres: dict[tuple[int, int, int], int] = {}
    for entry, _, _ in frais_repository.ecritures_simtis(
        db, company_id, bank_account_id=None, date_from=None, date_to=None, non_exportees=True
    ):
        account = accounts.get(entry.bank_account_id)
        if account is None:
            continue
        cle = (account.bank_id, entry.date_ecriture.year, entry.date_ecriture.month)
        nombres[cle] = nombres.get(cle, 0) + 1
    banques = {a.bank_id: a.bank for a in accounts.values()}
    return [
        AExporter(bank_id, banques[bank_id].code, banques[bank_id].logo, annee, mois, nb)
        for (bank_id, annee, mois), nb in sorted(
            nombres.items(),
            key=lambda item: (banques[item[0][0]].ordre_affichage, item[0][1], item[0][2]),
        )
    ]


def exporter(
    db: Session,
    company_id: int,
    *,
    bank_id: int,
    annee: int,
    mois: int,
    premiere: str,
    acteur_id: int,
    ip: str | None,
) -> tuple[str, bytes, int]:
    """UN fichier CSV à intégrer dans Sage (16/10/2026, « import paramétrable ») pour UNE banque
    et UN mois (09/11/2026) : les écritures pas encore exportées, par date ; par écriture, une
    ligne par type (une paire commission + TVA par commission pour « COM ») au débit de son compte
    et la contrepartie au crédit du compte comptable du compte bancaire (11/11/2026), Sens « D » /
    « C ».

    Le N° pièce est donné ici : `premiere` (« BP2610001 ») pour la première, puis +1 dans
    l'ordre des dates. Chaque écriture ne s'exporte qu'une fois ; elle est marquée exportée."""
    if not 1 <= mois <= 12:
        raise ConflictError("Choisissez un mois de 1 à 12.")
    reconciliation_repository.lock_company(db, company_id)
    accounts = {a.id: a for a in _accounts(db, company_id, None) if a.bank_id == bank_id}
    if not accounts:
        raise NotFoundError("Banque introuvable pour cette société.")
    banque = next(iter(accounts.values())).bank.code
    debut = date(annee, mois, 1)
    fin = (debut + timedelta(days=31)).replace(day=1) - timedelta(days=1)
    rows = [
        row
        for row in frais_repository.ecritures_simtis(
            db,
            company_id,
            bank_account_id=None,
            date_from=debut,
            date_to=fin,
            non_exportees=True,
        )
        if row[0].bank_account_id in accounts
    ]
    if not rows:
        raise ConflictError(f"Aucune écriture de frais {banque} à exporter en {mois:02d}/{annee}.")
    rang = premiere_piece(premiere, banque, annee, mois, len(rows))
    rows.sort(key=lambda row: (row[0].date_ecriture, row[0].id))
    operations = frais_repository.operations_of_entries(db, [entry.id for entry, _, _ in rows])
    saisies = frais_repository.lignes_saisies(db, [entry.id for entry, _, _ in rows])
    lignes = {}
    manquants: dict[str, set[str]] = {}
    for entry, _, _ in rows:
        account = accounts[entry.bank_account_id]
        lignes[entry.id] = lignes_ecriture(
            famille_de(entry), account, entry, operations.get(entry.id, []), saisies.get(entry.id)
        )
        _equilibree(entry, lignes[entry.id])
        absents = {ligne.nom_compte for ligne in lignes[entry.id] if not ligne.compte}
        if absents:
            manquants.setdefault(f"{account.bank.code} {account.devise}", set()).update(
                nom or "compte comptable" for nom in absents
            )
    en_devise = sorted(
        {
            f"{accounts[entry.bank_account_id].bank.code} {accounts[entry.bank_account_id].devise}"
            for entry, _, _ in rows
            if accounts[entry.bank_account_id].devise != "MAD"
        }
    )
    if en_devise:
        # Sage attend le montant en DH, le montant devise, le cours et le code ISO : le cours n'est
        # pas encore connu de SIMTIS (règle à définir avec le métier)
        raise ConflictError(
            "Les écritures de frais d'un compte en devise ne s'exportent pas encore vers Sage "
            f"({', '.join(en_devise)}) : le cours de la devise n'est pas connu. Filtrez sur un "
            "compte en MAD."
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

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=CSV_SEPARATEUR, lineterminator="\r\n")
    maintenant = datetime.now(UTC)
    for index, (entry, _, _) in enumerate(rows):
        piece = numero_piece(banque, debut, rang + index)
        for ligne in lignes[entry.id]:
            # Sage : un montant toujours positif et son sens ; Référence et les autres colonnes
            # facultatives restent vides (16/10/2026)
            debit = bool(ligne.debit)
            writer.writerow(
                [f"{entry.date_ecriture:%d/%m/%Y}", piece, entry.journal, ligne.compte, "",
                 texte_ligne(entry.libelle, ligne),
                 montant_csv(ligne.debit if debit else ligne.credit),
                 SENS_CSV[SENS_DEBIT if debit else SENS_CREDIT],
                 "", "", "", "", "", "", ""]
            )  # fmt: skip
        avant = {"numero_piece": entry.numero_piece, "exportee_le": entry.exportee_le}
        entry.numero_piece = piece
        entry.exportee_le = maintenant
        audit_service.log(
            db,
            user_id=acteur_id,
            action="export_ecriture_frais",
            entite=ENTITE,
            entite_id=entry.id,
            avant=avant,
            apres={"numero_piece": piece, "exportee_le": maintenant},
            ip=ip,
        )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="export_frais_sage",
        entite="company",
        entite_id=company_id,
        apres={
            "banque": banque,
            "mois": f"{mois:02d}/{annee}",
            "nb_ecritures": len(rows),
            "premiere_piece": numero_piece(banque, debut, rang),
            "derniere_piece": numero_piece(banque, debut, rang + len(rows) - 1),
        },
        ip=ip,
    )
    _commit(db)
    nom = f"ecritures-frais-{banque}-{annee}-{mois:02d}.csv"
    return nom, buffer.getvalue().encode(CSV_ENCODAGE, errors="replace"), len(rows)


def codes_rapprochement(db: Session, entries: list[AccountingEntry]) -> list[str | None]:
    """Code « BANQUE-AA-NNNNNN » du rapprochement de chaque écriture validée : le N° pièce
    n'existe qu'après l'export (09/11/2026)."""
    codes = []
    for entry in entries:
        match = frais_repository.active_match_of_entry(db, entry.id)
        codes.append(match.code if match else None)
    return codes


def montant_csv(montant: Decimal) -> str:
    """« 1234,50 » : virgule décimale, sans séparateur de milliers (CSV français de Sage)."""
    return f"{montant:.2f}".replace(".", ",")


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
    ecartes = _ecartes(db, list(accounts), date_from, date_to)
    tva_main = _tva_a_la_main(db, company_id, list(accounts), date_from, date_to)
    return [
        AutreFrais(
            tx,
            accounts[tx.bank_account_id].bank.code,
            accounts[tx.bank_account_id].bank.logo,
            pointage,
        )
        for tx, pointage in frais_repository.autres_frais(db, list(accounts), date_from, date_to)
        if a_la_main(tx, ecartes, tva_main) and tx.id not in inclus
    ]


@dataclass
class FraisInclus:
    """Frais encore « à comptabiliser » mais déjà dans une écriture Sage libre : à rapprocher."""

    transaction: BankTransaction
    bank_code: str
    bank_logo: str | None
    ecriture: AccountingEntry


@dataclass
class JourEcarte:
    """Journée écartée de la comptabilisation automatique (19/10/2026)."""

    ecarte: FraisJourEcarte
    bank_code: str
    bank_logo: str | None
    famille: Famille


@dataclass
class TableauFrais:
    propositions: list[Proposition]
    ecritures: list["EcritureSimtis"]
    autres: list[AutreFrais]
    inclus: list[FraisInclus]
    ecartes: list[JourEcarte] = field(default_factory=list)


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
        ecartes=[
            JourEcarte(
                row,
                accounts[row.bank_account_id].bank.code,
                accounts[row.bank_account_id].bank.logo,
                FAMILLES[row.famille],
            )
            for row in frais_repository.jours_ecartes(db, list(accounts), date_from, date_to)
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
    if montant is not None:
        return famille_automatique(libelle, montant) is not None
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
    compte: str | None = None,
) -> AccountingEntry:
    """Une écriture saisie à la main pour des frais d'un même compte, créée et rapprochée d'emblée.

    Le total est recalculé sur les opérations (jamais repris de l'écran). Avec de la TVA, le frais
    hors taxe est le total moins la TVA saisie, ou la ventilation au taux donné. `compte` : compte
    de charge choisi dans `COMPTES_FRAIS` (05/11/2026) ou saisi (« Autre », 4 à 20 chiffres,
    07/11/2026), sinon celui du libellé.
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
    comptes_operations = sorted({tx.bank_account_id for tx in operations})
    ecartes = _ecartes(db, comptes_operations, debut, fin)
    tva_main = _tva_a_la_main(db, company_id, comptes_operations, debut, fin)
    automatiques = [tx for tx in operations if not a_la_main(tx, ecartes, tva_main)]
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
    if journal is None or not compte_principal(account):
        raise ConflictError(
            f"Compte {account.bank.code} {account.devise} : renseignez son compte comptable et "
            "son journal des frais (écran Comptes)."
        )
    compte_libre = compte is not None and compte not in dict(comptes_frais(account.bank.code))
    if compte_libre:
        # « Autre » (07/11/2026) : un numéro saisi à la main, jamais un compte de la liste réservé
        # à une autre banque
        if compte in {numero for numero, _, _ in COMPTES_FRAIS}:
            raise ConflictError(
                f"Le compte {compte} n'est pas un compte de frais proposé pour {account.bank.code}."
            )
        if not COMPTE_LIBRE.fullmatch(compte):
            raise ConflictError(
                f"Compte « {compte} » : un numéro de compte a de 4 à 20 chiffres, sans espace."
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
        compte=compte_principal(account),
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
    # Pas de N° pièce : il est donné à l'export vers Sage (09/11/2026)
    lignes = lignes_manuelle(None, montant, montant_tva, texte, account.bank.code)
    if compte is not None and compte != lignes[0].compte:
        # Compte choisi autre que celui du libellé : lignes enregistrées, la TVA reste la sienne
        # Sans la ligne banque, recalculée à la lecture (11/11/2026)
        for ordre, ligne in enumerate((ligne for ligne in lignes if not ligne.banque), start=1):
            db.add(
                FraisLigne(
                    accounting_entry_id=entry.id,
                    ordre=ordre,
                    compte=ligne.compte if est_ligne_tva(ligne.type) else compte,
                    libelle=texte_ligne(texte, ligne)[:LIBELLE_MAX],
                    montant=ligne.debit or ligne.credit,
                    sens=SENS_DEBIT if ligne.debit else SENS_CREDIT,
                )
            )
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
            "compte_charge": compte or lignes[0].compte,
            "compte_libre": compte_libre,
        },
        ip=ip,
    )
    _commit(db)
    return entry


# --- Écarter / reproposer une journée (19/10/2026) ------------------------------------------------


def ecarter(
    db: Session,
    company_id: int,
    jours: list[tuple[Famille, int, date]],
    *,
    motif: str | None,
    acteur_id: int,
    ip: str | None,
) -> int:
    """Écarte des journées proposées, toutes ou aucune : elles ne sont plus proposées, leurs frais
    passent dans « Autres frais à passer à la main »."""
    if not jours:
        raise ConflictError("Choisissez au moins une journée à écarter.")
    texte = " ".join((motif or "").split()) or None
    if texte and len(texte) > reconciliation_service.COMMENTAIRE_MAX:
        raise ConflictError(
            f"Le motif ne peut pas dépasser {reconciliation_service.COMMENTAIRE_MAX} caractères."
        )
    reconciliation_repository.lock_company(db, company_id)
    accounts = {a.id: a for a in _accounts(db, company_id, None)}
    for regle, account_id, jour in jours:
        if account_id not in accounts:
            raise NotFoundError("Compte bancaire introuvable.")
        proposes = {j.jour for j in _jours(db, regle, company_id, [account_id], jour, jour)}
        if jour not in proposes:
            raise ConflictError(
                f"{accounts[account_id].bank.code}, {jour:%d/%m/%Y} : plus de {regle.nom} "
                "proposés ce jour-là. Rien n'a été écarté, rechargez la liste."
            )
    for regle, account_id, jour in jours:
        db.add(
            FraisJourEcarte(
                company_id=company_id,
                bank_account_id=account_id,
                jour=jour,
                famille=regle.code,
                motif=texte,
                cree_par_id=acteur_id,
            )
        )
        audit_service.log(
            db,
            user_id=acteur_id,
            action="ecartement_frais",
            entite="bank_account",
            entite_id=account_id,
            apres={"jour": jour, "famille": regle.code, "motif": texte},
            ip=ip,
        )
    _commit(db)
    return len(jours)


def reproposer(
    db: Session,
    company_id: int,
    jours: list[tuple[Famille, int, date]],
    *,
    acteur_id: int,
    ip: str | None,
) -> int:
    """Annule l'écartement de journées : SIMTIS les propose de nouveau."""
    if not jours:
        raise ConflictError("Choisissez au moins une journée à reproposer.")
    reconciliation_repository.lock_company(db, company_id)
    accounts = {a.id: a for a in _accounts(db, company_id, None)}
    lignes = []
    for regle, account_id, jour in jours:
        if account_id not in accounts:
            raise NotFoundError("Compte bancaire introuvable.")
        row = frais_repository.jour_ecarte(db, account_id, jour, regle.code)
        if row is None:
            raise NotFoundError(
                f"{accounts[account_id].bank.code}, {jour:%d/%m/%Y} : cette journée n'est pas "
                "écartée."
            )
        lignes.append(row)
    for row in lignes:
        audit_service.log(
            db,
            user_id=acteur_id,
            action="reproposition_frais",
            entite="bank_account",
            entite_id=row.bank_account_id,
            avant={"jour": row.jour, "famille": row.famille, "motif": row.motif},
            ip=ip,
        )
        db.delete(row)
    _commit(db)
    return len(lignes)


# --- Frais à justifier auprès de la banque (19/10/2026) -------------------------------------------

JUSTIFICATIF_HEADERS = (
    "Banque",
    "Compte",
    "Date d'opération",
    "Date de valeur",
    "Libellé",
    "Référence",
    "Montant",
    "Statut",
    "N° pièce SIMTIS",
    "Commentaire",
)


def _statut_justificatif(tx: BankTransaction, origine: str | None) -> str:
    if origine == "SIMTIS":
        return "Comptabilisé"
    if tx.statut == "Rapprochée":
        return "Rapprochée"
    return "À comptabiliser" if tx.statut == "Non rapprochée" else tx.statut


def justificatif(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None,
    date_from: date | None,
    date_to: date | None,
    acteur_id: int,
    ip: str | None,
) -> tuple[str, bytes, int]:
    """Fichier Excel des frais de plus de 200 DH (hors droits de timbre et, depuis le 11/11/2026,
    commissions et TVA sur deux lignes) de la période, quel que soit leur statut, à envoyer à la
    banque pour justification ; un total par banque et un total général. Rien n'est marqué : le
    fichier se retélécharge."""
    date_from, date_to = _periode(date_from, date_to)
    accounts = {a.id: a for a in _accounts(db, company_id, bank_account_id)}
    rows = frais_repository.frais_au_dessus(db, list(accounts), date_from, date_to, SEUIL_MANUEL)
    rows = [
        (tx, piece, origine)
        for tx, piece, origine in rows
        if not est_timbre(tx.libelle) and not sans_seuil(tx.libelle)
    ]
    if not rows:
        raise ConflictError(f"Aucun frais de plus de {SEUIL_MANUEL:.0f} DH sur cette période.")
    rows.sort(
        key=lambda row: (
            accounts[row[0].bank_account_id].bank.ordre_affichage,
            row[0].bank_account_id,
            row[0].date_operation,
            row[0].id,
        )
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Frais à justifier"
    sheet.append(JUSTIFICATIF_HEADERS)
    gras = Font(bold=True)
    for cell in sheet[1]:
        cell.font = gras
    general = ZERO
    banque_courante: str | None = None
    sous_total = ZERO

    def total_banque() -> None:
        sheet.append([f"Total {banque_courante}", None, None, None, None, None, sous_total])
        for cell in sheet[sheet.max_row]:
            cell.font = gras

    for tx, piece, origine in rows:
        account = accounts[tx.bank_account_id]
        if banque_courante is not None and account.bank.code != banque_courante:
            total_banque()
            sous_total = ZERO
        banque_courante = account.bank.code
        montant = -tx.montant
        sous_total += montant
        general += montant
        sheet.append(
            [account.bank.code, account.numero, tx.date_operation, tx.date_valeur, tx.libelle,
             tx.reference, montant, _statut_justificatif(tx, origine),
             piece if origine == "SIMTIS" else None, tx.commentaire]
        )  # fmt: skip
    total_banque()
    sheet.append(["Total général", None, None, None, None, None, general])
    for cell in sheet[sheet.max_row]:
        cell.font = gras
    for row in sheet.iter_rows(min_row=2):
        row[2].number_format = "DD/MM/YYYY"
        row[3].number_format = "DD/MM/YYYY"
        row[6].number_format = "#,##0.00"
    for index, width in enumerate((10, 22, 16, 16, 48, 22, 14, 18, 16, 30), start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    audit_service.log(
        db,
        user_id=acteur_id,
        action="export_frais_banque",
        entite="company",
        entite_id=company_id,
        apres={
            "du": date_from,
            "au": date_to,
            "bank_account_id": bank_account_id,
            "nb_frais": len(rows),
            "total": general,
        },
        ip=ip,
    )
    _commit(db)
    buffer = BytesIO()
    workbook.save(buffer)
    nom = f"frais-a-justifier-{date_from:%Y%m%d}-{date_to:%Y%m%d}.xlsx"
    return nom, buffer.getvalue(), len(rows)
