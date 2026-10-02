"""Import des relevés bancaires, en deux temps : analyse et aperçu (P7.1), puis confirmation (P7.2).

Déroulé (architecture technique §5) : lecture du classeur → détection de la ligne d'en-tête et des
colonnes → correspondance colonnes / champs standard (proposée, ou choisie par l'utilisateur) →
contrôle et normalisation de chaque ligne → aperçu : lignes valides, en erreur, en double.

Règles :
- fichiers Excel `.xlsx` uniquement (décision §3.3), 5 Mo et 5 000 lignes au plus ;
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
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException
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
)
from app.repositories import account_repository, balance_repository, import_repository
from app.services import account_service, audit_service, position_service
from app.services.errors import ConflictError, NotFoundError
from app.services.normalization_service import (
    clean_libelle,
    clean_text,
    extract_reference,
    file_hash,
    is_blank,
    line_hash,
    normalize_header,
    parse_amount,
    parse_date,
)

TYPE_IMPORT = "Banque"
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
HEADER_SCAN_ROWS = 30
SAMPLES = 3
LETTRAGE_MAX = 120
REFERENCE_MAX = 60
# Lignes sans date à ignorer : totaux et soldes de début ou de fin de relevé
_SUMMARY_LINE = re.compile(r"^(TOTAL|SOLDE|ANCIEN SOLDE|NOUVEAU SOLDE|REPORT)\b")


@dataclass(frozen=True)
class ImportField:
    code: str
    libelle: str
    obligatoire: bool
    # En-têtes reconnus, déjà normalisés (`normalize_header`)
    synonymes: tuple[str, ...]


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

Mapping = dict[str, int | None]


@dataclass
class Column:
    index: int
    lettre: str
    entete: str
    exemples: list[str]


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
    pointage: str | None = None
    pointage_type_id: int | None = None
    lettrage_escompte: str | None = None
    commentaire: str | None = None
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
    # Solde d'ouverture + mouvements = solde de clôture ? None sans colonne Solde
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


# --- Lecture du classeur ---------------------------------------------------------------------------


def _read_sheet(content: bytes, feuille: str | None) -> tuple[list[str], str, list[tuple]]:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as error:
        raise ConflictError(
            "Fichier illisible : ce n'est pas un classeur Excel .xlsx valide."
        ) from error
    try:
        names = list(workbook.sheetnames)
        name = feuille or names[0]
        if name not in names:
            raise ConflictError(f"Feuille introuvable dans le fichier : « {name} ».")
        rows: list[tuple] = []
        for row in workbook[name].iter_rows(values_only=True):
            rows.append(tuple(row))
            if len(rows) > MAX_ROWS + HEADER_SCAN_ROWS:
                raise ConflictError(f"Fichier trop long : {MAX_ROWS} lignes au plus par relevé.")
    finally:
        workbook.close()
    while rows and all(is_blank(cell) for cell in rows[-1]):
        rows.pop()
    if not rows:
        raise ConflictError(f"La feuille « {name} » est vide.")
    return names, name, rows


def _field_for_header(header: str) -> tuple[str | None, int]:
    """Champ reconnu pour un en-tête, et la force de la correspondance (2 exacte, 1 début, 0 aucune)."""
    if not header:
        return None, 0
    for item in STATEMENT_FIELDS:
        if header in item.synonymes:
            return item.code, 2
    best, best_length = None, 0
    for item in STATEMENT_FIELDS:
        for synonym in item.synonymes:
            if header.startswith(synonym + " ") and len(synonym) > best_length:
                best, best_length = item.code, len(synonym)
    return best, 1 if best else 0


def _detect_header(rows: list[tuple]) -> int:
    """Index de la ligne d'en-tête : celle qui reconnaît le plus de champs, parmi les premières."""
    best_index, best_score = None, 0
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        score = sum(1 for cell in row if _field_for_header(normalize_header(cell))[1])
        if score > best_score:
            best_index, best_score = index, score
    if best_index is not None and best_score >= 2:
        return best_index
    return next(i for i, row in enumerate(rows) if not all(is_blank(cell) for cell in row))


def _display(value: object) -> str:
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return clean_text(value) or ""


def _columns(header: tuple, data: list[tuple]) -> list[Column]:
    width = max([len(header), *(len(row) for row in data)])
    columns = []
    for index in range(width):
        values = [row[index] for row in data if index < len(row) and not is_blank(row[index])]
        title = clean_text(header[index]) if index < len(header) else None
        columns.append(
            Column(
                index=index,
                lettre=get_column_letter(index + 1),
                entete=title or "",
                exemples=[_display(value) for value in values[:SAMPLES]],
            )
        )
    return columns


# --- Correspondance colonnes / champs --------------------------------------------------------------


def propose_mapping(columns: list[Column]) -> Mapping:
    """Correspondance détectée : les correspondances exactes d'abord, puis les débuts d'en-tête."""
    mapping: Mapping = dict.fromkeys(FIELD_CODES)
    for strength in (2, 1):
        for column in columns:
            if column.index in mapping.values():
                continue
            code, found = _field_for_header(normalize_header(column.entete))
            if code and found == strength and mapping[code] is None:
                mapping[code] = column.index
    return mapping


def _saved_mapping(db: Session, bank_id: int, columns: list[Column]) -> Mapping | None:
    """Modèle mémorisé pour la banque (champ → en-tête), s'il retrouve toutes ses colonnes."""
    saved = import_repository.latest_mapping(db, bank_id, TYPE_IMPORT)
    if saved is None:
        return None
    by_header = {
        normalize_header(column.entete): column.index for column in columns if column.entete
    }
    mapping: Mapping = dict.fromkeys(FIELD_CODES)
    for code, header in saved.mapping.items():
        if code not in mapping or header is None:
            continue
        index = by_header.get(normalize_header(header))
        if index is None:
            return None
        mapping[code] = index
    return mapping


def mapping_errors(mapping: Mapping, width: int) -> list[str]:
    errors = []
    for code, index in mapping.items():
        if index is not None and not 0 <= index < width:
            errors.append(f"{FIELD_LABELS[code]} : colonne inexistante dans le fichier.")
    used = Counter(index for index in mapping.values() if index is not None)
    for index, count in sorted(used.items()):
        if count > 1 and 0 <= index < width:
            errors.append(
                f"La colonne {get_column_letter(index + 1)} est associée à plusieurs champs."
            )
    for item in STATEMENT_FIELDS:
        if item.obligatoire and mapping.get(item.code) is None:
            errors.append(f"Colonne obligatoire non associée : {item.libelle}.")
    has_debit_credit = mapping.get("debit") is not None or mapping.get("credit") is not None
    if mapping.get("montant") is not None and has_debit_credit:
        errors.append("Choisissez Débit et Crédit, ou Montant signé, pas les deux.")
    elif mapping.get("montant") is None and not has_debit_credit:
        errors.append("Associez au moins une colonne de montant : Débit, Crédit ou Montant signé.")
    return errors


# --- Lignes --------------------------------------------------------------------------------------


def _bank_matches(value: object, bank: Bank) -> bool:
    text = normalize_header(value)
    return any(
        name and name in text for name in (normalize_header(bank.code), normalize_header(bank.nom))
    )


def _pointage_index(db: Session) -> dict[str, int]:
    """Types de pointage actifs, retrouvés par leur code ou leur libellé (sans casse ni accents)."""
    index: dict[str, int] = {}
    for item in import_repository.active_pointage_types(db):
        index[normalize_header(item.code)] = item.id
        index[normalize_header(item.libelle)] = item.id
    return index


def _read_line(
    numero: int,
    cells: dict[str, object],
    mapping: Mapping,
    bank: Bank,
    today: date,
    pointages: dict[str, int],
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
    line.pointage = clean_text(cells.get("pointage"))
    if line.pointage:
        # Valeur inconnue : le pointage reste vide, la ligne n'est pas bloquée (décision métier)
        line.pointage_type_id = pointages.get(normalize_header(line.pointage))
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


def _is_ignored(cells: dict[str, object]) -> bool:
    """Ligne de titre, de total ou de solde, sans date d'opération."""
    if not is_blank(cells.get("date_operation")):
        return False
    amounts = ("debit", "credit", "montant")
    if all(is_blank(cells.get(code)) for code in amounts):
        return True
    libelle = clean_libelle(cells.get("libelle")) or ""
    return bool(_SUMMARY_LINE.match(libelle))


def _mark_duplicates(db: Session, account: BankAccount, lines: list[AnalysedLine]) -> None:
    first_seen: dict[tuple, int] = {}
    occurrences: Counter[tuple] = Counter()
    for line in lines:
        if line.statut != "Valide":
            continue
        key = (
            line.date_operation,
            line.date_valeur,
            line.libelle,
            line.debit,
            line.credit,
            line.solde,
            line.reference,
        )
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


def _balances(lines: list[AnalysedLine]) -> Balances:
    """Soldes d'ouverture et de clôture, quand chaque ligne porte son solde."""
    if not lines or any(line.solde is None for line in lines):
        return Balances()
    # Relevé du plus récent au plus ancien : on le lit dans l'ordre chronologique
    ordered = lines[::-1] if lines[0].date_operation > lines[-1].date_operation else lines
    ouverture = ordered[0].solde - ordered[0].montant
    cloture = ordered[-1].solde
    movements = sum((line.montant for line in lines), Decimal("0.00"))
    return Balances(ouverture, cloture, ouverture + movements == cloture)


def _summarise(lines: list[AnalysedLine], ignored: int) -> Summary:
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
    balances = _balances(valid)
    summary.solde_ouverture = balances.solde_ouverture
    summary.solde_cloture = balances.solde_cloture
    summary.soldes_coherents = balances.soldes_coherents
    return summary


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
) -> StatementAnalysis:
    """Analyse un relevé pour un compte. Ne modifie pas la base."""
    account = account_service.get_account(db, account_id)
    if not account.actif:
        raise ConflictError(
            f"Le compte {account.bank.code} {account.devise} est inactif : réactivez-le d'abord."
        )
    if not fichier_nom.lower().endswith(".xlsx"):
        raise ConflictError("Seuls les fichiers Excel .xlsx sont acceptés.")
    if not content:
        raise ConflictError("Le fichier est vide.")
    if len(content) > MAX_FILE_BYTES:
        raise ConflictError("Fichier trop volumineux : 5 Mo au plus.")

    feuilles, feuille, rows = _read_sheet(content, feuille)
    header_index = _detect_header(rows)
    data = rows[header_index + 1 :]
    if len(data) > MAX_ROWS:
        raise ConflictError(f"Fichier trop long : {MAX_ROWS} lignes au plus par relevé.")
    columns = _columns(rows[header_index], data)

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
    pointages = _pointage_index(db)
    lines, ignored = [], 0
    for offset, row in enumerate(data):
        if all(is_blank(cell) for cell in row):
            continue
        cells = {
            code: row[index] if index < len(row) else None
            for code, index in mapping.items()
            if index is not None
        }
        if _is_ignored(cells):
            ignored += 1
            continue
        numero = header_index + 2 + offset
        lines.append(_read_line(numero, cells, mapping, account.bank, today, pointages))

    _mark_duplicates(db, account, lines)
    analysis.lignes = lines
    analysis.resume = _summarise(lines, ignored)
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
    acteur_id: int,
    ip: str | None = None,
    today: date | None = None,
) -> StatementImport:
    """Enregistre un relevé : le fichier est analysé à nouveau, puis ses lignes retenues sont importées.

    - lignes en erreur : la confirmation est refusée, sauf si l'utilisateur choisit de les écarter ;
    - doublons : écartés ; une ligne identique à une autre du même fichier peut être gardée en
      donnant son numéro dans `garder_doublons` ; une ligne déjà importée ne peut jamais l'être ;
    - tout est enregistré dans une seule transaction, avec l'audit.
    """
    analysis = analyse_statement(
        db,
        account_id=account_id,
        fichier_nom=fichier_nom,
        content=content,
        mapping=mapping,
        feuille=feuille,
        today=today,
    )
    account = analysis.account
    if analysis.erreurs_mapping:
        raise ConflictError(
            "Correspondance des colonnes incomplète : " + " ".join(analysis.erreurs_mapping)
        )
    if analysis.deja_importe:
        raise ConflictError("Ce fichier a déjà été importé pour cette société.")

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
    dates = [line.date_operation for line in lines]
    balances = _balances(lines)
    total_debit = sum((line.debit for line in lines), Decimal("0.00"))
    total_credit = sum((line.credit for line in lines), Decimal("0.00"))
    skipped_duplicates = sum(1 for line in analysis.lignes if line.statut == "Doublon") - len(keep)

    batch = ImportBatch(
        type=TYPE_IMPORT,
        company_id=account.company_id,
        bank_account_id=account.id,
        fichier_nom=fichier_nom[:255],
        fichier_hash=analysis.fichier_hash,
        statut="Confirmé",
        nb_lignes=len(lines),
        nb_erreurs=len(errors),
        nb_doublons=skipped_duplicates,
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
            "nb_erreurs_ecartees": len(errors),
            "nb_doublons_ecartes": skipped_duplicates,
            "lignes_doublons_gardees": sorted(keep),
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
        nb_erreurs_ecartees=len(errors),
        nb_doublons_ecartes=skipped_duplicates,
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
