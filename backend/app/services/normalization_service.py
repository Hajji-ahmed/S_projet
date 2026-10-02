"""Normalisation des valeurs lues dans un fichier importé (architecture technique §7).

Fonctions pures, sans base de données : réutilisées par l'import des relevés (P7) et, plus tard, par
celui des écritures comptables (P10). Chaque fonction de lecture lève `ValueError` avec un message en
français destiné à l'utilisateur quand la valeur n'est pas lisible.
"""

import hashlib
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")
# Plus grand montant accepté par une colonne NUMERIC(18,2)
MAX_AMOUNT = Decimal("9999999999999999.99")
# Origine des numéros de série des dates Excel (système 1900, bug du 29/02/1900 compris)
EXCEL_EPOCH = date(1899, 12, 30)
REFERENCE_MAX = 60

_DATE_PATTERNS = (
    (re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$"), "jma"),
    (re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2})$"), "jma2"),
    (re.compile(r"^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})$"), "amj"),
)
# Symboles et codes de devise tolérés autour d'un montant
_CURRENCY = re.compile(r"(?i)\b(?:DH|DHS|MAD|EUR|USD)\b|€|\$")
_SPACES = re.compile(r"[\s  ]+")
_REFERENCE_PATTERNS = (
    re.compile(r"\b(?:CHQ|CHEQUE|CHÈQUE)\s*(?:N[°O]?\s*)?[:.]?\s*(\d{4,})"),
    re.compile(r"\b(?:REF|REFERENCE|RÉFÉRENCE)\s*[:.]?\s*([A-Z0-9][A-Z0-9/\-]{2,})"),
    re.compile(r"\bN[°O]\s*[:.]?\s*([A-Z0-9][A-Z0-9/\-]{2,})"),
    re.compile(r"\b(FACT(?:URE)?[-\s]?[A-Z0-9][A-Z0-9/\-]*\d)"),
)


def normalize_header(text: object) -> str:
    """« Date d'opération » → « date d operation » : minuscules, sans accents ni ponctuation."""
    if text is None:
        return ""
    raw = unicodedata.normalize("NFKD", str(text))
    raw = "".join(char for char in raw if not unicodedata.combining(char)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", raw).split())


def is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def parse_date(value: object) -> date | None:
    """Date d'une cellule : date Excel, texte jj/mm/aaaa, jj/mm/aa, aaaa-mm-jj, ou numéro de série."""
    if is_blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        if 1 <= value < 2958466:  # numéro de série Excel (jusqu'au 31/12/9999)
            return EXCEL_EPOCH + timedelta(days=int(value))
        raise ValueError(f"Date illisible : {value}.")
    text = str(value).strip().split(" ")[0]  # « 30/09/2026 00:00:00 » → « 30/09/2026 »
    for pattern, order in _DATE_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        a, b, c = (int(part) for part in match.groups())
        try:
            if order == "jma":
                return date(c, b, a)
            if order == "jma2":
                return date(2000 + c, b, a)
            return date(a, b, c)
        except ValueError:
            break
    raise ValueError(f"Date illisible : « {value} » (attendu jj/mm/aaaa).")


def parse_amount(value: object) -> Decimal | None:
    """Montant d'une cellule, exact à 2 décimales.

    Accepte les nombres Excel et les textes « 1 250 000,50 », « 1.250.000,50 », « 1,250,000.50 »,
    « -1 250,50 », « (1 250,50) », « 1 250,50- », avec ou sans DH / MAD / EUR / USD.
    """
    if is_blank(value):
        return None
    if isinstance(value, bool):
        raise ValueError(f"Montant illisible : {value}.")
    if isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        amount = Decimal(repr(value))
    elif isinstance(value, Decimal):
        amount = value
    else:
        amount = _parse_amount_text(str(value))
    if abs(amount) > MAX_AMOUNT:
        raise ValueError(f"Montant trop grand : « {value} ».")
    # Un nombre Excel calculé peut porter un résidu binaire (0,30000000000000004) : on l'ignore
    rounded = amount.quantize(Decimal("0.000001"))
    if rounded != rounded.quantize(CENT):
        raise ValueError(f"Montant avec plus de 2 décimales : « {value} ».")
    return rounded.quantize(CENT)


def _parse_amount_text(raw: str) -> Decimal:
    text = _SPACES.sub("", _CURRENCY.sub("", raw)).replace("'", "").replace("−", "-")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.endswith("-"):
        negative, text = True, text[:-1]
    if text.startswith("-"):
        negative, text = not negative, text[1:]
    elif text.startswith("+"):
        text = text[1:]

    if "," in text and "." in text:
        # Le dernier séparateur est celui des décimales, l'autre celui des milliers
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        text = text.replace(thousands, "").replace(decimal_sep, ".")
    elif "," in text:
        # Une seule virgule : décimales à la française ; plusieurs : séparateurs de milliers
        text = text.replace(",", ".") if text.count(",") == 1 else text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")

    if not re.fullmatch(r"\d+(\.\d+)?", text):
        raise ValueError(f"Montant illisible : « {raw} ».")
    try:
        amount = Decimal(text)
    except InvalidOperation as error:  # pragma: no cover - exclu par l'expression régulière
        raise ValueError(f"Montant illisible : « {raw} ».") from error
    return -amount if negative else amount


def clean_text(value: object) -> str | None:
    """Texte d'une cellule sans espaces superflus ; vide → None."""
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def clean_libelle(value: object) -> str | None:
    """Libellé normalisé pour le rapprochement : espaces réduits, en majuscules."""
    text = clean_text(value)
    return text.upper() if text else None


def extract_reference(libelle: str | None) -> str | None:
    """Référence trouvée dans un libellé (n° de chèque, REF, N°, facture), sinon None."""
    if not libelle:
        return None
    for pattern in _REFERENCE_PATTERNS:
        match = pattern.search(libelle.upper())
        if match:
            return match.group(1).strip()[:REFERENCE_MAX]
    return None


# --- Pointage automatique (décision métier du 02/10/2026) -----------------------------------------

POINTAGE_FRAIS = "FRAIS_BANCAIRES"
POINTAGE_ENCAISSEMENT = "ENCAISSEMENT"
POINTAGE_DECAISSEMENT = "DECAISSEMENT"
# Même règle que la migration 0005, qui l'applique aux opérations importées avant elle
_FRAIS = re.compile(r"\b(COMMISSIONS?|AGIOS|FRAIS|TENUE DE COMPTE)\b")


def _plain(text: str) -> str:
    """Majuscules sans accents : « Prélèvement » → « PRELEVEMENT »."""
    raw = unicodedata.normalize("NFKD", text)
    return "".join(char for char in raw if not unicodedata.combining(char)).upper()


def guess_pointage(
    libelle: str | None, debit: Decimal | None, credit: Decimal | None
) -> str | None:
    """Code du type d'opération déduit du libellé, puis du sens de l'opération.

    COMMISSION, AGIOS, FRAIS, TENUE DE COMPTE → Frais bancaires ; sinon un crédit → Encaissement,
    un débit → Décaissement. None si l'opération n'a pas de montant.
    """
    if libelle and _FRAIS.search(_plain(libelle)):
        return POINTAGE_FRAIS
    if credit:
        return POINTAGE_ENCAISSEMENT
    if debit:
        return POINTAGE_DECAISSEMENT
    return None


# --- Lignes de solde d'un relevé -------------------------------------------------------------------

_OPENING = re.compile(r"^(SOLDE INITIAL|SOLDE PRECEDENT|ANCIEN SOLDE|REPORT)\b")
_CLOSING = re.compile(r"^(SOLDE FINAL|NOUVEAU SOLDE)\b")


def balance_line_kind(libelle: str | None) -> str | None:
    """« ouverture » pour SOLDE INITIAL / ANCIEN SOLDE / SOLDE PRÉCÉDENT / REPORT, « cloture » pour
    SOLDE FINAL / NOUVEAU SOLDE, sinon None. Le libellé est comparé sans accents ni casse."""
    if not libelle:
        return None
    text = " ".join(_plain(libelle).split())
    if _OPENING.match(text):
        return "ouverture"
    if _CLOSING.match(text):
        return "cloture"
    return None


def file_hash(content: bytes) -> str:
    """Empreinte SHA-256 du contenu : un même fichier, quel que soit son nom, a la même empreinte."""
    return hashlib.sha256(content).hexdigest()


def line_hash(account_id: int, parts: tuple[object, ...], occurrence: int) -> str:
    """Empreinte d'une ligne de relevé pour un compte.

    `occurrence` numérote les lignes identiques d'un même fichier (1, 2...) : réimporter le fichier
    redonne les mêmes empreintes, mais deux frais identiques le même jour restent deux lignes.
    """
    text = "|".join("" if part is None else str(part) for part in (account_id, *parts, occurrence))
    return hashlib.sha256(text.encode()).hexdigest()
