"""Import des relevés bancaires, en deux temps : analyse et aperçu (P7.1), puis confirmation (P7.2).

Déroulé (architecture technique §5) : lecture du classeur → détection de la ligne d'en-tête et des
colonnes → correspondance colonnes / champs standard (proposée, ou choisie par l'utilisateur) →
contrôle et normalisation de chaque ligne → aperçu : lignes valides, en erreur, en double.

Règles :
- fichiers Excel `.xlsx` ou `.xls`, 20 Mo et 50 000 lignes au plus (`import_file`) ;
- le compte choisi doit être actif ; il fixe la société et la banque du relevé ;
- une ligne sans date d'opération ni montant (titre, « Solde initial »), ou une ligne de total ou de
  solde sans date, est ignorée ; toute autre ligne incomplète est en erreur, jamais corrigée en silence ;
- une ligne est en double si elle est déjà importée pour ce compte, ou si elle répète une ligne
  identique du même fichier ;
- un Pointage est rattaché au type actif de même code ou libellé ; inconnu, il reste vide ;
- l'analyse n'écrit rien en base ; la confirmation renvoie le fichier, l'analyse à nouveau et
  enregistre les lignes retenues (voir `confirm_statement`).
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    BalanceCheck,
    Bank,
    BankAccount,
    BankAccountBalance,
    BankStatement,
    BankTransaction,
    ColumnMapping,
    ImportBatch,
    PointageType,
)
from app.repositories import account_repository, balance_repository, import_repository
from app.services import account_service, audit_service, import_file, position_service
from app.services.errors import ConflictError, NotFoundError
from app.services.import_file import Column, IgnoredLine, ImportField, Mapping
from app.services.normalization_service import (
    balance_line_kind,
    clean_libelle,
    clean_text,
    extract_reference,
    file_hash,
    guess_pointage,
    is_blank,
    label_key,
    line_hash,
    normalize_header,
    parse_amount,
    parse_date,
)

TYPE_IMPORT = "Banque"
LETTRAGE_MAX = 120
REFERENCE_MAX = 60
# Lignes sans date à ignorer : totaux et soldes de début ou de fin de relevé
_SUMMARY_LINE = re.compile(r"^(TOTAL|SOLDE|ANCIEN SOLDE|NOUVEAU SOLDE|REPORT)\b")


# Structure standard du relevé (CDC §4, architecture technique §5.2). Société et banque viennent du
# compte choisi ; une colonne « Banque » du fichier sert seulement à vérifier qu'il s'agit du bon compte.
STATEMENT_FIELDS: tuple[ImportField, ...] = (
    ImportField(
        "date_operation",
        "Date d'opération",
        True,
        ("date operation", "date d operation", "date de l operation", "date op", "date"),
    ),
    ImportField(
        "date_valeur", "Date de valeur", False, ("date valeur", "date de valeur", "valeur")
    ),
    ImportField(
        "libelle",
        "Libellé",
        True,
        ("libelle", "libelle operation", "designation", "description", "operation", "nature"),
    ),
    ImportField("reference", "Référence", False, ("reference", "ref", "n piece", "numero piece")),
    ImportField("debit", "Débit", False, ("debit", "debits", "montant debit", "sortie", "retrait")),
    ImportField(
        "credit", "Crédit", False, ("credit", "credits", "montant credit", "entree", "versement")
    ),
    ImportField("montant", "Montant signé", False, ("montant", "montant signe")),
    ImportField("solde", "Solde", False, ("solde", "solde progressif", "nouveau solde")),
    ImportField("pointage", "Pointage", False, ("pointage", "type operation", "type d operation")),
    ImportField(
        "lettrage_escompte",
        "Lettrage / Escompte",
        False,
        ("lettrage escompte", "lettrage", "escompte"),
    ),
    ImportField("commentaire", "Commentaire", False, ("commentaire", "observation", "remarque")),
    ImportField("banque", "Banque", False, ("banque",)),
)
FIELD_CODES = tuple(item.code for item in STATEMENT_FIELDS)
FIELD_LABELS = {item.code: item.libelle for item in STATEMENT_FIELDS}


@dataclass
class AnalysedLine:
    numero: int  # numéro de la ligne dans Excel
    statut: str  # Valide / Erreur / Doublon
    motifs: list[str]
    date_operation: date | None = None
    date_valeur: date | None = None
    libelle: str | None = None
    reference: str | None = None
    debit: Decimal | None = None
    credit: Decimal | None = None
    montant: Decimal | None = None
    solde: Decimal | None = None
    pointage: str | None = None  # valeur lue dans le fichier, telle quelle
    pointage_type_id: int | None = None
    pointage_libelle: str | None = None
    # Pointage déduit du libellé et du sens (pas de valeur connue dans le fichier)
    pointage_auto: bool = False
    lettrage_escompte: str | None = None
    commentaire: str | None = None
    # « Corrigée » quand l'aperçu modifiable a changé au moins un champ (confirmation avec `lignes`)
    origine: str = "Fichier"
    # Solde calculé par SIMTIS : le fichier n'a pas de soldes (décision du 08/10/2026)
    solde_calcule: bool = False
    # Aperçu seulement : solde calculé depuis le solde d'ouverture choisi. Il ne va jamais dans
    # `solde`, qui entre dans l'empreinte de la ligne et dans la comparaison avec l'envoi de l'écran
    solde_apercu: Decimal | None = None
    # Aperçu seulement : solde de la banque − solde attendu (précédent − débit + crédit), s'ils
    # diffèrent (contrôle, 09/10/2026) ; jamais bloquant
    ecart_solde: Decimal | None = None
    hash_ligne: str | None = None
    # Doublon interne au fichier : numéro de la première ligne identique (gardable à la confirmation)
    doublon_de: int | None = None


@dataclass
class Summary:
    nb_lignes: int = 0
    nb_valides: int = 0
    nb_erreurs: int = 0
    nb_doublons: int = 0
    nb_ignorees: int = 0
    total_debit: Decimal = Decimal("0.00")
    total_credit: Decimal = Decimal("0.00")
    periode_debut: date | None = None
    periode_fin: date | None = None
    solde_ouverture: Decimal | None = None
    solde_cloture: Decimal | None = None
    # Soldes lus sur une ligne SOLDE INITIAL / SOLDE FINAL du fichier (sinon déduits des lignes)
    solde_ouverture_fichier: bool = False
    solde_cloture_fichier: bool = False
    # Solde d'ouverture + mouvements = solde de clôture ? None si l'un des deux est inconnu
    soldes_coherents: bool | None = None


@dataclass
class StatementAnalysis:
    account: BankAccount
    fichier_nom: str
    fichier_hash: str
    deja_importe: bool
    feuilles: list[str]
    feuille: str
    ligne_entete: int
    colonnes: list[Column]
    mapping: Mapping
    mapping_source: str  # Détection / Modèle de la banque / Utilisateur
    erreurs_mapping: list[str]
    lignes: list[AnalysedLine] = field(default_factory=list)
    resume: Summary = field(default_factory=Summary)
    # Montants des lignes SOLDE INITIAL et SOLDE FINAL du fichier, s'il en a
    solde_initial_fichier: Decimal | None = None
    solde_final_fichier: Decimal | None = None
    # Lignes non retenues (titres, totaux, soldes) et leur raison : affichées, jamais importées
    lignes_ignorees: list[IgnoredLine] = field(default_factory=list)
    # Fichier sans soldes : SIMTIS les calcule depuis un solde d'ouverture (08/10/2026)
    soldes_calcules: bool = False
    solde_ouverture_propose: Decimal | None = None
    solde_ouverture_source: str | None = None
    # Calcul à rebours depuis un solde postérieur au fichier : à vérifier (08/10/2026)
    solde_ouverture_avertissement: str | None = None
    # Saisie du solde d'ouverture permise : premier import du compte seulement (09/10/2026)
    solde_ouverture_modifiable: bool = True
    solde_ouverture_choisi: Decimal | None = None


# --- Lecture du classeur et correspondance (module commun `import_file`) --------------------------


def propose_mapping(columns: list[Column]) -> Mapping:
    """Correspondance détectée : les correspondances exactes d'abord, puis les débuts d'en-tête."""
    return import_file.propose_mapping(columns, STATEMENT_FIELDS)


def _saved_mapping(db: Session, bank_id: int, columns: list[Column]) -> Mapping | None:
    """Modèle mémorisé pour la banque (champ → en-tête), s'il retrouve toutes ses colonnes."""
    saved = import_repository.latest_mapping(db, bank_id, TYPE_IMPORT)
    if saved is None:
        return None
    return import_file.mapping_from_headers(saved.mapping, columns, STATEMENT_FIELDS)


def mapping_errors(mapping: Mapping, width: int) -> list[str]:
    return import_file.mapping_errors(mapping, width, STATEMENT_FIELDS)


# --- Lignes --------------------------------------------------------------------------------------


def _bank_matches(value: object, bank: Bank) -> bool:
    text = normalize_header(value)
    return any(
        name and name in text for name in (normalize_header(bank.code), normalize_header(bank.nom))
    )


@dataclass
class Pointages:
    """Types de pointage actifs : retrouvés par code ou libellé (sans casse ni accents), et la
    mémoire de la société (libellé → pointage le plus fréquent)."""

    by_key: dict[str, int]
    labels: dict[int, str]
    memory: dict[str, int] = field(default_factory=dict)

    def find(self, text: str | None) -> int | None:
        return self.by_key.get(normalize_header(text)) if text else None

    def guess(self, libelle: str | None) -> int | None:
        """Pointage d'une ligne sans valeur dans le fichier (décision du 08/10/2026) : la mémoire
        de la société pour ce libellé, sinon la catégorie nommée dans le libellé, sinon None."""
        remembered = self.memory.get(label_key(libelle))
        if remembered is not None:
            return remembered
        return self.find(guess_pointage(libelle, self.labels.values()))


def _pointages(db: Session, company_id: int) -> Pointages:
    by_key: dict[str, int] = {}
    labels: dict[int, str] = {}
    for item in import_repository.active_pointage_types(db):
        by_key[normalize_header(item.code)] = item.id
        by_key[normalize_header(item.libelle)] = item.id
        labels[item.id] = item.libelle
    counts: dict[str, Counter[int]] = defaultdict(Counter)
    for libelle, pointage_type_id in import_repository.pointages_of_company(db, company_id):
        key = label_key(libelle)
        if key:
            counts[key][pointage_type_id] += 1
    # Le plus fréquent ; à égalité, le plus petit identifiant (résultat stable)
    memory = {
        key: min(counter.items(), key=lambda item: (-item[1], item[0]))[0]
        for key, counter in counts.items()
    }
    return Pointages(by_key, labels, memory)


def _read_line(
    numero: int,
    cells: dict[str, object],
    mapping: Mapping,
    bank: Bank,
    today: date,
    pointages: Pointages,
) -> AnalysedLine:
    line = AnalysedLine(numero=numero, statut="Valide", motifs=[])

    def amount(code: str) -> Decimal | None:
        try:
            return parse_amount(cells.get(code))
        except ValueError as error:
            line.motifs.append(f"{FIELD_LABELS[code]} : {error}")
            return None

    try:
        line.date_operation = parse_date(cells.get("date_operation"))
        if line.date_operation is None:
            line.motifs.append("Date d'opération manquante.")
        elif line.date_operation > today:
            line.motifs.append("Date d'opération dans le futur.")
    except ValueError as error:
        line.motifs.append(f"Date d'opération : {error}")
    try:
        line.date_valeur = parse_date(cells.get("date_valeur"))
    except ValueError as error:
        line.motifs.append(f"Date de valeur : {error}")

    line.libelle = clean_libelle(cells.get("libelle"))
    if line.libelle is None:
        line.motifs.append("Libellé manquant.")

    unreadable = len(line.motifs)
    if mapping.get("montant") is not None:
        signed = amount("montant")
        if signed:
            line.credit = max(signed, Decimal("0.00"))
            line.debit = max(-signed, Decimal("0.00"))
        elif len(line.motifs) == unreadable:  # vide ou nul (un montant illisible est déjà signalé)
            line.motifs.append("Montant manquant ou nul.")
    else:
        # Un débit écrit en négatif dans sa colonne reste un débit
        debit, credit = amount("debit"), amount("credit")
        if len(line.motifs) == unreadable:
            debit = abs(debit) if debit is not None else Decimal("0.00")
            credit = abs(credit) if credit is not None else Decimal("0.00")
            if debit and credit:
                line.motifs.append("Débit et crédit renseignés sur la même ligne.")
            elif not debit and not credit:
                line.motifs.append("Ni débit ni crédit.")
            else:
                line.debit, line.credit = debit, credit
    if line.debit is not None and line.credit is not None:
        line.montant = line.credit - line.debit

    line.solde = amount("solde")
    reference = clean_text(cells.get("reference")) or extract_reference(line.libelle)
    line.reference = reference[:REFERENCE_MAX] if reference else None
    # Pointage : la valeur connue du fichier l'emporte ; sinon la mémoire, puis le libellé
    # (décision métier du 02/10/2026). Une valeur inconnue ne bloque jamais la ligne.
    line.pointage = clean_text(cells.get("pointage"))
    line.pointage_type_id = pointages.find(line.pointage)
    if line.pointage_type_id is None:
        line.pointage_type_id = pointages.guess(line.libelle)
        line.pointage_auto = line.pointage_type_id is not None
    line.pointage_libelle = pointages.labels.get(line.pointage_type_id)
    line.lettrage_escompte = clean_text(cells.get("lettrage_escompte"))
    if line.lettrage_escompte and len(line.lettrage_escompte) > LETTRAGE_MAX:
        line.motifs.append(f"Lettrage / Escompte : {LETTRAGE_MAX} caractères au plus.")
    line.commentaire = clean_text(cells.get("commentaire"))
    banque = cells.get("banque")
    if not is_blank(banque) and not _bank_matches(banque, bank):
        line.motifs.append(
            f"Banque « {clean_text(banque)} » différente de celle du compte ({bank.code})."
        )

    if line.motifs:
        line.statut = "Erreur"
    return line


SENS_INTROUVABLE = (
    "Sens introuvable : le solde ne permet pas de savoir si c'est un débit ou un crédit."
)


def _direction_from_balances(
    lines: list[AnalysedLine], mapping: Mapping, opening: Decimal | None, pointages: Pointages
) -> None:
    """Colonne Montant sans signe (relevé BP « Format_Different ») : le sens vient du Solde.

    Décision du 04/10/2026. Ne s'applique que si le fichier a une colonne Montant et une colonne
    Solde, qu'aucun montant n'est négatif (sinon la colonne est vraiment signée) et que la chaîne
    des soldes prouve au moins un débit (solde précédent − montant = solde). Alors chaque ligne
    prend le sens prouvé par son solde ; une ligne dont le sens n'est pas prouvé passe en erreur,
    jamais au crédit par défaut. Le solde précédent de la 1re ligne est le SOLDE INITIAL du fichier.
    """
    if mapping.get("montant") is None or mapping.get("solde") is None:
        return
    readable = [line for line in lines if line.credit is not None and line.debit is not None]
    if any(line.debit for line in readable):
        return
    dated = [line for line in lines if line.date_operation is not None]
    newest_first = len(dated) > 1 and dated[0].date_operation > dated[-1].date_operation
    ordered = lines[::-1] if newest_first else lines

    proofs: dict[int, str | None] = {}
    previous = opening
    for line in ordered:
        sens = None
        if line.credit and previous is not None and line.solde is not None:
            if previous + line.credit == line.solde:
                sens = "credit"
            elif previous - line.credit == line.solde:
                sens = "debit"
        proofs[id(line)] = sens
        previous = line.solde
    if "debit" not in proofs.values():
        return

    for line in ordered:
        if not line.credit:
            continue  # montant illisible ou manquant : déjà en erreur
        sens = proofs[id(line)]
        if sens == "debit":
            line.debit, line.credit = line.credit, Decimal("0.00")
            line.montant = -line.debit
        elif sens is None:
            line.motifs.append(SENS_INTROUVABLE)
            line.statut = "Erreur"


def _ignored_reason(cells: dict[str, object]) -> str | None:
    """Raison d'ignorer une ligne sans date d'opération (titre, total, solde), sinon None."""
    if not is_blank(cells.get("date_operation")):
        return None
    libelle = clean_libelle(cells.get("libelle")) or ""
    amounts = ("debit", "credit", "montant")
    if all(is_blank(cells.get(code)) for code in amounts):
        return (
            "Ligne de total ou de solde"
            if _SUMMARY_LINE.match(libelle)
            else ("Ligne de titre ou sans montant")
        )
    if _SUMMARY_LINE.match(libelle):
        return "Ligne de total ou de solde"
    return None


def _is_ignored(cells: dict[str, object]) -> bool:
    """Ligne de titre, de total ou de solde, sans date d'opération."""
    return _ignored_reason(cells) is not None


def _line_key(line: AnalysedLine) -> tuple:
    """Valeurs qui identifient une opération : base de son empreinte (`line_hash`)."""
    return (
        line.date_operation,
        line.date_valeur,
        line.libelle,
        line.debit,
        line.credit,
        line.solde,
        line.reference,
    )


def _mark_duplicates(db: Session, account: BankAccount, lines: list[AnalysedLine]) -> None:
    first_seen: dict[tuple, int] = {}
    occurrences: Counter[tuple] = Counter()
    for line in lines:
        if line.statut != "Valide":
            continue
        key = _line_key(line)
        occurrences[key] += 1
        line.hash_ligne = line_hash(account.id, key, occurrences[key])
        if key in first_seen:
            line.statut = "Doublon"
            line.doublon_de = first_seen[key]
            line.motifs.append(f"Ligne identique à la ligne {first_seen[key]} du fichier.")
        else:
            first_seen[key] = line.numero
    # Une ligne déjà importée l'emporte sur « identique dans le fichier » : elle ne peut pas être gardée
    hashes = [line.hash_ligne for line in lines if line.hash_ligne]
    known = import_repository.existing_line_hashes(db, account.id, hashes)
    for line in lines:
        if line.hash_ligne in known:
            line.statut = "Doublon"
            line.doublon_de = None
            line.motifs = ["Déjà importée pour ce compte."]


@dataclass
class Balances:
    solde_ouverture: Decimal | None = None
    solde_cloture: Decimal | None = None
    soldes_coherents: bool | None = None


def _balances(
    lines: list[AnalysedLine], opening: Decimal | None = None, closing: Decimal | None = None
) -> Balances:
    """Soldes d'ouverture et de clôture, et leur cohérence avec les mouvements.

    Les lignes SOLDE INITIAL / SOLDE FINAL du fichier (`opening`, `closing`) l'emportent ; à défaut,
    les soldes sont déduits des lignes quand chacune porte son solde.
    """
    if not lines:
        return Balances(opening, closing, None)
    computed_open = computed_close = None
    if all(line.solde is not None for line in lines):
        # Relevé du plus récent au plus ancien : on le lit dans l'ordre chronologique
        ordered = lines[::-1] if lines[0].date_operation > lines[-1].date_operation else lines
        computed_open = ordered[0].solde - ordered[0].montant
        computed_close = ordered[-1].solde
    ouverture = opening if opening is not None else computed_open
    cloture = closing if closing is not None else computed_close
    if ouverture is None or cloture is None:
        return Balances(ouverture, cloture, None)
    movements = sum((line.montant for line in lines), Decimal("0.00"))
    return Balances(ouverture, cloture, ouverture + movements == cloture)


def _summarise(
    lines: list[AnalysedLine],
    ignored: int,
    opening: Decimal | None = None,
    closing: Decimal | None = None,
) -> Summary:
    summary = Summary(nb_lignes=len(lines), nb_ignorees=ignored)
    valid = [line for line in lines if line.statut == "Valide"]
    summary.nb_valides = len(valid)
    summary.nb_erreurs = sum(1 for line in lines if line.statut == "Erreur")
    summary.nb_doublons = sum(1 for line in lines if line.statut == "Doublon")
    summary.total_debit = sum((line.debit for line in valid), Decimal("0.00"))
    summary.total_credit = sum((line.credit for line in valid), Decimal("0.00"))
    if not valid:
        return summary
    dates = [line.date_operation for line in valid]
    summary.periode_debut, summary.periode_fin = min(dates), max(dates)
    balances = _balances(valid, opening, closing)
    summary.solde_ouverture = balances.solde_ouverture
    summary.solde_cloture = balances.solde_cloture
    summary.solde_ouverture_fichier = opening is not None
    summary.solde_cloture_fichier = closing is not None
    summary.soldes_coherents = balances.soldes_coherents
    return summary


# --- Relevés sans soldes : solde calculé (décision du 08/10/2026) ---------------------------------

OUVERTURE_A_SAISIR = (
    "Indiquez le solde d'ouverture : le fichier n'a pas de soldes et aucun solde connu du compte "
    "ne précède sa première opération."
)


def _chronological(lines: list[AnalysedLine]) -> list[AnalysedLine]:
    """Lignes dans l'ordre chronologique : un relevé du plus récent au plus ancien est retourné."""
    dated = [line for line in lines if line.date_operation is not None]
    if dated and dated[0].date_operation > dated[-1].date_operation:
        return lines[::-1]
    return list(lines)


def running_balances(
    lines: list[AnalysedLine], opening: Decimal, *, apercu: bool = False
) -> Decimal:
    """Solde de chaque ligne = solde précédent − débit + crédit, depuis `opening` ; retourne le
    solde de clôture. Une ligne qui porte le solde de la banque le garde et le calcul repart de lui
    (colonne Solde remplie à moitié, 09/10/2026). `apercu` : le résultat va dans `solde_apercu` (analyse), sinon dans `solde`
    (enregistrement). Une ligne sans montant lisible n'a pas de solde."""
    solde = opening
    for line in _chronological(lines):
        if line.solde is not None and not line.solde_calcule:
            # Solde écrit par la banque : gardé, contrôlé, et le calcul repart de lui (09/10/2026)
            if apercu:
                attendu = None if line.montant is None else solde + line.montant
                line.ecart_solde = (
                    None if attendu is None or attendu == line.solde else line.solde - attendu
                )
            solde = line.solde
            continue
        value = None if line.montant is None else solde + line.montant
        if value is not None:
            solde = value
        if apercu:
            line.solde_apercu = value
        else:
            line.solde, line.solde_calcule = value, True
    return solde


@dataclass
class Ouverture:
    """Solde d'ouverture proposé, d'où il vient, et un avertissement s'il est à vérifier."""

    solde: Decimal | None
    source: str
    avertissement: str | None = None
    # Saisie manuelle permise seulement au premier import du compte (09/10/2026)
    modifiable: bool = True


SOURCE_FICHIER = "Ligne SOLDE INITIAL du fichier"
SOURCE_PREMIERE_LIGNE = "Solde de la banque sur la première opération du fichier"


def _proposed_opening(
    db: Session, account: BankAccount, lines: list[AnalysedLine], file_opening: Decimal | None
) -> Ouverture:
    """Solde d'ouverture, dans cet ordre (décision du 09/10/2026) :

    1. la banque : la ligne SOLDE INITIAL du fichier (verrouillé) ;
    2. le solde de clôture du relevé précédent : la dernière opération importée avant la première
       opération du fichier (verrouillé) ;
    3. le tableau de position bancaire : le dernier solde du jour avant le fichier, sinon un calcul
       à rebours depuis un solde postérieur ; modifiable, c'est un premier import ;
    4. sinon, à saisir (premier import seulement).

    « Premier import » = aucune opération importée avant ce fichier sur ce compte.
    """
    # Les lignes déjà importées pour ce compte ne comptent pas : elles ne seront pas enregistrées
    nouvelles = [
        line
        for line in lines
        if line.date_operation is not None
        and not (line.statut == "Doublon" and line.doublon_de is None)
    ]
    dates = [line.date_operation for line in nouvelles]
    precedent = (
        import_repository.last_operation_before(db, account.id, min(dates)) if dates else None
    )
    source = SOURCE_FICHIER
    if file_opening is None:
        file_opening, source = _bank_opening(nouvelles), SOURCE_PREMIERE_LIGNE
    if file_opening is not None:
        avertissement = None
        if precedent is not None and precedent[1] != file_opening:
            jour, solde = precedent
            avertissement = (
                f"Le solde initial du fichier ({_texte_montant(file_opening)}) ne correspond pas "
                f"au solde de clôture du relevé précédent ({_texte_montant(solde)}, le "
                f"{jour:%d/%m/%Y}) : une période manque peut-être."
            )
        return Ouverture(file_opening, source, avertissement, modifiable=False)
    if precedent is not None:
        jour, solde = precedent
        return Ouverture(
            solde, f"Solde de clôture du relevé précédent, le {jour:%d/%m/%Y}", modifiable=False
        )
    if not dates:
        return Ouverture(None, "À saisir")
    known = import_repository.last_known_balance(db, account.id, min(dates))
    if known is not None:
        jour, solde, _ = known
        return Ouverture(solde, f"Solde du jour enregistré le {jour:%d/%m/%Y} (tableau Banques)")
    return _opening_backwards(db, account, nouvelles, max(dates))


def _bank_opening(lines: list[AnalysedLine]) -> Decimal | None:
    """Colonne Solde remplie à moitié : si la première opération (dans l'ordre chronologique) porte
    le solde de la banque, le solde d'ouverture est ce solde moins son montant."""
    ordered = _chronological(lines)
    if not ordered:
        return None
    first = ordered[0]
    if first.solde is None or first.montant is None:
        return None
    return first.solde - first.montant


def _texte_montant(value: Decimal) -> str:
    """« 1 234 567,89 » : montant lisible dans un message."""
    entier, decimales = f"{abs(value):.2f}".split(".")
    groupes = f"{int(entier):,}".replace(",", " ")
    return f"{'-' if value < 0 else ''}{groupes},{decimales}"


def _opening_backwards(
    db: Session, account: BankAccount, lines: list[AnalysedLine], dernier_jour: date
) -> Ouverture:
    """Solde d'ouverture = solde du tableau Banques du dernier jour du fichier − crédits + débits du
    fichier. Seulement quand ce solde est daté du dernier jour du fichier (décision du 09/10/2026) :
    un solde postérieur supposerait qu'aucune opération n'a eu lieu entre les deux dates, la
    proposition serait souvent fausse ; le solde est alors à saisir (premier import)."""
    later = import_repository.first_balance_from(db, account.id, dernier_jour)
    if later is None or later[0] != dernier_jour:
        return Ouverture(None, "À saisir")
    jour, solde = later
    mouvements = sum((line.montant for line in lines if line.montant is not None), Decimal(0))
    return Ouverture(
        solde - mouvements,
        f"Calculé à rebours depuis le solde du {jour:%d/%m/%Y} (tableau Banques)",
    )


def _no_amount(value: object) -> bool:
    """Cellule de montant vide, à zéro (0, « 0,00 ») ou tiret : ce que les banques écrivent
    dans Débit / Crédit sur une ligne de solde."""
    if is_blank(value) or str(value).strip() in {"-", "–", "—"}:
        return True
    try:
        return parse_amount(value) == 0
    except ValueError:
        return False


def _balance_line(cells: dict[str, object]) -> tuple[str, Decimal | None] | None:
    """Ligne SOLDE INITIAL / SOLDE FINAL (datée ou non), sans débit ni crédit : (sorte, montant).

    Ce n'est pas une opération : son montant donne le solde d'ouverture ou de clôture du fichier.
    Débit et crédit peuvent être vides, à zéro ou un tiret ; un vrai montant en fait une opération.
    """
    kind = balance_line_kind(clean_libelle(cells.get("libelle")))
    if kind is None or not all(
        _no_amount(cells.get(code)) for code in ("debit", "credit", "montant")
    ):
        return None
    try:
        return kind, parse_amount(cells.get("solde"))
    except ValueError:
        return kind, None


# --- Analyse -------------------------------------------------------------------------------------


def analyse_statement(
    db: Session,
    *,
    account_id: int,
    fichier_nom: str,
    content: bytes,
    mapping: Mapping | None = None,
    feuille: str | None = None,
    today: date | None = None,
    solde_ouverture: Decimal | None = None,
) -> StatementAnalysis:
    """Analyse un relevé pour un compte. Ne modifie pas la base.

    Fichier sans soldes : `solde_ouverture` (saisi à l'étape Validation) remplace le solde
    d'ouverture proposé, et les soldes de l'aperçu en sont calculés."""
    account = account_service.get_account(db, account_id)
    if not account.actif:
        raise ConflictError(
            f"Le compte {account.bank.code} {account.devise} est inactif : réactivez-le d'abord."
        )
    import_file.check_file(fichier_nom, content)

    feuilles, feuille, rows = import_file.read_sheet(content, feuille, unite="relevé")
    header_index = import_file.detect_header(rows, STATEMENT_FIELDS)
    data = rows[header_index + 1 :]
    if len(data) > import_file.MAX_ROWS:
        raise ConflictError(
            f"Fichier trop long : {import_file.MAX_ROWS_TEXTE} lignes au plus par relevé."
        )
    columns = import_file.columns_of(rows[header_index], data)

    if mapping is not None:
        source = "Utilisateur"
        mapping = {code: mapping.get(code) for code in FIELD_CODES}
    else:
        saved = _saved_mapping(db, account.bank_id, columns)
        source = "Modèle de la banque" if saved else "Détection"
        mapping = saved or propose_mapping(columns)

    fhash = file_hash(content)
    analysis = StatementAnalysis(
        account=account,
        fichier_nom=fichier_nom,
        fichier_hash=fhash,
        deja_importe=import_repository.confirmed_file(db, account.company_id, TYPE_IMPORT, fhash)
        is not None,
        feuilles=feuilles,
        feuille=feuille,
        ligne_entete=header_index + 1,
        colonnes=columns,
        mapping=mapping,
        mapping_source=source,
        erreurs_mapping=mapping_errors(mapping, len(columns)),
    )
    if analysis.erreurs_mapping:
        return analysis  # pas de lecture des lignes tant que la correspondance est incomplète

    today = today or position_service.business_today()
    pointages = _pointages(db, account.company_id)
    lines, ignored = [], 0
    # Une cellule Solde remplie (même illisible) : le fichier a ses soldes, rien n'est calculé
    for offset, row in enumerate(data):
        if all(is_blank(cell) for cell in row):
            continue
        numero = header_index + 2 + offset
        cells = {
            code: row[index] if index < len(row) else None
            for code, index in mapping.items()
            if index is not None
        }
        balance = _balance_line(cells)
        if balance is not None:
            ignored += 1
            kind, value = balance
            raison = (
                "Ligne SOLDE INITIAL : donne le solde d'ouverture du fichier"
                if kind == "ouverture"
                else "Ligne SOLDE FINAL : donne le solde de clôture du fichier"
            )
            analysis.lignes_ignorees.append(import_file.ignored_line(numero, raison, row))
            if kind == "ouverture" and analysis.solde_initial_fichier is None:
                analysis.solde_initial_fichier = value
            elif kind == "cloture" and value is not None:
                analysis.solde_final_fichier = value
            continue
        raison = _ignored_reason(cells)
        if raison is not None:
            ignored += 1
            analysis.lignes_ignorees.append(import_file.ignored_line(numero, raison, row))
            continue
        lines.append(_read_line(numero, cells, mapping, account.bank, today, pointages))

    _direction_from_balances(lines, mapping, analysis.solde_initial_fichier, pointages)
    _mark_duplicates(db, account, lines)
    analysis.lignes = lines
    # Pas de soldes dans le fichier : ils sont calculés depuis un solde d'ouverture
    # Une case Solde vide sur une ligne lisible (colonne absente ou remplie à moitié) : SIMTIS la
    # calcule (09/10/2026). Une ligne en erreur ne compte pas : elle n'est pas importée telle quelle
    solde_manquant = any(line.solde is None for line in lines if line.statut != "Erreur")
    if lines and solde_manquant:
        analysis.soldes_calcules = True
        ouverture = _proposed_opening(db, account, lines, analysis.solde_initial_fichier)
        proposed = ouverture.solde
        analysis.solde_ouverture_propose = proposed
        analysis.solde_ouverture_source = ouverture.source
        analysis.solde_ouverture_avertissement = ouverture.avertissement
        analysis.solde_ouverture_modifiable = ouverture.modifiable
        if solde_ouverture is not None and not ouverture.modifiable and solde_ouverture != proposed:
            origine = (
                f"de la banque ({ouverture.source[0].lower()}{ouverture.source[1:]})"
                if ouverture.source in (SOURCE_FICHIER, SOURCE_PREMIERE_LIGNE)
                else "du relevé précédent (son solde de clôture)"
            )
            raise ConflictError(
                f"Le solde d'ouverture vient {origine} : il ne se saisit pas. La saisie n'est "
                "possible qu'au premier import du compte."
            )
        opening = solde_ouverture if solde_ouverture is not None else proposed
        analysis.solde_ouverture_choisi = opening
        closing = None
        if opening is not None:
            valid = [line for line in lines if line.statut == "Valide"]
            closing = running_balances(valid, opening, apercu=True) if valid else None
        analysis.resume = _summarise(lines, ignored, opening, closing)
        # Ces soldes ne viennent pas d'une ligne SOLDE INITIAL / SOLDE FINAL du fichier
        analysis.resume.solde_ouverture_fichier = analysis.solde_initial_fichier is not None
        analysis.resume.solde_cloture_fichier = False
        return analysis
    analysis.resume = _summarise(
        lines, ignored, analysis.solde_initial_fichier, analysis.solde_final_fichier
    )
    return analysis


# --- Confirmation (P7.2) ---------------------------------------------------------------------------


@dataclass
class StatementImport:
    batch: ImportBatch
    statement: BankStatement
    nb_importees: int
    nb_erreurs_ecartees: int
    nb_doublons_ecartes: int
    total_debit: Decimal
    total_credit: Decimal
    soldes_coherents: bool | None
    controle: BalanceCheck | None
    # Solde du jour de clôture : « Créé », « Corrigé », « Inchangé », ou None sans colonne Solde
    solde_du_jour: str | None
    modele_enregistre: bool


def _save_mapping(db: Session, analysis: StatementAnalysis) -> bool:
    """Mémorise la correspondance pour la banque (champ → en-tête), réutilisée au prochain import.

    Impossible si une colonne associée n'a pas d'en-tête : le modèle ne pourrait pas la retrouver.
    """
    headers = {
        code: analysis.colonnes[index].entete
        for code, index in analysis.mapping.items()
        if index is not None
    }
    if not all(headers.values()):
        return False
    bank = analysis.account.bank
    saved = import_repository.latest_mapping(db, bank.id, TYPE_IMPORT)
    if saved is None:
        import_repository.add(
            db,
            ColumnMapping(
                type=TYPE_IMPORT, bank_id=bank.id, nom=f"Relevé {bank.code}", mapping=headers
            ),
        )
    elif saved.mapping != headers:
        saved.mapping = headers
    return True


def _closing_balance(
    db: Session,
    account: BankAccount,
    statement: BankStatement,
    balances: Balances,
    fichier_nom: str,
    acteur_id: int,
    ip: str | None,
) -> tuple[BalanceCheck | None, str | None]:
    """Contrôle le solde de clôture contre le solde enregistré du jour, puis l'enregistre.

    Le relevé fait foi : son solde de clôture devient le solde du jour (source « Relevé »). Le
    contrôle garde la trace d'une différence avec la valeur enregistrée avant l'import.
    """
    if balances.solde_cloture is None:
        return None, None
    jour, cloture = statement.periode_fin, balances.solde_cloture
    existing = balance_repository.get(db, account.id, jour)
    recorded = existing.solde if existing else None

    check = None
    if recorded is not None:
        ecart = cloture - recorded
        statut = "Conforme" if ecart == 0 else "Écart"
        commentaire = None
        if balances.soldes_coherents is False:
            statut = "À vérifier"
            commentaire = "Les mouvements du relevé ne retrouvent pas son solde de clôture."
        check = BalanceCheck(
            bank_account_id=account.id,
            bank_statement_id=statement.id,
            date_controle=jour,
            solde_releve=cloture,
            solde_enregistre=recorded,
            ecart=ecart,
            statut=statut,
            commentaire=commentaire,
            user_id=acteur_id,
        )
        import_repository.add(db, check)

    if existing is None:
        balance = BankAccountBalance(
            bank_account_id=account.id,
            date_solde=jour,
            solde=cloture,
            source="Relevé",
            saisi_par_id=acteur_id,
            commentaire=f"Relevé {fichier_nom}"[:500],
        )
        import_repository.add(db, balance)
        action, avant, result = "saisie_solde", None, "Créé"
    elif existing.solde == cloture and existing.source == "Relevé":
        return check, "Inchangé"
    else:
        avant = {"date_solde": jour, "solde": existing.solde, "source": existing.source}
        existing.solde, existing.source, existing.saisi_par_id = cloture, "Relevé", acteur_id
        balance, action, result = existing, "correction_solde", "Corrigé"
    audit_service.log(
        db,
        user_id=acteur_id,
        action=action,
        entite="bank_account_balance",
        entite_id=balance.id,
        avant=avant,
        apres={"date_solde": jour, "solde": cloture, "source": "Relevé"},
        ip=ip,
    )
    return check, result


@dataclass
class Selection:
    """Lignes retenues pour l'enregistrement, et ce qui a été écarté ou corrigé (pour l'audit)."""

    lines: list[AnalysedLine]
    nb_erreurs: int
    nb_doublons: int
    doublons_gardes: list[int] = field(default_factory=list)
    corrections: list[dict] = field(default_factory=list)
    non_importees: list[int] = field(default_factory=list)


def _file_selection(
    analysis: StatementAnalysis, garder_doublons: list[int] | None, ecarter_erreurs: bool
) -> Selection:
    """Fonctionnement sans aperçu modifiable : le fichier est importé tel qu'il est analysé.

    - lignes en erreur : la confirmation est refusée, sauf si l'utilisateur choisit de les écarter ;
    - doublons : écartés ; une ligne identique à une autre du même fichier peut être gardée en
      donnant son numéro dans `garder_doublons` ; une ligne déjà importée ne peut jamais l'être.
    """
    errors = [line for line in analysis.lignes if line.statut == "Erreur"]
    if errors and not ecarter_erreurs:
        plural = "s" if len(errors) > 1 else ""
        raise ConflictError(
            f"{len(errors)} ligne{plural} en erreur : corrigez le fichier, "
            "ou confirmez en les écartant."
        )
    by_number = {line.numero: line for line in analysis.lignes}
    keep = set(garder_doublons or [])
    for numero in sorted(keep):
        line = by_number.get(numero)
        if line is None or line.doublon_de is None:
            raise ConflictError(
                f"La ligne {numero} n'est pas identique à une autre ligne du fichier : "
                "elle ne peut pas être gardée."
            )
    lines = [line for line in analysis.lignes if line.statut == "Valide" or line.numero in keep]
    if not lines:
        raise ConflictError("Aucune ligne à importer dans ce fichier.")
    kept = {line.numero for line in lines}
    return Selection(
        lines=lines,
        nb_erreurs=len(errors),
        nb_doublons=sum(1 for line in analysis.lignes if line.statut == "Doublon") - len(keep),
        doublons_gardes=sorted(keep),
        non_importees=sorted(line.numero for line in analysis.lignes if line.numero not in kept),
    )


# Champs comparés pour décider qu'une ligne a été corrigée dans l'aperçu (tracés dans l'audit)
CORRECTABLE_FIELDS = (
    "date_operation",
    "date_valeur",
    "libelle",
    "reference",
    "debit",
    "credit",
    "solde",
    "pointage_type_id",
    "lettrage_escompte",
    "commentaire",
)
# Une ligne envoyée se lit comme une ligne de fichier aux colonnes Débit / Crédit séparées
_SUBMITTED_MAPPING: Mapping = {"debit": 0, "credit": 1}
_SUBMITTED_CELLS = (
    "date_operation",
    "date_valeur",
    "libelle",
    "reference",
    "debit",
    "credit",
    "solde",
    "lettrage_escompte",
    "commentaire",
)


def _submitted_line(
    data: dict, original: AnalysedLine, bank: Bank, today: date, pointages: Pointages
) -> AnalysedLine:
    """Revérifie une ligne envoyée par l'aperçu avec les règles de l'analyse (`_read_line`)."""
    cells = {code: data.get(code) for code in _SUBMITTED_CELLS}
    line = _read_line(original.numero, cells, _SUBMITTED_MAPPING, bank, today, pointages)
    chosen = data.get("pointage_type_id")
    if chosen is not None:
        if chosen not in pointages.labels:
            line.motifs.append("Pointage inconnu ou inactif.")
            line.statut = "Erreur"
        else:
            line.pointage_type_id, line.pointage_auto = chosen, False
            line.pointage_libelle = pointages.labels[chosen]
    return line


def _corrections(original: AnalysedLine, line: AnalysedLine) -> list[dict]:
    return [
        {
            "numero": line.numero,
            "champ": name,
            "avant": getattr(original, name),
            "apres": getattr(line, name),
        }
        for name in CORRECTABLE_FIELDS
        if getattr(original, name) != getattr(line, name)
    ]


def _submitted_selection(
    db: Session, analysis: StatementAnalysis, lignes: list[dict], today: date
) -> Selection:
    """Lignes envoyées par l'aperçu modifiable (décision métier du 02/10/2026).

    Chaque ligne doit être une ligne d'opération du fichier (pas d'ajout). Elle est revérifiée avec
    les règles de l'analyse ; une seule ligne invalide ou déjà importée refuse tout. Une ligne
    garde l'empreinte de sa version d'origine, pour que la même opération renvoyée plus tard par la
    banque soit reconnue comme déjà importée. Rien n'est écrit ici.
    """
    if not lignes:
        raise ConflictError("Aucune ligne à importer dans ce fichier.")
    account = analysis.account
    pointages = _pointages(db, account.company_id)
    originals = {line.numero: line for line in analysis.lignes}
    lines: list[AnalysedLine] = []
    corrections: list[dict] = []
    problems: list[str] = []
    for data in lignes:
        original = originals.get(data["numero"])
        if original is None:
            raise ConflictError(f"La ligne {data['numero']} n'est pas une opération du fichier.")
        if original.statut == "Doublon" and original.doublon_de is None:
            problems.append(f"Ligne {original.numero} : déjà importée pour ce compte.")
            continue
        line = _submitted_line(data, original, account.bank, today, pointages)
        if original.statut == "Erreur":
            # Une autre banque ne se corrige pas dans l'aperçu : la ligne reste refusée
            line.motifs.extend(m for m in original.motifs if m.startswith("Banque «"))
        if line.motifs:
            problems.append(f"Ligne {line.numero} : {' '.join(line.motifs)}")
            continue
        changes = _corrections(original, line)
        if original.statut == "Erreur":
            # Jamais corrigée en silence : une ligne en erreur dans le fichier doit avoir été
            # corrigée, et l'erreur du fichier est gardée dans l'audit
            if not changes:
                problems.append(f"Ligne {line.numero} : {' '.join(original.motifs)}")
                continue
            changes.append(
                {
                    "numero": line.numero,
                    "champ": "erreurs_du_fichier",
                    "avant": " ".join(original.motifs),
                    "apres": None,
                }
            )
        line.origine = "Corrigée" if changes else "Fichier"
        corrections.extend(changes)
        line.hash_ligne = original.hash_ligne
        lines.append(line)
    if problems:
        raise ConflictError(" ".join(problems))

    # Ligne d'origine en erreur : empreinte de ses valeurs corrigées (spécification §4.2), comme si
    # la banque l'avait donnée lisible. Les lignes lisibles du fichier comptent dans les occurrences,
    # pour qu'une correction identique à l'une d'elles reçoive une empreinte distincte.
    occurrences: Counter[tuple] = Counter(
        _line_key(line) for line in analysis.lignes if line.statut != "Erreur"
    )
    for line in lines:
        if line.hash_ligne is None:
            key = _line_key(line)
            occurrences[key] += 1
            line.hash_ligne = line_hash(account.id, key, occurrences[key])
    known = import_repository.existing_line_hashes(
        db, account.id, [line.hash_ligne for line in lines]
    )
    already = [
        f"Ligne {line.numero} : déjà importée pour ce compte."
        for line in lines
        if line.hash_ligne in known
    ]
    if already:
        raise ConflictError(" ".join(already))

    kept = {line.numero for line in lines}
    return Selection(
        lines=sorted(lines, key=lambda line: line.numero),
        nb_erreurs=sum(
            1 for line in analysis.lignes if line.statut == "Erreur" and line.numero not in kept
        ),
        nb_doublons=sum(
            1 for line in analysis.lignes if line.statut == "Doublon" and line.numero not in kept
        ),
        doublons_gardes=sorted(
            line.numero
            for line in analysis.lignes
            if line.statut == "Doublon" and line.numero in kept
        ),
        corrections=corrections,
        non_importees=sorted(numero for numero in originals if numero not in kept),
    )


def confirm_statement(
    db: Session,
    *,
    account_id: int,
    fichier_nom: str,
    content: bytes,
    mapping: Mapping | None = None,
    feuille: str | None = None,
    garder_doublons: list[int] | None = None,
    ecarter_erreurs: bool = False,
    lignes: list[dict] | None = None,
    acteur_id: int,
    ip: str | None = None,
    today: date | None = None,
    solde_ouverture: Decimal | None = None,
) -> StatementImport:
    """Enregistre un relevé : le fichier est analysé à nouveau, puis ses lignes retenues sont importées.

    Avec `lignes` (aperçu modifiable), ce sont les lignes envoyées, revérifiées, qui sont
    enregistrées ; sinon, le fichier tel qu'il est analysé (`_file_selection`). Tout est enregistré
    dans une seule transaction, avec l'audit.
    """
    analysis = analyse_statement(
        db,
        account_id=account_id,
        fichier_nom=fichier_nom,
        content=content,
        mapping=mapping,
        feuille=feuille,
        today=today,
        solde_ouverture=solde_ouverture,
    )
    account = analysis.account
    if analysis.erreurs_mapping:
        raise ConflictError(
            "Correspondance des colonnes incomplète : " + " ".join(analysis.erreurs_mapping)
        )
    if analysis.deja_importe:
        raise ConflictError("Ce fichier a déjà été importé pour cette société.")

    if lignes is not None:
        today = today or position_service.business_today()
        selection = _submitted_selection(db, analysis, lignes, today)
    else:
        selection = _file_selection(analysis, garder_doublons, ecarter_erreurs)
    lines = selection.lines
    dates = [line.date_operation for line in lines]
    if analysis.soldes_calcules:
        # Le serveur refait le calcul sur les lignes retenues, jamais celui de l'écran
        if analysis.solde_ouverture_choisi is None:
            raise ConflictError(OUVERTURE_A_SAISIR)
        running_balances(lines, analysis.solde_ouverture_choisi)
    balances = _balances(
        lines,
        analysis.solde_ouverture_choisi
        if analysis.soldes_calcules
        else analysis.solde_initial_fichier,
        analysis.solde_final_fichier,
    )
    total_debit = sum((line.debit for line in lines), Decimal("0.00"))
    total_credit = sum((line.credit for line in lines), Decimal("0.00"))

    batch = ImportBatch(
        type=TYPE_IMPORT,
        company_id=account.company_id,
        bank_account_id=account.id,
        fichier_nom=fichier_nom[:255],
        fichier_hash=analysis.fichier_hash,
        statut="Confirmé",
        nb_lignes=len(lines),
        nb_erreurs=selection.nb_erreurs,
        nb_doublons=selection.nb_doublons,
        user_id=acteur_id,
    )
    try:
        import_repository.add(db, batch)
        statement = BankStatement(
            bank_account_id=account.id,
            import_batch_id=batch.id,
            periode_debut=min(dates),
            periode_fin=max(dates),
            solde_ouverture=balances.solde_ouverture,
            solde_cloture=balances.solde_cloture,
        )
        import_repository.add(db, statement)
        # Même ordre que le calcul des soldes : un fichier du plus récent au plus ancien est retourné
        rang = {id(line): numero for numero, line in enumerate(_chronological(lines), start=1)}
        import_repository.add(
            db,
            *(
                BankTransaction(
                    statement_id=statement.id,
                    bank_account_id=account.id,
                    pointage_type_id=line.pointage_type_id,
                    date_operation=line.date_operation,
                    date_valeur=line.date_valeur,
                    libelle=line.libelle,
                    reference=line.reference,
                    debit=line.debit,
                    credit=line.credit,
                    montant=line.montant,
                    solde=line.solde,
                    lettrage_escompte=line.lettrage_escompte,
                    commentaire=line.commentaire,
                    hash_ligne=line.hash_ligne,
                    origine=line.origine,
                    solde_calcule=line.solde_calcule,
                    ordre=rang[id(line)],
                )
                for line in lines
            ),
        )
    except IntegrityError as error:  # le même fichier ou les mêmes lignes importés en parallèle
        db.rollback()
        raise ConflictError(
            "Ce relevé vient d'être importé par ailleurs : relancez l'analyse."
        ) from error

    controle, solde_du_jour = _closing_balance(
        db, account, statement, balances, fichier_nom, acteur_id, ip
    )
    modele = _save_mapping(db, analysis)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="import_releve",
        entite="import_batch",
        entite_id=batch.id,
        apres={
            "fichier_nom": batch.fichier_nom,
            "fichier_hash": batch.fichier_hash,
            "bank_account_id": account.id,
            "bank_statement_id": statement.id,
            "nb_lignes": len(lines),
            "nb_erreurs_ecartees": selection.nb_erreurs,
            "nb_doublons_ecartes": selection.nb_doublons,
            "lignes_doublons_gardees": selection.doublons_gardes,
            "lignes_corrigees": selection.corrections,
            "lignes_fichier_non_importees": selection.non_importees,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "periode_debut": statement.periode_debut,
            "periode_fin": statement.periode_fin,
            "solde_ouverture": statement.solde_ouverture,
            "solde_cloture": statement.solde_cloture,
            "controle_solde": controle.statut if controle else None,
            "modele_colonnes_enregistre": modele,
        },
        ip=ip,
    )
    db.commit()
    return StatementImport(
        batch=batch,
        statement=statement,
        nb_importees=len(lines),
        nb_erreurs_ecartees=selection.nb_erreurs,
        nb_doublons_ecartes=selection.nb_doublons,
        total_debit=total_debit,
        total_credit=total_credit,
        soldes_coherents=balances.soldes_coherents,
        controle=controle,
        solde_du_jour=solde_du_jour,
        modele_enregistre=modele,
    )


# --- Consultation (P7.3) ---------------------------------------------------------------------------


@dataclass
class StatementRow:
    statement: BankStatement
    batch: ImportBatch
    account: BankAccount
    importe_par: str | None
    controle: BalanceCheck | None


def list_statements(
    db: Session, company_id: int, bank_account_id: int | None = None
) -> list[StatementRow]:
    """Relevés importés d'UNE société (jamais ceux de l'autre), du plus récent au plus ancien."""
    if account_repository.get_company(db, company_id) is None:
        raise NotFoundError("Société introuvable.")
    rows = import_repository.list_statements(db, company_id, bank_account_id)
    checks = import_repository.balance_checks(db, [row[0].id for row in rows])
    return [
        StatementRow(statement, batch, account, importe_par, checks.get(statement.id))
        for statement, batch, account, importe_par in rows
    ]


BUSINESS_FIELDS = ("pointage_type_id", "lettrage_escompte", "commentaire")


def update_transaction(
    db: Session,
    transaction_id: int,
    *,
    pointage_type_id: int | None,
    lettrage_escompte: str | None,
    commentaire: str | None,
    acteur_id: int,
    ip: str | None = None,
) -> tuple[BankTransaction, str | None]:
    """Modifie les champs métier d'une opération importée (décision métier du 02/10/2026).

    Dates, libellé et montants restent ceux de la banque. Seuls les champs changés sont tracés ;
    rien n'est écrit si rien ne change. Retourne l'opération et le libellé de son pointage.
    """
    transaction = import_repository.get_transaction(db, transaction_id)
    if transaction is None:
        raise NotFoundError("Opération introuvable.")
    pointage = None
    if pointage_type_id is not None:
        pointage = import_repository.get_pointage_type(db, pointage_type_id)
        # Un type désactivé depuis reste accepté s'il ne change pas : on peut modifier le reste
        unchanged = pointage_type_id == transaction.pointage_type_id
        if pointage is None or (not pointage.actif and not unchanged):
            raise ConflictError("Pointage inconnu ou inactif.")
    new_values = {
        "pointage_type_id": pointage_type_id,
        "lettrage_escompte": clean_text(lettrage_escompte),
        "commentaire": clean_text(commentaire),
    }
    changed = [name for name in BUSINESS_FIELDS if getattr(transaction, name) != new_values[name]]
    if changed:
        avant = {name: getattr(transaction, name) for name in changed}
        for name in changed:
            setattr(transaction, name, new_values[name])
        audit_service.log(
            db,
            user_id=acteur_id,
            action="modification_operation",
            entite="bank_transaction",
            entite_id=transaction.id,
            avant=avant,
            apres={name: new_values[name] for name in changed},
            ip=ip,
        )
        db.commit()
    return transaction, pointage.libelle if pointage else None


def list_pointage_types(db: Session) -> list[PointageType]:
    """Types de pointage actifs, par ordre alphabétique sans casse ni accents (liste de choix de
    l'aperçu et de la modification)."""
    return sorted(
        import_repository.active_pointage_types(db),
        key=lambda item: (label_key(item.libelle), item.libelle),
    )


def statement_transactions(
    db: Session, statement_id: int
) -> tuple[BankStatement, list[tuple[BankTransaction, str | None]]]:
    statement = import_repository.get_statement(db, statement_id)
    if statement is None:
        raise NotFoundError("Relevé introuvable.")
    return statement, import_repository.statement_transactions(db, statement_id)


# --- Export au format standard ---------------------------------------------------------------------

# Les 11 champs du relevé standard (CDC §4), dans leur ordre : tout relevé exporté a cette forme
STANDARD_HEADERS = (
    "Société",
    "Pointage",
    "Banque",
    "Date d'opération",
    "Date de valeur",
    "Libellé",
    "Débit",
    "Crédit",
    "Solde",
    "Lettrage / Escompte",
    "Commentaire",
)
_DATE_FORMAT = "DD/MM/YYYY"
_AMOUNT_FORMAT = "#,##0.00"
_WIDTHS = (16, 18, 10, 16, 16, 48, 16, 16, 18, 22, 32)


def export_filename(statement: BankStatement) -> str:
    """« releve_CIH_MAD_2026-09-24_2026-09-26.xlsx »."""
    account = statement.bank_account
    return (
        f"releve_{account.bank.code}_{account.devise}_"
        f"{statement.periode_debut}_{statement.periode_fin}.xlsx"
    )


def export_statement(db: Session, statement_id: int) -> tuple[str, bytes]:
    """Un fichier importé, au format standard, en classeur Excel."""
    statement, rows = statement_transactions(db, statement_id)
    return export_filename(statement), _standard_workbook(statement.bank_account, rows)


def _standard_workbook(
    account: BankAccount, rows: list[tuple[BankTransaction, str | None]]
) -> bytes:
    """Relevé au format standard, en classeur Excel : une feuille, les 11 colonnes.

    Dates et montants sont de vraies valeurs Excel (pas du texte) ; un débit ou un crédit nul est
    une cellule vide, comme sur un relevé bancaire. Un pointage inconnu reste vide.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Relevé standard"
    sheet.append(STANDARD_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for transaction, pointage in rows:
        sheet.append(
            [
                account.company.nom,
                pointage,
                account.bank.code,
                transaction.date_operation,
                transaction.date_valeur,
                transaction.libelle,
                transaction.debit or None,
                transaction.credit or None,
                transaction.solde,
                transaction.lettrage_escompte,
                transaction.commentaire,
            ]
        )
    for row in sheet.iter_rows(min_row=2):
        for cell in row[3:5]:
            cell.number_format = _DATE_FORMAT
        for cell in row[6:9]:
            cell.number_format = _AMOUNT_FORMAT
    for index, width in enumerate(_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# --- Relevé continu d'un compte ----------------------------------------------------------------------


@dataclass
class AccountStatement:
    """Toutes les opérations importées d'un compte, quel que soit le fichier : un seul relevé
    qui s'allonge à chaque import (décision métier du 02/10/2026)."""

    account: BankAccount
    rows: list[tuple[BankTransaction, str | None]]
    periode_debut: date | None
    periode_fin: date | None
    total_debit: Decimal
    total_credit: Decimal
    solde_ouverture: Decimal | None
    solde_cloture: Decimal | None


def account_statement(
    db: Session, account_id: int, date_from: date | None = None, date_to: date | None = None
) -> AccountStatement:
    """Relevé continu d'un compte, sur toute son histoire ou sur une période."""
    account = account_service.get_account(db, account_id)  # 404 si le compte n'existe pas
    if date_from and date_to and date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    rows = import_repository.account_transactions(db, account.id, date_from, date_to)
    transactions = [transaction for transaction, _ in rows]
    first = transactions[0] if transactions else None
    last = transactions[-1] if transactions else None
    return AccountStatement(
        account=account,
        rows=rows,
        periode_debut=first.date_operation if first else None,
        periode_fin=last.date_operation if last else None,
        total_debit=sum((t.debit for t in transactions), Decimal("0.00")),
        total_credit=sum((t.credit for t in transactions), Decimal("0.00")),
        # Solde avant la première opération, et après la dernière, quand le relevé les donne
        solde_ouverture=(first.solde - first.montant)
        if first and first.solde is not None
        else None,
        solde_cloture=last.solde if last else None,
    )


def export_account_statement(
    db: Session, account_id: int, date_from: date | None = None, date_to: date | None = None
) -> tuple[str, bytes]:
    """Relevé continu du compte au format standard : « releve_CIH_MAD_<début>_<fin>.xlsx »."""
    result = account_statement(db, account_id, date_from, date_to)
    if not result.rows:
        raise ConflictError("Aucune opération à exporter sur cette période.")
    account = result.account
    filename = (
        f"releve_{account.bank.code}_{account.devise}_"
        f"{result.periode_debut}_{result.periode_fin}.xlsx"
    )
    return filename, _standard_workbook(account, result.rows)


# --- Relevé déjà importé sans soldes : recalcul (08/10/2026) ---------------------------------------


@dataclass
class Recalcul:
    statement: BankStatement
    nb_operations: int
    solde_ouverture: Decimal
    solde_cloture: Decimal
    solde_du_jour: str | None


def recompute_statement_balances(
    db: Session,
    statement_id: int,
    solde_ouverture: Decimal,
    *,
    acteur_id: int | None = None,
    ip: str | None = None,
) -> Recalcul:
    """Calcule les soldes d'un relevé importé sans soldes (solde précédent − débit + crédit, par
    date puis ordre d'import), met à jour ses soldes d'ouverture et de clôture et le solde du jour
    de clôture, avec audit. Refusé si le relevé a des soldes lus dans le fichier."""
    statement = import_repository.get_statement(db, statement_id)
    if statement is None:
        raise NotFoundError("Relevé introuvable.")
    operations = import_repository.statement_transactions_in_order(db, statement.id)
    if not operations:
        raise ConflictError("Ce relevé n'a aucune opération.")
    if any(op.solde is not None and not op.solde_calcule for op in operations):
        raise ConflictError("Ce relevé a déjà ses soldes, lus dans le fichier : rien à calculer.")
    avant = {
        "solde_ouverture": statement.solde_ouverture,
        "solde_cloture": statement.solde_cloture,
    }
    solde = solde_ouverture
    for operation in operations:
        solde = solde + operation.montant
        operation.solde, operation.solde_calcule = solde, True
    statement.solde_ouverture, statement.solde_cloture = solde_ouverture, solde
    # Période du relevé (solde du jour de clôture), déduite des opérations si elle manque
    statement.periode_debut = statement.periode_debut or operations[0].date_operation
    statement.periode_fin = statement.periode_fin or operations[-1].date_operation
    db.flush()
    batch = db.get(ImportBatch, statement.import_batch_id) if statement.import_batch_id else None
    _, solde_du_jour = _closing_balance(
        db,
        statement.bank_account,
        statement,
        Balances(solde_ouverture, solde, True),
        batch.fichier_nom if batch else f"n° {statement.id}",
        acteur_id,
        ip,
    )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="recalcul_soldes",
        entite="bank_statement",
        entite_id=statement.id,
        avant=avant,
        apres={
            "solde_ouverture": solde_ouverture,
            "solde_cloture": solde,
            "operations": len(operations),
        },
        ip=ip,
    )
    db.commit()
    return Recalcul(statement, len(operations), solde_ouverture, solde, solde_du_jour)
