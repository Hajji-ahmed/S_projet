"""Règles pures du rapprochement 1→1 (P11) : score d'une paire, puis choix des propositions.

Aucune lecture en base : `reconciliation_service` fournit les opérations, les écritures et la grille.
Le moteur ne fait que PROPOSER ; un humain autorisé valide chaque correspondance.

Sens : les écritures gardent le sens de Sage (P10). Un crédit en banque (argent qui entre) est un
débit du compte banque dans Sage ; une paire n'est donc comparée que si
`montant de l'opération = − montant de l'écriture` en signe, c'est-à-dire de signes opposés.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache

from app.services.normalization_service import extract_reference

try:
    # difflib compilé (15/10/2026) : mêmes ratios que difflib, environ 4 fois plus vite
    from cydifflib import SequenceMatcher
except ImportError:  # pragma: no cover - repli si la dépendance manque
    from difflib import SequenceMatcher

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# Codes des critères, dans l'ordre d'affichage du détail du score
CRITERES = ("reference", "montant", "date", "libelle", "tiers")
LIBELLES_CRITERES = {
    "reference": "N° chèque / référence",
    "montant": "Montant",
    "date": "Date",
    "libelle": "Libellé",
    "tiers": "Tiers",
}


@dataclass(frozen=True)
class Grille:
    """Grille de score (table `reconciliation_rules`) ; non encore validée par le métier.

    Décision du 07/10/2026 : montant, date et libellé (50 + 30 + 20). Décision du 08/10/2026 : le
    n° de chèque / référence revient (40), lu aussi dans les libellés ; le total reste plafonné à
    100. Le tiers est désactivé (0 point). Décision du 28/10/2026 : un montant identique vaut 60
    points s'il a des centimes, 40 s'il est rond (`points_montant`).
    """

    reference: Decimal = Decimal("40")
    # Montant identique avec centimes (28/10/2026 : 60 ; 50 avant pour tout montant identique)
    montant: Decimal = Decimal("60")
    # Montant identique sans centimes (28/10/2026)
    montant_rond: Decimal = Decimal("40")
    date: Decimal = Decimal("30")
    libelle: Decimal = Decimal("20")
    tiers: Decimal = Decimal("0")
    # Au-delà de `tolerance_jours` d'écart, le critère Date ne rapporte rien
    tolerance_jours: int = 3
    # Seules les écritures à ± `fenetre_jours` de l'opération sont comparées
    fenetre_jours: int = 10
    # Chèque ou effet au même n° et au même montant : comparé jusqu'à ± 180 jours (12/10/2026)
    fenetre_numero_jours: int = 180
    # Recherche élargie (bouton à part, 20/10/2026) : même n° et même montant jusqu'à ± 365 jours
    fenetre_elargie_jours: int = 365
    # Espèces (28/10/2026) : points de date pleins jusqu'à ± 2 jours de l'échéance Sage, puis
    # dégressifs sur `tolerance_jours` (27/10/2026 : jamais proposé au-delà de 2 jours)
    fenetre_especes_jours: int = 2
    # En dessous : aucune proposition
    seuil_proposition: Decimal = Decimal("50")
    # À partir de : « Forte correspondance », validable en lot (toujours par un humain) ; 80 depuis
    # le 08/10/2026
    seuil_fort: Decimal = Decimal("80")
    # Une 2e écriture à moins de cet écart de points est signalée « concurrente proche » ; depuis le
    # 08/10/2026, seule une égalité de score rend une opération ambiguë
    ecart_ambiguite: Decimal = Decimal("10")

    def poids(self, critere: str) -> Decimal:
        # Le montant rapporte `montant` ou `montant_rond` selon les centimes (28/10/2026)
        if critere == "montant":
            return max(self.montant, self.montant_rond)
        return getattr(self, critere)

    @property
    def criteres_actifs(self) -> tuple[str, ...]:
        """Critères qui rapportent des points, dans l'ordre d'affichage."""
        return tuple(code for code in CRITERES if self.poids(code) > 0)


GRILLE_PAR_DEFAUT = Grille()


@dataclass(frozen=True)
class Operation:
    """Opération bancaire comparée. `montant` = crédit − débit."""

    id: int
    date_operation: date
    date_valeur: date | None
    libelle: str
    reference: str | None
    montant: Decimal
    bank_account_id: int | None = None


@dataclass(frozen=True)
class Ecriture:
    """Écriture comptable comparée, au sens de Sage. `montant` = crédit − débit."""

    id: int
    date_ecriture: date
    libelle: str
    reference: str | None
    numero_piece: str | None
    tiers: str | None
    montant: Decimal
    # Compte bancaire du journal Sage de l'écriture
    bank_account_id: int | None = None
    # Échéance Sage : date comparée pour un effet (09/10/2026)
    echeance: date | None = None


@dataclass(frozen=True)
class Score:
    total: Decimal
    detail: dict[str, Decimal]


@dataclass(frozen=True)
class Proposition:
    operation_id: int
    ecriture_id: int
    score: Score
    # Meilleur score d'un autre candidat de l'opération ou de l'écriture (None : aucun)
    second: Decimal | None = None


@dataclass
class Resultat:
    propositions: list[Proposition] = field(default_factory=list)
    # Opérations et écritures dont plusieurs candidats ont le même meilleur score : « À vérifier »
    operations_ambigues: set[int] = field(default_factory=set)
    ecritures_ambigues: set[int] = field(default_factory=set)


# --- Normalisation des textes ----------------------------------------------------------------------

# Mots trop fréquents dans les libellés bancaires et comptables pour signaler une même opération
_MOTS_VIDES = frozenset(
    {
        "VIR", "VIREMENT", "VIRT", "REG", "REGLEMENT", "RGLT", "PAIEMENT", "PAIE", "CHQ", "CHEQUE",
        "CHEQUES", "FACT", "FACTURE", "FAC", "RECU", "RECUE", "EMIS", "EMISE", "REMISE", "PRLV",
        "PRELEVEMENT", "CLIENT", "FOURNISSEUR", "FRS", "REF", "SARL", "SA", "STE", "LE",
        "LA", "LES", "DE", "DU", "DES", "ET", "EN", "AU", "AUX", "PAR", "POUR", "SUR", "MAD", "DH",
        "DHS", "NO", "N",
    }
)  # fmt: skip
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
# N° de chèque, d'effet ou de remise : 5 chiffres ou plus (« EAR1° » n'en est pas un)
_NUMERO = re.compile(r"\d{5,}")


# Un même libellé revient dans des milliers de paires : sa forme normalisée est calculée une fois
_CACHE = 65536


@lru_cache(maxsize=_CACHE)
def _plain(text: str | None) -> str:
    """Majuscules sans accents, ponctuation remplacée par des espaces."""
    if not text:
        return ""
    raw = unicodedata.normalize("NFKD", text)
    upper = "".join(char for char in raw if not unicodedata.combining(char)).upper()
    return " ".join(_NON_ALNUM.sub(" ", upper).split())


@lru_cache(maxsize=_CACHE)
def _mots(text: str | None) -> frozenset[str]:
    """Mots significatifs d'un libellé : sans mots vides, d'au moins 2 caractères."""
    return frozenset(
        mot for mot in _plain(text).split() if len(mot) >= 2 and mot not in _MOTS_VIDES
    )


def _cle(value: str | None) -> str:
    """Référence comparable : majuscules, lettres et chiffres seulement (« REG-458 » → « REG458 »)."""
    return _plain(value).replace(" ", "")


@lru_cache(maxsize=_CACHE)
def _motif_cle(cle: str) -> re.Pattern[str]:
    motif = r"\s?".join(re.escape(char) for char in cle)
    return re.compile(rf"(?<![A-Z0-9]){motif}(?![A-Z0-9])")


def _contient(texte_plain: str, cle: str) -> bool:
    """La clé (lettres et chiffres) apparaît dans le texte comme un mot entier ; la ponctuation et
    les espaces entre ses caractères sont ignorés (« REG-458 » et « REG 458 » contiennent REG458)."""
    if not cle:
        return False
    return _motif_cle(cle).search(texte_plain) is not None


# --- Type d'opération lu dans le libellé (décision du 09/10/2026) ------------------------------------
# Une ligne Chèque ne se rapproche jamais d'une ligne Effet ou Espèces ; « Autre » (virements, frais…)
# reste comparable à tout. Préfixes cherchés au début du libellé normalisé (`_plain`).
TYPES_SAGE: tuple[tuple[str, str], ...] = (
    # Impayés (16/10/2026) : « IMP EAR1° … », « IMP EAR° … » annulent un encaissement
    ("IMPAYE", "Impayé"),
    ("IMP", "Impayé"),
    ("EAR1", "Chèque"),  # « EAR1° … »
    ("EAR", "Effet"),  # « EAR° … »
    ("LCN", "Effet"),  # « LCN … » (28/10/2026)
    ("ESP", "Espèces"),
    # Virements (12/10/2026) : « Virement … » d'un côté, « VIR … » de l'autre
    ("VIREMENT", "Virement"),
    ("VIRT", "Virement"),
    ("VIR", "Virement"),
)
TYPES_BANQUE: tuple[tuple[str, str], ...] = (
    # Impayés (16/10/2026) : « IMPAYE SUR EFFET ESCOMPTE N … », « IMP LCN … »
    ("IMPAYE", "Impayé"),
    ("IMP", "Impayé"),
    ("ENCAISSEMENT CHEQUE", "Chèque"),
    ("ENCAISSEMENT EFFET", "Effet"),
    ("REMISE D EFFETS", "Effet"),
    ("VERSEMENT DEPLACE", "Espèces"),
    # Virements (12/10/2026) : « Virement … » d'un côté, « VIR … » de l'autre
    ("VIREMENT", "Virement"),
    ("VIRT", "Virement"),
    ("VIR", "Virement"),
    ("RTGS", "Virement"),
)


def _type(libelle: str | None, regles: tuple[tuple[str, str], ...]) -> str | None:
    texte = _plain(libelle)
    for prefixe, nom in regles:
        if texte == prefixe or texte.startswith(prefixe + " "):
            return nom
    return None


@lru_cache(maxsize=_CACHE)
def type_operation(libelle: str | None) -> str | None:
    """Type d'une opération bancaire (Chèque, Effet, Espèces) ; None = autre."""
    return _type(libelle, TYPES_BANQUE)


@lru_cache(maxsize=_CACHE)
def type_ecriture(libelle: str | None) -> str | None:
    """Type d'une écriture Sage (Chèque, Effet, Espèces) ; None = autre."""
    return _type(libelle, TYPES_SAGE)


def types_compatibles(operation: Operation, ecriture: Ecriture) -> bool:
    """Le moteur ne compare que deux lignes du même type (28/10/2026) : chèque avec chèque,
    espèces avec espèces…, et un type inconnu (autre) seulement avec un autre type inconnu. Le
    rapprochement manuel garde sa propre règle (deux types connus différents refusés)."""
    return type_operation(operation.libelle) == type_ecriture(ecriture.libelle)


def numeros(*textes: str | None) -> set[str]:
    """Numéros de 5 chiffres ou plus des textes, sans les zéros en tête (« 0173813 » → « 173813 »)."""
    return set().union(*(_numeros_du_texte(texte) for texte in textes if texte))


@lru_cache(maxsize=_CACHE)
def _numeros_du_texte(texte: str) -> frozenset[str]:
    return frozenset(numero.lstrip("0") or "0" for numero in _NUMERO.findall(texte))


# --- Critères --------------------------------------------------------------------------------------


def _points(poids: Decimal, ratio: Decimal) -> Decimal:
    return (poids * ratio).quantize(CENT, rounding=ROUND_HALF_UP)


def critere_reference(operation: Operation, ecriture: Ecriture) -> bool:
    """Même référence / n° de chèque / n° de pièce des deux côtés.

    Un même numéro de 5 chiffres ou plus dans les libellés ou références des deux côtés, sans les
    zéros en tête (« CHEQUE N 0173813 » ↔ « EAR1° AXK 173813 », décision du 08/10/2026). Sinon,
    clés de l'écriture : sa référence et son N° pièce ; clés de l'opération : sa référence et celle
    trouvée dans son libellé. Une clé de l'écriture (3 caractères au moins) écrite dans le libellé
    ou la référence bancaire compte aussi (« CHQ 1234567 » contient la pièce 1234567).
    """
    return _reference_preparee(_cote_operation(operation), _cote_ecriture(ecriture))


@dataclass(frozen=True)
class _Cote:
    """Ce que le score lit d'une ligne, calculé une seule fois par ligne (15/10/2026)."""

    plain: str
    mots: frozenset[str]
    numeros: frozenset[str]
    cles: frozenset[str]
    # Opération : son libellé et sa référence, où chercher une clé de l'écriture
    textes: tuple[str, ...] = ()


def _cote_operation(operation: Operation) -> _Cote:
    return _Cote(
        plain=_plain(operation.libelle),
        mots=_mots(operation.libelle),
        numeros=frozenset(numeros(operation.libelle, operation.reference)),
        cles=frozenset(
            {_cle(operation.reference), _cle(extract_reference(operation.libelle))} - {""}
        ),
        textes=(_plain(operation.libelle), _plain(operation.reference)),
    )


def _cote_ecriture(ecriture: Ecriture) -> _Cote:
    return _Cote(
        plain=_plain(ecriture.libelle),
        mots=_mots(ecriture.libelle),
        numeros=frozenset(numeros(ecriture.libelle, ecriture.reference, ecriture.numero_piece)),
        cles=frozenset({_cle(ecriture.reference), _cle(ecriture.numero_piece)} - {""}),
    )


def _reference_preparee(operation: _Cote, ecriture: _Cote) -> bool:
    """`critere_reference` sur des lignes préparées : mêmes règles."""
    if operation.numeros & ecriture.numeros:
        return True
    if ecriture.cles & operation.cles:
        return True
    return any(
        len(cle) >= 3 and _contient(texte, cle)
        for cle in ecriture.cles
        for texte in operation.textes
    )


def _mots_prepares(operation: _Cote, ecriture: _Cote) -> Decimal:
    """`_ratio_mots` sur des lignes préparées."""
    if not operation.mots or not ecriture.mots:
        return Decimal(0)
    plus_court = min(len(operation.mots), len(ecriture.mots))
    return Decimal(len(operation.mots & ecriture.mots)) / Decimal(plus_court)


# Types comparés à leur échéance Sage (décision du 12/10/2026) : espèces et virements. Chèques et
# effets sont comparés à la date de l'écriture (points dégressifs sur 3 jours).
TYPES_PAR_ECHEANCE = frozenset({"Espèces", "Virement"})


ESPECES = "Espèces"


def est_especes(operation: Operation, ecriture: Ecriture) -> bool:
    """Un des deux côtés est des espèces (une écriture « ESP » face à un versement au libellé non
    reconnu compte)."""
    return ESPECES in (type_operation(operation.libelle), type_ecriture(ecriture.libelle))


def points_montant(montant_banque: Decimal, montant_sage: Decimal, grille: Grille) -> Decimal:
    """Points du montant (28/10/2026) : montants exactement opposés, `montant` (60) s'ils ont des
    centimes, `montant_rond` (40) sinon ; 0 si les montants diffèrent."""
    if montant_banque != -montant_sage:
        return ZERO
    return grille.montant if montant_banque % 1 else grille.montant_rond


def points_date(ecart: int, especes: bool, grille: Grille) -> Decimal:
    """Points de la date. Espèces (28/10/2026) : pleins jusqu'à `fenetre_especes_jours` d'écart,
    puis dégressifs comme les autres (2 j : 30 ; 3 j : 22,5 ; 4 j : 15 ; 5 j : 7,5 ; 6 j : 0)."""
    if especes:
        ecart = max(0, ecart - grille.fenetre_especes_jours)
    return _points(grille.date, ratio_date(ecart, grille.tolerance_jours))


def date_comparee(ecriture: Ecriture) -> date:
    """Date Sage comparée : l'échéance pour des espèces ou un virement qui en ont une, sinon la date
    de l'écriture."""
    if ecriture.echeance is not None and type_ecriture(ecriture.libelle) in TYPES_PAR_ECHEANCE:
        return ecriture.echeance
    return ecriture.date_ecriture


def ecart_jours(operation: Operation, ecriture: Ecriture) -> int:
    """Écart, en jours, entre la date Sage comparée et la date bancaire : pour des espèces ou un
    virement, la plus proche de la date de valeur et de la date d'opération ; pour les autres types
    (chèque, effet, frais…), la date d'opération seulement, la date de valeur étant décalée par la
    banque."""
    jour_sage = date_comparee(ecriture)
    dates = [operation.date_operation]
    if operation.date_valeur and type_ecriture(ecriture.libelle) in TYPES_PAR_ECHEANCE:
        dates.append(operation.date_valeur)
    return min(abs((jour - jour_sage).days) for jour in dates)


def ratio_date(ecart: int, tolerance: int) -> Decimal:
    """1 le même jour, puis dégressif jusqu'à 0 au-delà de la tolérance (3 j : 1, ¾, ½, ¼, 0)."""
    if ecart > tolerance:
        return ZERO
    return Decimal(tolerance + 1 - ecart) / Decimal(tolerance + 1)


def _ratio_mots(operation: Operation, ecriture: Ecriture) -> Decimal:
    """Mots significatifs communs, sur le plus court des deux libellés (0 à 1)."""
    mots_operation, mots_ecriture = _mots(operation.libelle), _mots(ecriture.libelle)
    if not mots_operation or not mots_ecriture:
        return Decimal(0)
    plus_court = min(len(mots_operation), len(mots_ecriture))
    return Decimal(len(mots_operation & mots_ecriture)) / Decimal(plus_court)


def ratio_libelle(operation: Operation, ecriture: Ecriture) -> Decimal:
    """Similarité des libellés, de 0 à 1 : le meilleur entre les mots significatifs communs (sur le
    plus court des deux libellés) et la similarité des caractères."""
    caracteres = SequenceMatcher(None, _plain(operation.libelle), _plain(ecriture.libelle)).ratio()
    return max(_ratio_mots(operation, ecriture), Decimal(str(round(caracteres, 4))))


def critere_tiers(operation: Operation, ecriture: Ecriture) -> bool:
    """Le tiers de l'écriture apparaît dans le libellé bancaire (tous ses mots significatifs)."""
    if not ecriture.tiers:
        return False
    libelle = _plain(operation.libelle)
    if _contient(libelle, _cle(ecriture.tiers)):
        return True
    mots_tiers = _mots(ecriture.tiers)
    return bool(mots_tiers) and mots_tiers <= set(libelle.split())


def comparable(operation: Operation, ecriture: Ecriture, grille: Grille) -> bool:
    """Pré-filtre : même compte bancaire, sens opposés (crédit banque ↔ débit Sage), même type
    d'opération quand les deux sont connus (09/10/2026) et dates dans la fenêtre."""
    return _ecart_si_comparable(operation, ecriture, grille) is not None


def _ecart_si_comparable(operation: Operation, ecriture: Ecriture, grille: Grille) -> int | None:
    """L'écart de dates de la paire si elle passe le pré-filtre (`comparable`), sinon None : il
    est calculé une seule fois et resservi au score (15/10/2026)."""
    if operation.bank_account_id != ecriture.bank_account_id:
        return None
    if operation.montant == 0 or ecriture.montant == 0:
        return None
    if (operation.montant > 0) == (ecriture.montant > 0):
        return None
    if not types_compatibles(operation, ecriture):
        return None
    ecart = ecart_jours(operation, ecriture)
    if ecart <= grille.fenetre_jours:
        return ecart
    # Au-delà : seulement un chèque ou un effet au même n° et au même montant (12/10/2026)
    if ecart <= grille.fenetre_numero_jours and meme_numero_et_montant(operation, ecriture):
        return ecart
    return None


# Types rapprochés par leur n° même loin en date : chèques et effets (12/10/2026), impayés
# (16/10/2026)
TYPES_PAR_NUMERO = frozenset({"Chèque", "Effet", "Impayé"})


def _numeros_ecriture(ecriture: Ecriture) -> set[str]:
    return numeros(ecriture.libelle, ecriture.reference, ecriture.numero_piece)


def meme_numero_et_montant(operation: Operation, ecriture: Ecriture) -> bool:
    """Chèque, effet ou impayé des deux côtés, même montant (sens opposé) et un n° commun."""
    if type_operation(operation.libelle) not in TYPES_PAR_NUMERO:
        return False
    if type_ecriture(ecriture.libelle) != type_operation(operation.libelle):
        return False
    if operation.montant != -ecriture.montant:
        return False
    return bool(numeros(operation.libelle, operation.reference) & _numeros_ecriture(ecriture))


def score(operation: Operation, ecriture: Ecriture, grille: Grille = GRILLE_PAR_DEFAUT) -> Score:
    """Points obtenus par critère et total sur 100."""
    return _score(operation, ecriture, grille, ecart_jours(operation, ecriture), None)


def _score(
    operation: Operation,
    ecriture: Ecriture,
    grille: Grille,
    ecart: int,
    reference: bool | None,
) -> Score:
    """`score`, avec l'écart de dates (et la référence, si elle est déjà connue) calculés par
    l'appelant : mêmes formules, sans les refaire."""
    if reference is None:
        reference = critere_reference(operation, ecriture)
    detail = {
        "reference": grille.reference if reference else ZERO,
        "montant": points_montant(operation.montant, ecriture.montant, grille),
        "date": points_date(ecart, est_especes(operation, ecriture), grille),
        "libelle": _points(grille.libelle, ratio_libelle(operation, ecriture)),
        "tiers": grille.tiers if critere_tiers(operation, ecriture) else ZERO,
    }
    detail = {code: value.quantize(CENT) for code, value in detail.items()}
    total = min(sum(detail.values(), ZERO), Decimal("100.00")).quantize(CENT)
    return Score(total=total, detail=detail)


def est_forte(total: Decimal, grille: Grille = GRILLE_PAR_DEFAUT) -> bool:
    return total >= grille.seuil_fort


# --- Choix des propositions ------------------------------------------------------------------------


def proposer(
    operations: Iterable[Operation],
    ecritures: Iterable[Ecriture],
    grille: Grille = GRILLE_PAR_DEFAUT,
    paires_rejetees: frozenset[tuple[int, int]] | set[tuple[int, int]] = frozenset(),
) -> Resultat:
    """Propositions 1→1, prudentes : une paire n'est proposée que si elle est, sans ambiguïté, le
    meilleur candidat de son opération ET de son écriture.

    - Une paire rejetée par un utilisateur (rejet en vigueur) n'est pas reproposée.
    - Une paire sous le seuil de proposition n'est pas un candidat.
    - Si les deux meilleurs candidats d'une opération (ou d'une écriture) ont le même score,
      aucune proposition pour elle (décision du 08/10/2026 : avant, à moins de 10 points). Sinon le
      meilleur est proposé, avec le score du suivant (`second`).
    - Les paires retenues sont retirées, puis le choix recommence sur ce qui reste.
    - À la fin, une opération ou une écriture qui garde un candidat est « ambiguë » (« À vérifier »).
    """
    operations, ecritures = list(operations), list(ecritures)
    cotes_op = {operation.id: _cote_operation(operation) for operation in operations}
    cotes_ec = {ecriture.id: _cote_ecriture(ecriture) for ecriture in ecritures}
    candidats: dict[tuple[int, int], Score] = {}
    for operation, ecriture, ecart in _paires_comparables(operations, ecritures, grille):
        if (operation.id, ecriture.id) in paires_rejetees:
            continue
        resultat = _candidat(
            operation, ecriture, grille, ecart, cotes_op[operation.id], cotes_ec[ecriture.id]
        )
        if resultat is not None:
            candidats[(operation.id, ecriture.id)] = resultat

    # Attribution du meilleur score au plus bas (16/10/2026) : une ligne déjà prise passe sa
    # place à la suivante ; seule une ÉGALITÉ au meilleur score d'une ligne la rend ambiguë (ses
    # candidates à égalité aussi), jamais une concurrente de score inférieur
    resultat = Resultat()
    par_operation: dict[int, list[tuple[Decimal, int]]] = {}
    par_ecriture: dict[int, list[tuple[Decimal, int]]] = {}
    for (operation_id, ecriture_id), valeur in candidats.items():
        par_operation.setdefault(operation_id, []).append((valeur.total, ecriture_id))
        par_ecriture.setdefault(ecriture_id, []).append((valeur.total, operation_id))
    for liste in (*par_operation.values(), *par_ecriture.values()):
        liste.sort(key=lambda item: (-item[0], item[1]))
    pris_op: set[int] = set()
    pris_ec: set[int] = set()

    def libres(liste, pris, ambigus, nombre=2):
        """Les `nombre` premiers partenaires encore libres de la ligne."""
        trouves = []
        for total, cle in liste:
            if cle not in pris and cle not in ambigus:
                trouves.append((total, cle))
                if len(trouves) == nombre:
                    break
        return trouves

    for (operation_id, ecriture_id), valeur in sorted(
        candidats.items(), key=lambda item: (-item[1].total, item[0])
    ):
        if operation_id in pris_op or operation_id in resultat.operations_ambigues:
            continue
        if ecriture_id in pris_ec or ecriture_id in resultat.ecritures_ambigues:
            continue
        cote_op = libres(par_operation[operation_id], pris_ec, resultat.ecritures_ambigues)
        cote_ec = libres(par_ecriture[ecriture_id], pris_op, resultat.operations_ambigues)
        if (len(cote_op) == 2 and cote_op[1][0] == valeur.total) or (
            len(cote_ec) == 2 and cote_ec[1][0] == valeur.total
        ):
            # Plusieurs lignes au même meilleur score : toutes celles liées entre elles à ce score
            # sont ambiguës (deux opérations identiques face à deux écritures identiques)
            ops, ecs = {operation_id}, {ecriture_id}
            a_voir = [("op", operation_id), ("ec", ecriture_id)]
            while a_voir:
                cote, cle = a_voir.pop()
                if cote == "op":
                    for total, autre in par_operation[cle]:
                        if total == valeur.total and autre not in pris_ec and autre not in ecs:
                            ecs.add(autre)
                            a_voir.append(("ec", autre))
                else:
                    for total, autre in par_ecriture[cle]:
                        if total == valeur.total and autre not in pris_op and autre not in ops:
                            ops.add(autre)
                            a_voir.append(("op", autre))
            resultat.operations_ambigues.update(ops)
            resultat.ecritures_ambigues.update(ecs)
            continue
        autres = [total for total, _ in cote_op[1:]] + [total for total, _ in cote_ec[1:]]
        resultat.propositions.append(
            Proposition(operation_id, ecriture_id, valeur, max(autres) if autres else None)
        )
        pris_op.add(operation_id)
        pris_ec.add(ecriture_id)

    resultat.propositions.sort(key=lambda item: (item.operation_id, item.ecriture_id))
    return resultat


def _peut_atteindre(operation: Operation, ecriture: Ecriture, grille: Grille) -> bool:
    """Le score de la paire peut-il atteindre le seuil de proposition, même avec un libellé et un
    tiers parfaits ? Sinon, le libellé (le calcul le plus coûteux) n'est pas comparé : une paire
    écartée ici aurait de toute façon un score sous le seuil, le résultat ne change pas."""
    plafond = (
        points_montant(operation.montant, ecriture.montant, grille)
        + points_date(ecart_jours(operation, ecriture), est_especes(operation, ecriture), grille)
        + grille.libelle
        + grille.tiers
    )
    if plafond >= grille.seuil_proposition:
        return True
    if grille.reference and critere_reference(operation, ecriture):
        plafond += grille.reference
    return plafond >= grille.seuil_proposition


def _majorant(ratio: float) -> Decimal:
    return Decimal(str(round(ratio, 4)))


def _candidat(
    operation: Operation,
    ecriture: Ecriture,
    grille: Grille,
    ecart: int,
    cote_op: _Cote | None = None,
    cote_ec: _Cote | None = None,
) -> Score | None:
    """Score de la paire si elle atteint le seuil de proposition, sinon None (15/10/2026 : 15
    millions de paires sur une année BP). Une paire qui ne peut pas atteindre le seuil, même avec
    le meilleur libellé possible, est écartée sans calculer le libellé exact ; les autres reçoivent
    le score exact de `score`. Le résultat ne change pas.

    Sans le libellé, la paire a ses points de montant, de date, de tiers, puis de référence ; il
    lui manque `manque` points. Trois majorants du libellé décident d'abord, du moins coûteux au
    plus coûteux (mots communs ; longueurs, comme `real_quick_ratio` ; `quick_ratio`) ; le vrai
    ratio n'est calculé que s'il le faut."""
    cote_op = cote_op or _cote_operation(operation)
    cote_ec = cote_ec or _cote_ecriture(ecriture)
    acquis = (
        points_montant(operation.montant, ecriture.montant, grille)
        + points_date(ecart, est_especes(operation, ecriture), grille)
        + (grille.tiers if grille.tiers and critere_tiers(operation, ecriture) else ZERO)
    )
    manque = grille.seuil_proposition - acquis
    if manque > grille.libelle + grille.reference:
        return None
    reference = bool(grille.reference) and _reference_preparee(cote_op, cote_ec)
    if reference:
        manque -= grille.reference
    if manque > grille.libelle:
        return None
    if manque > 0 and _points(grille.libelle, _mots_prepares(cote_op, cote_ec)) < manque:
        # `ratio` ≤ `quick_ratio` ≤ `real_quick_ratio` = 2·min(longueurs) / somme des longueurs
        a, b = cote_op.plain, cote_ec.plain
        longueurs = len(a) + len(b)
        borne = 2 * min(len(a), len(b)) / longueurs if longueurs else 1.0
        if _points(grille.libelle, _majorant(borne)) < manque:
            return None
        if _points(grille.libelle, _majorant(SequenceMatcher(None, a, b).quick_ratio())) < manque:
            return None
    resultat = _score(operation, ecriture, grille, ecart, reference)
    return resultat if resultat.total >= grille.seuil_proposition else None


def _paires_comparables(
    operations: Iterable[Operation], ecritures: Iterable[Ecriture], grille: Grille
) -> Iterable[tuple[Operation, Ecriture, int]]:
    """Paires qui passent le pré-filtre. Les écritures sont rangées par jour : chaque opération ne
    parcourt que les jours de sa fenêtre, jamais toutes les écritures."""
    par_jour: dict[date, list[Ecriture]] = {}
    # Chèques et effets aussi rangés par n° : comparés au-delà de la fenêtre (12/10/2026)
    par_numero: dict[str, list[Ecriture]] = {}
    for ecriture in ecritures:
        par_jour.setdefault(date_comparee(ecriture), []).append(ecriture)
        if type_ecriture(ecriture.libelle) in TYPES_PAR_NUMERO:
            for numero in _numeros_ecriture(ecriture):
                par_numero.setdefault(numero, []).append(ecriture)
    for operation in operations:
        vues: set[int] = set()
        if type_operation(operation.libelle) in TYPES_PAR_NUMERO:
            for numero in numeros(operation.libelle, operation.reference):
                for ecriture in par_numero.get(numero, ()):
                    if ecriture.id not in vues:
                        vues.add(ecriture.id)
                        ecart = _ecart_si_comparable(operation, ecriture, grille)
                        if ecart is not None:
                            yield operation, ecriture, ecart
        jours = {operation.date_operation}
        if operation.date_valeur:
            jours.add(operation.date_valeur)
        for jour in sorted(jours):
            for decalage in range(-grille.fenetre_jours, grille.fenetre_jours + 1):
                for ecriture in par_jour.get(jour + timedelta(days=decalage), ()):
                    if ecriture.id in vues:
                        continue
                    vues.add(ecriture.id)
                    ecart = _ecart_si_comparable(operation, ecriture, grille)
                    if ecart is not None:
                        yield operation, ecriture, ecart


def _meilleur_net(candidats: list[tuple[Decimal, int]], grille: Grille) -> int | None:
    """Identifiant du meilleur candidat, ou None si le deuxième a le même score (ambiguïté)."""
    classes = sorted(candidats, key=lambda item: (-item[0], item[1]))
    if len(classes) >= 2 and classes[0][0] == classes[1][0]:
        return None
    return classes[0][1]


# --- Filtre « Type d'opération » des écrans (14/10/2026) ------------------------------------------

TYPES_OPERATION = ("Chèque", "Effet", "Espèces", "Virement", "Impayé")
AUTRE = "Autre"
_SEPARATEUR = "[^A-Za-z0-9]"


def regex_type(regles: tuple[tuple[str, str], ...], nom: str | None = None) -> str:
    """Expression régulière PostgreSQL (insensible à la casse, `~*`) qui reconnaît en base les
    libellés d'un type, comme `type_operation` / `type_ecriture` : le libellé commence par l'un
    des préfixes, mot entier (la ponctuation compte comme un espace). Sans `nom`, tous les types."""
    prefixes = [
        f"{_SEPARATEUR}+".join(prefixe.split())
        for prefixe, type_ in regles
        if nom is None or type_ == nom
    ]
    return f"^{_SEPARATEUR}*({'|'.join(prefixes)})({_SEPARATEUR}|$)"


# --- Recherche élargie (20/10/2026) ---------------------------------------------------------------


@dataclass(frozen=True)
class PropositionElargie:
    operation_id: int
    ecriture_id: int
    score: Score
    ecart_jours: int
    second: Decimal | None = None


def proposer_elargi(
    operations: Iterable[Operation],
    ecritures: Iterable[Ecriture],
    grille: Grille = GRILLE_PAR_DEFAUT,
    paires_rejetees: frozenset[tuple[int, int]] | set[tuple[int, int]] = frozenset(),
) -> list[PropositionElargie]:
    """Paires très éloignées en date (au-delà de `fenetre_jours`, jusqu'à `fenetre_elargie_jours`) :
    montant exactement opposé,
    même compte, types compatibles et un n° commun (5 chiffres ou plus, ou la référence). Les
    écritures sont rangées par (compte, montant) : chaque opération ne regarde que celles de son
    montant opposé. Une paire n'est proposée que si chacune n'a QUE cette candidate."""
    par_montant: dict[tuple[int | None, Decimal], list[Ecriture]] = {}
    for ecriture in ecritures:
        par_montant.setdefault((ecriture.bank_account_id, ecriture.montant), []).append(ecriture)
    candidats: dict[int, list[tuple[Operation, Ecriture, int]]] = {}
    par_ecriture: dict[int, int] = {}
    for operation in operations:
        numeros_op = numeros(operation.libelle, operation.reference)
        if not numeros_op:
            continue
        for ecriture in par_montant.get((operation.bank_account_id, -operation.montant), ()):
            if (operation.id, ecriture.id) in paires_rejetees:
                continue
            if not types_compatibles(operation, ecriture):
                continue
            if not numeros_op & _numeros_ecriture(ecriture):
                continue
            ecart = ecart_jours(operation, ecriture)
            # Dans la fenêtre normale, c'est le moteur habituel qui compare
            if ecart <= grille.fenetre_jours or ecart > grille.fenetre_elargie_jours:
                continue
            candidats.setdefault(operation.id, []).append((operation, ecriture, ecart))
            par_ecriture[ecriture.id] = par_ecriture.get(ecriture.id, 0) + 1
    propositions = []
    for liste in candidats.values():
        if len(liste) != 1:
            continue
        operation, ecriture, ecart = liste[0]
        if par_ecriture[ecriture.id] != 1:
            continue
        resultat = score(operation, ecriture, grille)
        if resultat.total >= grille.seuil_proposition:
            propositions.append(PropositionElargie(operation.id, ecriture.id, resultat, ecart))
    return propositions
