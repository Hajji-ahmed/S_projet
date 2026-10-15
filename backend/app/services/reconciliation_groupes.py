"""Rapprochement groupé N → 1 (décision du 12/10/2026) : règles pures, sans base de données.

Plusieurs opérations bancaires pour une seule écriture Sage, quand leur somme vaut exactement
l'opposé du montant de l'écriture (un crédit banque est un débit Sage). Depuis le 15/10/2026, un
seul cas : une opération principale + une commission + sa TVA (10 %) du même jour
(12 450 − 175 − 17,50 = 12 257,50). Les autres frais se comptabilisent dans SIMTIS ; tout autre
regroupement se fait à la main.

Le moteur ne fait que proposer : un humain valide chaque groupe. Prudence : aucun groupe pour une
écriture qui a deux groupes différents possibles (sauf lignes indiscernables, mêmes libellés et
montants), et une opération n'entre que dans un groupe.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from itertools import combinations

from app.services.reconciliation_scoring import (
    CENT,
    TYPES_PAR_ECHEANCE,
    ZERO,
    Ecriture,
    Grille,
    Operation,
    Score,
    _plain,
    _points,
    date_comparee,
    ecart_jours,
    numeros,
    ratio_date,
    ratio_libelle,
    type_ecriture,
    type_operation,
)

# Au plus 6 opérations dans un groupe cherché par combinaisons ; les totaux d'une famille de frais
# du jour (tous les timbres du jour) ne sont pas limités
MAX_LIGNES = 6
# Taille des combinaisons de frais d'un jour : paires sur tous les frais, triplets sur les 20 premiers
MAX_FRAIS_TRIPLETS = 20

# Début du libellé (normalisé) d'un frais bancaire, et sa famille pour les totaux du jour
FAMILLES_FRAIS: tuple[tuple[str, str], ...] = (
    ("DROITS DE TIMBRE", "timbre"),
    ("DROIT DE TIMBRE", "timbre"),
    ("COMMISSION", "commission"),
    ("COM ", "commission"),
    ("TAXE SUR VALEUR AJOUTEE", "tva"),
    ("TVA", "tva"),
    ("INTERET", "interet"),
    ("AGIOS", "interet"),
    ("FRAIS", "frais"),
)


@lru_cache(maxsize=20_000)
def famille_frais(libelle: str | None) -> str | None:
    """Famille d'un frais bancaire (timbre, commission, tva, interet, frais), sinon None."""
    texte = _plain(libelle) + " "
    for prefixe, famille in FAMILLES_FRAIS:
        if texte.startswith(prefixe):
            return famille
    return None


@dataclass(frozen=True)
class Groupe:
    ecriture_id: int
    operation_ids: tuple[int, ...]
    principale_id: int
    score: Score
    explication: str


@dataclass
class ResultatGroupes:
    groupes: list[Groupe] = field(default_factory=list)
    # Écritures qui ont plusieurs groupes possibles : jamais proposées, à trancher à la main
    ecritures_ambigues: set[int] = field(default_factory=set)


def _montant_texte(value: Decimal) -> str:
    entier, decimales = f"{abs(value):.2f}".split(".")
    return f"{'-' if value < 0 else ''}{int(entier):,}".replace(",", " ") + f",{decimales}"


def _signature(ops: Sequence[Operation]) -> tuple:
    """Lignes indiscernables : mêmes libellés et mêmes montants, quel que soit leur identifiant."""
    return tuple(sorted((_plain(op.libelle), op.montant) for op in ops))


def score_groupe(ops: Sequence[Operation], ecriture: Ecriture, grille: Grille) -> Score:
    """Montant exact (toujours, sinon pas de groupe) + n° commun + date (écart le plus grand) +
    libellé de l'opération principale (la plus grosse), plafonné à 100."""
    principale = max(ops, key=lambda op: abs(op.montant))
    commun = any(numeros(op.libelle, op.reference) for op in ops) and bool(
        set().union(*(numeros(op.libelle, op.reference) for op in ops))
        & numeros(ecriture.libelle, ecriture.reference, ecriture.numero_piece)
    )
    ecart = max(ecart_jours(op, ecriture) for op in ops)
    detail = {
        "reference": grille.reference if commun else ZERO,
        "montant": grille.montant,
        "date": _points(grille.date, ratio_date(ecart, grille.tolerance_jours)),
        "libelle": _points(grille.libelle, ratio_libelle(principale, ecriture)),
        "tiers": ZERO,
    }
    detail = {code: value.quantize(CENT) for code, value in detail.items()}
    total = min(sum(detail.values(), ZERO), Decimal("100.00")).quantize(CENT)
    return Score(total=total, detail=detail)


def explication(ops: Sequence[Operation], ecriture: Ecriture) -> str:
    """« ENCAISSEMENT CHEQUE N 1550018 10 000,00 + COMMISSION 50,00 = 10 050,00 · n° 1550018 »."""
    lignes = sorted(ops, key=lambda op: -abs(op.montant))
    parties = " + ".join(f"{op.libelle[:40]} {_montant_texte(abs(op.montant))}" for op in lignes)
    total = sum((op.montant for op in ops), ZERO)
    texte = f"{parties} = {_montant_texte(abs(total))}"
    communs = set().union(*(numeros(op.libelle, op.reference) for op in ops)) & numeros(
        ecriture.libelle, ecriture.reference, ecriture.numero_piece
    )
    if communs:
        texte += f" · n° {', '.join(sorted(communs))} commun"
    ecart = max(ecart_jours(op, ecriture) for op in ops)
    texte += " · même jour" if ecart == 0 else f" · jusqu'à {ecart} j d'écart"
    return texte


def _candidats_ecriture(
    ecriture: Ecriture,
    par_compte_jour: dict[tuple[int | None, date], list[Operation]],
    grille: Grille,
) -> list[Operation]:
    """Opérations libres du même compte, de date comparable à l'écriture (règles du type).

    L'écart est celui de `ecart_jours`, calculé ici sans appel par opération (15/10/2026)."""
    jour = ecriture.echeance or ecriture.date_ecriture
    jours = {ecriture.date_ecriture, jour}
    jour_sage = date_comparee(ecriture)
    avec_valeur = type_ecriture(ecriture.libelle) in TYPES_PAR_ECHEANCE
    fenetre = grille.fenetre_jours
    vues: dict[int, Operation] = {}
    for base in jours:
        for decalage in range(-fenetre, fenetre + 1):
            for op in par_compte_jour.get(
                (ecriture.bank_account_id, base + timedelta(decalage)), ()
            ):
                if op.id in vues:
                    continue
                ecart = abs((op.date_operation - jour_sage).days)
                if avec_valeur and op.date_valeur:
                    ecart = min(ecart, abs((op.date_valeur - jour_sage).days))
                if ecart <= fenetre:
                    vues[op.id] = op
    return list(vues.values())


class _SommesDuJour:
    """Sommes des combinaisons de 1 à 3 frais d'un même compte et d'un même jour, calculées une
    fois par jour : une écriture ou une opération principale y cherche son complément d'un coup."""

    def __init__(self, par_compte_jour: dict[tuple[int | None, date], list[Operation]]):
        self._jours = par_compte_jour
        self._cache: dict[tuple[int | None, date], dict[Decimal, list[tuple[Operation, ...]]]] = {}
        self._frais: dict[tuple[int | None, date], list[Operation]] = {}

    def frais(self, cle: tuple[int | None, date]) -> list[Operation]:
        if cle not in self._frais:
            self._frais[cle] = [op for op in self._jours.get(cle, []) if famille_frais(op.libelle)]
        return self._frais[cle]

    def sommes(self, cle: tuple[int | None, date]) -> dict[Decimal, list[tuple[Operation, ...]]]:
        if cle not in self._cache:
            frais = self.frais(cle)
            table: dict[Decimal, list[tuple[Operation, ...]]] = {}
            for taille in (1, 2, 3):
                pool = frais if taille < 3 else frais[:MAX_FRAIS_TRIPLETS]
                for combo in combinations(pool, taille):
                    table.setdefault(sum((op.montant for op in combo), ZERO), []).append(combo)
            self._cache[cle] = table
        return self._cache[cle]


@lru_cache(maxsize=200_000)
def _numeros_operation(libelle: str | None, reference: str | None) -> frozenset[str]:
    return frozenset(numeros(libelle, reference))


@lru_cache(maxsize=200_000)
def _principale_possible(libelle: str | None) -> tuple[bool, str | None]:
    """(frais ?, type) d'une opération, calculés une fois par libellé (15/10/2026)."""
    return bool(famille_frais(libelle)), type_operation(libelle)


# Taux de TVA d'une commission bancaire, et tolérance d'arrondi (15/10/2026)
TAUX_TVA_COMMISSION = Decimal("0.10")
TOLERANCE_TVA = Decimal("0.01")


def tva_de_la_commission(commission: Decimal, tva: Decimal) -> bool:
    """La TVA vaut 10 % de la commission, au centime près (50,00 → 5,00)."""
    attendue = (abs(commission) * TAUX_TVA_COMMISSION).quantize(CENT, rounding=ROUND_HALF_UP)
    return abs(abs(tva) - attendue) <= TOLERANCE_TVA


def _groupes_possibles(
    ecriture: Ecriture,
    candidats: list[Operation],
    sommes: _SommesDuJour,
    frais_ids: frozenset[int] | set[int] = frozenset(),
    grille: Grille | None = None,
) -> list[tuple[Operation, ...]]:
    """Groupes possibles pour l'écriture (décision du 15/10/2026) : **exactement** une opération
    principale (qui n'est pas un frais), une commission et sa TVA (10 % de la commission, au
    centime près), du même compte et du même jour que la principale, dont la somme vaut l'opposé
    de l'écriture. Rien d'autre n'est regroupé automatiquement (frais seuls, deux commissions,
    timbres, n° commun…) : un cas différent se rapproche à la main. `frais_ids` : opérations
    reconnues comme frais par la règle de « À comptabiliser »."""
    cible = -ecriture.montant
    compte = ecriture.bank_account_id
    fenetre = grille.fenetre_jours if grille is not None else None
    type_sage = type_ecriture(ecriture.libelle)
    trouves: dict[frozenset[int], tuple[Operation, ...]] = {}
    for principale in candidats:
        frais, type_op = _principale_possible(principale.libelle)
        # `types_compatibles` sans appel par opération : deux types connus doivent être égaux
        if (
            frais
            or principale.id in frais_ids
            or (type_op is not None and type_sage is not None and type_op != type_sage)
        ):
            continue
        reste = cible - principale.montant
        if reste == 0:
            continue
        du_jour = sommes.frais((compte, principale.date_operation))
        commissions = [op for op in du_jour if famille_frais(op.libelle) == "commission"]
        tvas = [op for op in du_jour if famille_frais(op.libelle) == "tva"]
        for commission in commissions:
            for tva in tvas:
                if commission.montant + tva.montant != reste:
                    continue
                if not tva_de_la_commission(commission.montant, tva.montant):
                    continue
                ops = (principale, commission, tva)
                if fenetre is not None and max(ecart_jours(op, ecriture) for op in ops) > fenetre:
                    continue
                trouves.setdefault(frozenset(op.id for op in ops), ops)
    return list(trouves.values())


def grouper(
    operations: Iterable[Operation],
    ecritures: Iterable[Ecriture],
    grille: Grille,
    paires_rejetees: frozenset[tuple[int, int]] | set[tuple[int, int]] = frozenset(),
    frais_ids: frozenset[int] | set[int] = frozenset(),
) -> ResultatGroupes:
    """Propositions N → 1 sur des opérations et écritures libres (le 1 → 1 a déjà été fait) :
    une opération principale et ses frais (15/10/2026 : jamais de frais seuls)."""
    operations = list(operations)
    par_compte_jour: dict[tuple[int | None, date], list[Operation]] = {}
    for op in operations:
        par_compte_jour.setdefault((op.bank_account_id, op.date_operation), []).append(op)

    sommes = _SommesDuJour(par_compte_jour)
    resultat = ResultatGroupes()
    meilleurs: list[tuple[Decimal, Ecriture, tuple[Operation, ...]]] = []
    for ecriture in ecritures:
        if ecriture.montant == 0:
            continue
        candidats = _candidats_ecriture(ecriture, par_compte_jour, grille)
        possibles = [
            ops
            for ops in _groupes_possibles(ecriture, candidats, sommes, frais_ids, grille)
            if not any((op.id, ecriture.id) in paires_rejetees for op in ops)
        ]
        if not possibles:
            continue
        notes = sorted(
            ((score_groupe(ops, ecriture, grille).total, ops) for ops in possibles),
            key=lambda item: (-item[0], sorted(op.id for op in item[1])),
        )
        meilleur, ops = notes[0]
        if meilleur < grille.seuil_proposition:
            continue
        # Un autre groupe à moins de `ecart_ambiguite` points : ambiguïté (prudence, il s'agit de
        # regrouper de l'argent), sauf lignes indiscernables (mêmes libellés et montants)
        rivaux = [o for s, o in notes[1:] if meilleur - s < grille.ecart_ambiguite]
        if any(_signature(o) != _signature(ops) for o in rivaux):
            resultat.ecritures_ambigues.add(ecriture.id)
            continue
        meilleurs.append((meilleur, ecriture, ops))

    # Une opération n'entre que dans un groupe : les meilleurs scores d'abord
    utilisees: set[int] = set()
    for _total, ecriture, ops in sorted(meilleurs, key=lambda item: (-item[0], item[1].id)):
        if any(op.id in utilisees for op in ops):
            continue
        utilisees.update(op.id for op in ops)
        principale = max(ops, key=lambda op: abs(op.montant))
        resultat.groupes.append(
            Groupe(
                ecriture_id=ecriture.id,
                operation_ids=tuple(sorted(op.id for op in ops)),
                principale_id=principale.id,
                score=score_groupe(ops, ecriture, grille),
                explication=explication(ops, ecriture),
            )
        )
    return resultat


# Écriture Sage de frais du jour : familles de frais qu'elle peut contenir (13/10/2026). Un droit
# de timbre n'est jamais dans une « COM » : sans cette règle, 1 + 20 + 1 = 22 le rattacherait à tort.
FAMILLES_PAR_ECRITURE = (
    ("DT D ENREGISTREMENT", {"timbre"}),
    ("DT D'ENREGISTREMENT", {"timbre"}),
    ("FRAIS D ESCOMPTE", {"interet", "tva"}),
    ("FRAIS D'ESCOMPTE", {"interet", "tva"}),
    ("COM", {"commission", "tva"}),
    # Frais à TVA comprise (14/10/2026) : commissions RTGS, prélèvement, tenue, frais récupérés
    ("FRAIS", {"frais", "tva", "timbre"}),
)


def _familles_admises(ecriture: Ecriture) -> set[str] | None:
    texte = _plain(ecriture.libelle)
    for prefixe, familles in FAMILLES_PAR_ECRITURE:
        if texte == prefixe or texte.startswith(prefixe + " ") or texte.startswith(prefixe + "/"):
            return familles
    return None


def operations_couvertes(
    operations: Iterable[Operation],
    ecritures: Iterable[Ecriture],
    grille: Grille,
    paires_rejetees: frozenset[tuple[int, int]] | set[tuple[int, int]] = frozenset(),
    ecart_seul: int = 3,
    cibles: set[int] | None = None,
) -> dict[int, int]:
    """Opérations libres qu'une écriture libre pourrait couvrir : {opération : écriture}.

    Sert à ne jamais comptabiliser dans SIMTIS un frais déjà inclus dans une écriture Sage
    (13/10/2026). Depuis le 15/10/2026, les frais se comptabilisent dans SIMTIS : seul le groupe
    d'une opération principale avec ses frais (10 000 + commission 50 + TVA 10 = 10 060), même
    ambigu, couvre un frais. Les frais à contrôler (`cibles`) ne sont jamais l'opération
    principale. Une paire rejetée par un utilisateur ne couvre rien. `ecart_seul` n'est plus
    utilisé (un frais seul face à une écriture n'est plus couvert)."""
    operations = list(operations)
    par_compte_jour: dict[tuple[int | None, date], list[Operation]] = {}
    for op in operations:
        par_compte_jour.setdefault((op.bank_account_id, op.date_operation), []).append(op)
    sommes = _SommesDuJour(par_compte_jour)
    couvertes: dict[int, int] = {}
    for ecriture in ecritures:
        if ecriture.montant == 0:
            continue
        candidats = _candidats_ecriture(ecriture, par_compte_jour, grille)
        # Écriture sans aucune opération à contrôler parmi ses candidates : rien à chercher
        if cibles is not None and not any(op.id in cibles for op in candidats):
            continue
        for ops in _groupes_possibles(ecriture, candidats, sommes, cibles or frozenset(), grille):
            if any((op.id, ecriture.id) in paires_rejetees for op in ops):
                continue
            for op in ops:
                couvertes.setdefault(op.id, ecriture.id)
    return couvertes


# --- Ensemble choisi à la main (P13, 15/10/2026) --------------------------------------------------


def type_ensemble(nb_operations: int, nb_ecritures: int) -> str:
    """« 1-1 », « 1-N » (une opération, plusieurs écritures), « N-1 » ou « N-N »."""
    return f"{'N' if nb_operations > 1 else '1'}-{'N' if nb_ecritures > 1 else '1'}"


def score_ensemble(
    ops: Sequence[Operation], ecritures: Sequence[Ecriture], grille: Grille
) -> Score:
    """Score indicatif d'un rapprochement manuel de plusieurs lignes (toujours équilibré) :
    montant + n° commun entre les deux côtés + date (pour chaque opération, l'écriture la plus
    proche ; le plus grand de ces écarts) + libellé des deux plus grosses lignes, plafonné à 100."""
    principale = max(ops, key=lambda op: abs(op.montant))
    plus_grosse = max(ecritures, key=lambda e: abs(e.montant))
    cote_banque = set().union(*(numeros(op.libelle, op.reference) for op in ops))
    cote_sage = set().union(*(numeros(e.libelle, e.reference, e.numero_piece) for e in ecritures))
    ecart = max(min(ecart_jours(op, e) for e in ecritures) for op in ops)
    detail = {
        "reference": grille.reference if cote_banque & cote_sage else ZERO,
        "montant": grille.montant,
        "date": _points(grille.date, ratio_date(ecart, grille.tolerance_jours)),
        "libelle": _points(grille.libelle, ratio_libelle(principale, plus_grosse)),
        "tiers": ZERO,
    }
    detail = {code: value.quantize(CENT) for code, value in detail.items()}
    total = min(sum(detail.values(), ZERO), Decimal("100.00")).quantize(CENT)
    return Score(total=total, detail=detail)


def explication_ensemble(ops: Sequence[Operation], ecritures: Sequence[Ecriture]) -> str:
    """« 2 opérations = 12 000,00 ↔ 3 écritures = 12 000,00 · n° 173813 commun »."""
    total_ops = sum((op.montant for op in ops), ZERO)
    total_ecr = sum((e.montant for e in ecritures), ZERO)

    def cote(n: int, mot: str, total: Decimal) -> str:
        return f"{n} {mot}{'s' if n > 1 else ''} = {_montant_texte(abs(total))}"

    texte = (
        f"{cote(len(ops), 'opération', total_ops)} ↔ {cote(len(ecritures), 'écriture', total_ecr)}"
    )
    communs = set().union(*(numeros(op.libelle, op.reference) for op in ops)) & set().union(
        *(numeros(e.libelle, e.reference, e.numero_piece) for e in ecritures)
    )
    if communs:
        texte += f" · n° {', '.join(sorted(communs))} commun"
    return texte + " · choisi à la main"
