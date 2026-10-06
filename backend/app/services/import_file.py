"""Lecture d'un classeur d'import, commune aux relevés bancaires et aux exports comptables.

Fichiers Excel `.xlsx` seulement (décision §3.3), 5 Mo et 5 000 lignes au plus. La ligne d'en-tête
est celle qui reconnaît le plus de champs parmi les 30 premières ; la correspondance colonnes /
champs se propose par synonymes d'en-têtes, ou se reprend d'un modèle mémorisé (par en-tête).
"""

import zipfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from app.services.errors import ConflictError
from app.services.normalization_service import clean_text, is_blank, normalize_header

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
HEADER_SCAN_ROWS = 30
SAMPLES = 3

Mapping = dict[str, int | None]


@dataclass(frozen=True)
class ImportField:
    code: str
    libelle: str
    obligatoire: bool
    # En-têtes reconnus, déjà normalisés (`normalize_header`)
    synonymes: tuple[str, ...]


@dataclass
class Column:
    index: int
    lettre: str
    entete: str
    exemples: list[str]


def check_file(fichier_nom: str, content: bytes) -> None:
    if not fichier_nom.lower().endswith(".xlsx"):
        raise ConflictError("Seuls les fichiers Excel .xlsx sont acceptés.")
    if not content:
        raise ConflictError("Le fichier est vide.")
    if len(content) > MAX_FILE_BYTES:
        raise ConflictError("Fichier trop volumineux : 5 Mo au plus.")


def read_sheet(
    content: bytes, feuille: str | None, unite: str = "fichier"
) -> tuple[list[str], str, list[tuple]]:
    """Feuilles du classeur, feuille lue et ses lignes (sans les lignes vides de la fin).
    `unite` nomme ce qu'est le fichier dans le message de taille (« relevé », « fichier »)."""
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
                raise ConflictError(f"Fichier trop long : {MAX_ROWS} lignes au plus par {unite}.")
    finally:
        workbook.close()
    while rows and all(is_blank(cell) for cell in rows[-1]):
        rows.pop()
    if not rows:
        raise ConflictError(f"La feuille « {name} » est vide.")
    return names, name, rows


def field_for_header(header: str, fields: Sequence[ImportField]) -> tuple[str | None, int]:
    """Champ reconnu pour un en-tête, et la force de la correspondance (2 exacte, 1 début, 0 aucune)."""
    if not header:
        return None, 0
    for item in fields:
        if header in item.synonymes:
            return item.code, 2
    best, best_length = None, 0
    for item in fields:
        for synonym in item.synonymes:
            if header.startswith(synonym + " ") and len(synonym) > best_length:
                best, best_length = item.code, len(synonym)
    return best, 1 if best else 0


def detect_header(rows: list[tuple], fields: Sequence[ImportField]) -> int:
    """Index de la ligne d'en-tête : celle qui reconnaît le plus de champs, parmi les premières."""
    best_index, best_score = None, 0
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        score = sum(1 for cell in row if field_for_header(normalize_header(cell), fields)[1])
        if score > best_score:
            best_index, best_score = index, score
    if best_index is not None and best_score >= 2:
        return best_index
    return next(i for i, row in enumerate(rows) if not all(is_blank(cell) for cell in row))


def _display(value: object) -> str:
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return clean_text(value) or ""


def columns_of(header: tuple, data: list[tuple]) -> list[Column]:
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


def propose_mapping(columns: list[Column], fields: Sequence[ImportField]) -> Mapping:
    """Correspondance détectée : les correspondances exactes d'abord, puis les débuts d'en-tête."""
    mapping: Mapping = dict.fromkeys(item.code for item in fields)
    for strength in (2, 1):
        for column in columns:
            if column.index in mapping.values():
                continue
            code, found = field_for_header(normalize_header(column.entete), fields)
            if code and found == strength and mapping[code] is None:
                mapping[code] = column.index
    return mapping


def mapping_from_headers(
    saved: dict[str, str | None], columns: list[Column], fields: Sequence[ImportField]
) -> Mapping | None:
    """Modèle mémorisé (champ → en-tête), s'il retrouve toutes ses colonnes dans le fichier."""
    by_header = {
        normalize_header(column.entete): column.index for column in columns if column.entete
    }
    mapping: Mapping = dict.fromkeys(item.code for item in fields)
    for code, header in saved.items():
        if code not in mapping or header is None:
            continue
        index = by_header.get(normalize_header(header))
        if index is None:
            return None
        mapping[code] = index
    return mapping


def mapping_errors(
    mapping: Mapping,
    width: int,
    fields: Sequence[ImportField],
    *,
    amount_codes: tuple[str, str, str] = ("debit", "credit", "montant"),
) -> list[str]:
    labels = {item.code: item.libelle for item in fields}
    errors = []
    for code, index in mapping.items():
        if index is not None and not 0 <= index < width:
            errors.append(f"{labels[code]} : colonne inexistante dans le fichier.")
    used = Counter(index for index in mapping.values() if index is not None)
    for index, count in sorted(used.items()):
        if count > 1 and 0 <= index < width:
            errors.append(
                f"La colonne {get_column_letter(index + 1)} est associée à plusieurs champs."
            )
    for item in fields:
        if item.obligatoire and mapping.get(item.code) is None:
            errors.append(f"Colonne obligatoire non associée : {item.libelle}.")
    debit, credit, montant = amount_codes
    has_debit_credit = mapping.get(debit) is not None or mapping.get(credit) is not None
    if mapping.get(montant) is not None and has_debit_credit:
        errors.append("Choisissez Débit et Crédit, ou Montant signé, pas les deux.")
    elif mapping.get(montant) is None and not has_debit_credit:
        errors.append("Associez au moins une colonne de montant : Débit, Crédit ou Montant signé.")
    return errors


def headers_of(mapping: Mapping, columns: list[Column]) -> dict[str, str] | None:
    """En-têtes à mémoriser (champ → en-tête) ; `None` si une colonne associée n'a pas d'en-tête."""
    headers = {}
    for code, index in mapping.items():
        if index is None:
            continue
        if not columns[index].entete:
            return None
        headers[code] = columns[index].entete
    return headers
