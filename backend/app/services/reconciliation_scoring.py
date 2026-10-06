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
from difflib import SequenceMatcher

from app.services.normalization_service import extract_reference

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# Codes des critères, dans l'ordre d'affichage du détail du score
CRITERES = ("reference", "montant", "date", "libelle", "tiers")
LIBELLES_CRITERES = {
    "reference": "Référence / N° pièce",
    "montant": "Montant",
    "date": "Date",
    "libelle": "Libellé",
    "tiers": "Tiers",
}


@dataclass(frozen=True)
class Grille:
    """Grille de score (table `reconciliation_rules`, plan P11) ; non encore validée par le métier."""

    reference: Decimal = Decimal("40")
    montant: Decimal = Decimal("30")
    date: Decimal = Decimal("15")
    libelle: Decimal = Decimal("10")
    tiers: Decimal = Decimal("5")
    # Au-delà de `tolerance_jours` d'écart, le critère Date ne rapporte rien
    tolerance_jours: int = 3
    # Seules les écritures à ± `fenetre_jours` de l'opération sont comparées
    fenetre_jours: int = 10
    # En dessous : aucune proposition
    seuil_proposition: Decimal = Decimal("50")
    # À partir de : « Forte correspondance », validable en lot (toujours par un humain)
    seuil_fort: Decimal = Decimal("90")
    # Deux candidats à moins de cet écart de points : ambiguïté, aucune proposition
    ecart_ambiguite: Decimal = Decimal("10")

    def poids(self, critere: str) -> Decimal:
        return getattr(self, critere)


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


@dataclass(frozen=True)
class Score:
    total: Decimal
    detail: dict[str, Decimal]


@dataclass(frozen=True)
class Proposition:
    operation_id: int
    ecriture_id: int
    score: Score


@dataclass
class Resultat:
    propositions: list[Proposition] = field(default_factory=list)
    # Opérations et écritures dont plusieurs candidats ont un score proche : « À vérifier »
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


def _plain(text: str | None) -> str:
    """Majuscules sans accents, ponctuation remplacée par des espaces."""
    if not text:
        return ""
    raw = unicodedata.normalize("NFKD", text)
    upper = "".join(char for char in raw if not unicodedata.combining(char)).upper()
    return " ".join(_NON_ALNUM.sub(" ", upper).split())


def _mots(text: str | None) -> set[str]:
    """Mots significatifs d'un libellé : sans mots vides, d'au moins 2 caractères."""
    return {mot for mot in _plain(text).split() if len(mot) >= 2 and mot not in _MOTS_VIDES}


def _cle(value: str | None) -> str:
    """Référence comparable : majuscules, lettres et chiffres seulement (« REG-458 » → « REG458 »)."""
    return _plain(value).replace(" ", "")


def _contient(texte_plain: str, cle: str) -> bool:
    """La clé (lettres et chiffres) apparaît dans le texte comme un mot entier ; la ponctuation et
    les espaces entre ses caractères sont ignorés (« REG-458 » et « REG 458 » contiennent REG458)."""
    if not cle:
        return False
    motif = r"\s?".join(re.escape(char) for char in cle)
    return re.search(rf"(?<![A-Z0-9]){motif}(?![A-Z0-9])", texte_plain) is not None


# --- Critères --------------------------------------------------------------------------------------


def _points(poids: Decimal, ratio: Decimal) -> Decimal:
    return (poids * ratio).quantize(CENT, rounding=ROUND_HALF_UP)


def critere_reference(operation: Operation, ecriture: Ecriture) -> bool:
    """Même référence / n° de chèque / n° de pièce des deux côtés.

    Clés de l'écriture : sa référence et son N° pièce. Clés de l'opération : sa référence et celle
    trouvée dans son libellé. Une clé de l'écriture (3 caractères au moins) écrite dans le libellé
    ou la référence bancaire compte aussi (« CHQ 1234567 » contient la pièce 1234567).
    """
    cles_ecriture = {_cle(ecriture.reference), _cle(ecriture.numero_piece)} - {""}
    cles_operation = {_cle(operation.reference), _cle(extract_reference(operation.libelle))} - {""}
    if cles_ecriture & cles_operation:
        return True
    textes = [_plain(operation.libelle), _plain(operation.reference)]
    return any(len(cle) >= 3 and _contient(texte, cle) for cle in cles_ecriture for texte in textes)


def ecart_jours(operation: Operation, ecriture: Ecriture) -> int:
    """Plus petit écart, en jours, entre l'écriture et la date d'opération ou de valeur."""
    dates = [operation.date_operation] + ([operation.date_valeur] if operation.date_valeur else [])
    return min(abs((jour - ecriture.date_ecriture).days) for jour in dates)


def ratio_date(ecart: int, tolerance: int) -> Decimal:
    """1 le même jour, puis dégressif jusqu'à 0 au-delà de la tolérance (3 j : 1, ¾, ½, ¼, 0)."""
    if ecart > tolerance:
        return ZERO
    return Decimal(tolerance + 1 - ecart) / Decimal(tolerance + 1)


def ratio_libelle(operation: Operation, ecriture: Ecriture) -> Decimal:
    """Similarité des libellés, de 0 à 1 : le meilleur entre les mots significatifs communs (sur le
    plus court des deux libellés) et la similarité des caractères."""
    mots_operation, mots_ecriture = _mots(operation.libelle), _mots(ecriture.libelle)
    communs = Decimal(0)
    if mots_operation and mots_ecriture:
        plus_court = min(len(mots_operation), len(mots_ecriture))
        communs = Decimal(len(mots_operation & mots_ecriture)) / Decimal(plus_court)
    caracteres = SequenceMatcher(None, _plain(operation.libelle), _plain(ecriture.libelle)).ratio()
    return max(communs, Decimal(str(round(caracteres, 4))))


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
    """Pré-filtre : même compte bancaire, sens opposés (crédit banque ↔ débit Sage) et dates dans
    la fenêtre."""
    if operation.bank_account_id != ecriture.bank_account_id:
        return False
    if operation.montant == 0 or ecriture.montant == 0:
        return False
    if (operation.montant > 0) == (ecriture.montant > 0):
        return False
    return ecart_jours(operation, ecriture) <= grille.fenetre_jours


def score(operation: Operation, ecriture: Ecriture, grille: Grille = GRILLE_PAR_DEFAUT) -> Score:
    """Points obtenus par critère et total sur 100."""
    detail = {
        "reference": grille.reference if critere_reference(operation, ecriture) else ZERO,
        "montant": grille.montant if operation.montant == -ecriture.montant else ZERO,
        "date": _points(
            grille.date, ratio_date(ecart_jours(operation, ecriture), grille.tolerance_jours)
        ),
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

    - Une paire déjà rejetée par un utilisateur n'est jamais reproposée.
    - Une paire sous le seuil de proposition n'est pas un candidat.
    - Si les deux meilleurs candidats d'une opération (ou d'une écriture) sont à moins de
      `ecart_ambiguite` points, aucune proposition pour elle.
    - Les paires retenues sont retirées, puis le choix recommence sur ce qui reste.
    - À la fin, une opération ou une écriture qui garde un candidat est « ambiguë » (« À vérifier »).
    """
    candidats: dict[tuple[int, int], Score] = {}
    for operation, ecriture in _paires_comparables(operations, ecritures, grille):
        if (operation.id, ecriture.id) in paires_rejetees:
            continue
        resultat = score(operation, ecriture, grille)
        if resultat.total >= grille.seuil_proposition:
            candidats[(operation.id, ecriture.id)] = resultat

    resultat = Resultat()
    restants = dict(candidats)
    while True:
        par_operation: dict[int, list[tuple[Decimal, int]]] = {}
        par_ecriture: dict[int, list[tuple[Decimal, int]]] = {}
        for (operation_id, ecriture_id), valeur in restants.items():
            par_operation.setdefault(operation_id, []).append((valeur.total, ecriture_id))
            par_ecriture.setdefault(ecriture_id, []).append((valeur.total, operation_id))

        meilleurs_operation = {
            cle: _meilleur_net(liste, grille) for cle, liste in par_operation.items()
        }
        meilleurs_ecriture = {
            cle: _meilleur_net(liste, grille) for cle, liste in par_ecriture.items()
        }
        retenues = [
            (operation_id, ecriture_id)
            for operation_id, ecriture_id in sorted(restants)
            if meilleurs_operation[operation_id] == ecriture_id
            and meilleurs_ecriture[ecriture_id] == operation_id
        ]
        if not retenues:
            # Ce qui garde un candidat n'a pas pu être proposé à cause d'une ambiguïté
            resultat.operations_ambigues = set(par_operation)
            resultat.ecritures_ambigues = set(par_ecriture)
            break
        for operation_id, ecriture_id in retenues:
            resultat.propositions.append(
                Proposition(operation_id, ecriture_id, restants[(operation_id, ecriture_id)])
            )
        utilisees_operation = {paire[0] for paire in retenues}
        utilisees_ecriture = {paire[1] for paire in retenues}
        restants = {
            paire: valeur
            for paire, valeur in restants.items()
            if paire[0] not in utilisees_operation and paire[1] not in utilisees_ecriture
        }

    resultat.propositions.sort(key=lambda item: (item.operation_id, item.ecriture_id))
    return resultat


def _paires_comparables(
    operations: Iterable[Operation], ecritures: Iterable[Ecriture], grille: Grille
) -> Iterable[tuple[Operation, Ecriture]]:
    """Paires qui passent le pré-filtre. Les écritures sont rangées par jour : chaque opération ne
    parcourt que les jours de sa fenêtre, jamais toutes les écritures."""
    par_jour: dict[date, list[Ecriture]] = {}
    for ecriture in ecritures:
        par_jour.setdefault(ecriture.date_ecriture, []).append(ecriture)
    for operation in operations:
        vues: set[int] = set()
        jours = {operation.date_operation}
        if operation.date_valeur:
            jours.add(operation.date_valeur)
        for jour in sorted(jours):
            for decalage in range(-grille.fenetre_jours, grille.fenetre_jours + 1):
                for ecriture in par_jour.get(jour + timedelta(days=decalage), ()):
                    if ecriture.id in vues:
                        continue
                    vues.add(ecriture.id)
                    if comparable(operation, ecriture, grille):
                        yield operation, ecriture


def _meilleur_net(candidats: list[tuple[Decimal, int]], grille: Grille) -> int | None:
    """Identifiant du meilleur candidat, ou None si le deuxième est trop proche (ambiguïté)."""
    classes = sorted(candidats, key=lambda item: (-item[0], item[1]))
    if len(classes) >= 2 and classes[0][0] - classes[1][0] < grille.ecart_ambiguite:
        return None
    return classes[0][1]
