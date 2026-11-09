"""Impayés Sage rapprochés avec l'écriture qu'ils annulent (décision du 09/11/2026).

Un chèque ou un effet remis (« EAR1° 0001006 HAJAR ISMAILI ») revient impayé : Sage passe une
écriture « IMP … » / « IMPAYE … » du même montant en sens opposé. Quand ni l'une ni l'autre n'a
trouvé d'opération de banque, le moteur propose de les rapprocher entre elles (correspondance
« E-E », sans opération) ; un humain valide, comme pour toute proposition.

Règles (fonctions pures, sans base) :
- l'impayé est une écriture de type « Impayé » datée dans la période du lancement ;
- l'origine est un « Chèque » ou un « Effet » du même compte bancaire (journal Sage), au montant
  exactement opposé, avec un n° commun (chèque, effet, pièce : `numeros`), datée le jour de
  l'impayé ou avant ;
- s'il y a plusieurs origines, la plus proche en date est proposée ; à égalité, rien ;
- une origine ne sert qu'une fois : si elle est la meilleure de deux impayés, aucun n'est proposé.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.services.reconciliation_scoring import Ecriture, numeros, type_ecriture

TYPE_IMPAYE = "Impayé"
TYPES_ORIGINE = frozenset({"Chèque", "Effet"})


@dataclass(frozen=True)
class PaireAnnulation:
    impaye_id: int
    origine_id: int
    # Jours entre l'origine et l'impayé (0 = même jour)
    ecart_jours: int


def _numeros(ecriture: Ecriture) -> set[str]:
    return numeros(ecriture.libelle, ecriture.reference, ecriture.numero_piece)


def origines_possibles(impaye: Ecriture, ecritures: Sequence[Ecriture]) -> list[Ecriture]:
    """Origines qui respectent toutes les règles face à cet impayé, de la plus proche à la plus
    ancienne."""
    if type_ecriture(impaye.libelle) != TYPE_IMPAYE or impaye.bank_account_id is None:
        return []
    numeros_impaye = _numeros(impaye)
    if not numeros_impaye:
        return []
    possibles = [
        ecriture
        for ecriture in ecritures
        if ecriture.id != impaye.id
        and ecriture.bank_account_id == impaye.bank_account_id
        and ecriture.montant == -impaye.montant
        and ecriture.date_ecriture <= impaye.date_ecriture
        and type_ecriture(ecriture.libelle) in TYPES_ORIGINE
        and _numeros(ecriture) & numeros_impaye
    ]
    return sorted(possibles, key=lambda e: (-e.date_ecriture.toordinal(), e.id))


def paires_annulation(
    ecritures: Sequence[Ecriture], *, du: date, au: date
) -> list[PaireAnnulation]:
    """Paires (impayé, origine) à proposer parmi des écritures libres, triées par impayé."""
    meilleures: dict[int, Ecriture] = {}
    impayes = {e.id: e for e in ecritures if du <= e.date_ecriture <= au}
    for impaye in impayes.values():
        possibles = origines_possibles(impaye, ecritures)
        if not possibles:
            continue
        # Deux origines du même jour : rien n'est proposé, un humain choisira
        if len(possibles) > 1 and possibles[1].date_ecriture == possibles[0].date_ecriture:
            continue
        meilleures[impaye.id] = possibles[0]

    par_origine: dict[int, list[int]] = {}
    for impaye_id, origine in meilleures.items():
        par_origine.setdefault(origine.id, []).append(impaye_id)
    paires = [
        PaireAnnulation(
            impaye_id=impaye_id,
            origine_id=origine.id,
            ecart_jours=(impayes[impaye_id].date_ecriture - origine.date_ecriture).days,
        )
        for impaye_id, origine in meilleures.items()
        if len(par_origine[origine.id]) == 1
    ]
    return sorted(paires, key=lambda p: p.impaye_id)
