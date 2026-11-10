"""Tableaux Devises et Prévisions de la page Position bancaire, saisis à la main (première version).

Règles :
- Devises : une grille par société et par date ; l'enregistrer remplace la grille de cette date ;
- Prévisions : chaque ligne a sa date (30/10/2026) ; l'écran montre et remplace les lignes datées
  du jour choisi ou plus tard ; une ligne datée avant est ajoutée à sa date (09/11/2026) ;
- une cellule vide n'est pas enregistrée, jamais remplacée par 0 ; rien n'est calculé (pas de TOTAL
  automatique) en attendant P9 (devises) et P14 (prévisions) ;
- seules les colonnes des banques actives se saisissent ; les valeurs d'une banque désactivée sont
  conservées telles quelles ;
- l'audit ne garde que les cellules réellement changées.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, NamedTuple

from sqlalchemy.orm import Session

from app.models import Bank, Company, SaisieDevise, SaisiePrevision, SaisiePrevisionJour
from app.models.enums import LIGNES_PREVISIONS_PAR_DATE
from app.repositories import account_repository, bank_repository, saisie_repository
from app.services import audit_service, formule_service
from app.services.errors import ConflictError, NotFoundError
from app.services.position_service import PREMIERE_DATE_SOLDE

CENT = Decimal("0.01")
JOUR_FIELDS = {"encaissement": "Encaissement", "escompte": "Escompte", "douane": "Douane"}
# Colonnes de `saisies_previsions_jour` : les montants puis leurs formules (10/11/2026)
JOUR_COLUMNS = {
    **JOUR_FIELDS,
    **{f"formule_{name}": f"{title} (formule)" for name, title in JOUR_FIELDS.items()},
}

# Cellule du tableau Devises : (ligne, colonne, banque). La banque n'existe que pour la colonne « Banque ».
DeviseCell = tuple[str, str, int | None]
# Cellule du tableau Prévisions : (date de la ligne, rang dans la date, banque). Sans banque,
# c'est le libellé.
PrevisionCell = tuple[date, int, int | None]


def _amount(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(CENT)


def _text(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _company(db: Session, company_id: int) -> Company:
    company = account_repository.get_company(db, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    return company


def _active_banks(db: Session, bank_ids: set[int]) -> dict[int, Bank]:
    """Banques actives, après avoir vérifié que chaque banque demandée en fait partie."""
    banks = {bank.id: bank for bank in bank_repository.list_banks(db) if bank.actif}
    unknown = sorted(bank_ids - banks.keys())
    if unknown:
        raise ConflictError(f"Banque inconnue ou inactive : {unknown[0]}.")
    return banks


def _sync(
    db: Session,
    existing: Mapping[Any, Any],
    wanted: Mapping[Any, Any],
    *,
    editable: Callable[[Any], bool],
    value_of: Callable[[Any], Any],
    set_value: Callable[[Any, Any], None],
    build: Callable[[Any, Any], Any],
    label: Callable[[Any], str],
    avant: dict[str, Any],
    apres: dict[str, Any],
    shown: Callable[[Any], Any] = lambda value: value,
) -> None:
    """Aligne les cellules enregistrées sur la grille voulue : ajoute, corrige ou supprime.
    `shown` donne la valeur écrite dans l'audit."""
    keys = set(wanted) | {key for key in existing if editable(key)}
    for key in keys:
        row = existing.get(key)
        old = None if row is None else value_of(row)
        new = wanted.get(key)
        if old == new:
            continue
        avant[label(key)] = shown(old)
        apres[label(key)] = shown(new)
        if new is None:
            saisie_repository.delete(db, row)
        elif row is None:
            saisie_repository.add(db, build(key, new))
        else:
            set_value(row, new)


# --- Devises ---------------------------------------------------------------------------------------


def list_devises(db: Session, company_id: int, jour: date) -> list[SaisieDevise]:
    _company(db, company_id)
    return saisie_repository.list_devises(db, company_id, jour)


def save_devises(
    db: Session,
    company_id: int,
    jour: date,
    cells: Mapping[DeviseCell, Decimal | None],
    *,
    acteur_id: int,
    ip: str | None = None,
) -> list[SaisieDevise]:
    company = _company(db, company_id)
    banks = _active_banks(db, {bank_id for _, _, bank_id in cells if bank_id is not None})
    wanted = {key: _amount(value) for key, value in cells.items() if value is not None}
    existing = {
        (row.ligne, row.colonne, row.bank_id): row
        for row in saisie_repository.list_devises(db, company.id, jour)
    }

    def set_value(row: SaisieDevise, value: Decimal) -> None:
        row.montant = value
        row.saisi_par_id = acteur_id

    def build(key: DeviseCell, value: Decimal) -> SaisieDevise:
        ligne, colonne, bank_id = key
        return SaisieDevise(
            company_id=company.id,
            jour=jour,
            ligne=ligne,
            colonne=colonne,
            bank_id=bank_id,
            montant=value,
            saisi_par_id=acteur_id,
        )

    def label(key: DeviseCell) -> str:
        ligne, colonne, bank_id = key
        return f"{ligne} · {banks[bank_id].code if bank_id is not None else colonne}"

    avant: dict[str, Any] = {}
    apres: dict[str, Any] = {}
    _sync(
        db,
        existing,
        wanted,
        editable=lambda key: key[2] is None or key[2] in banks,
        value_of=lambda row: row.montant,
        set_value=set_value,
        build=build,
        label=label,
        avant=avant,
        apres=apres,
    )
    if apres:
        audit_service.log(
            db,
            user_id=acteur_id,
            action="saisie_devises",
            entite="saisie_devises",
            entite_id=company.id,
            avant={"jour": jour, **avant},
            apres={"jour": jour, **apres},
            ip=ip,
        )
        db.commit()
    return saisie_repository.list_devises(db, company.id, jour)


# --- Prévisions ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LignePrevision:
    """Une ligne envoyée par l'écran : sa date, son libellé, un montant par banque et Encaissement,
    Escompte, Douane (`montants`)."""

    jour: date
    libelle: str | None
    banques: Mapping[int, Decimal | None] = field(default_factory=dict)
    montants: Mapping[str, Decimal | None] = field(default_factory=dict)
    # Formule tapée dans une cellule de montant (10/11/2026), par banque ou par nom de colonne
    formules: Mapping[int | str, str | None] = field(default_factory=dict)


class MontantFormule(NamedTuple):
    """Montant d'une cellule Prévisions et la formule qui le donne, s'il y en a une."""

    montant: Decimal
    formule: str | None = None


def list_previsions(
    db: Session, company_id: int, depuis: date
) -> tuple[list[SaisiePrevision], list[SaisiePrevisionJour]]:
    """Les lignes dont la date est `depuis` ou plus tard (décision du 30/10/2026)."""
    _company(db, company_id)
    return (
        saisie_repository.list_previsions(db, company_id, depuis),
        saisie_repository.list_previsions_jour(db, company_id, depuis),
    )


def _date(jour: date) -> str:
    """JJ/MM/AAAA, l'année sur 4 chiffres même avant l'an 1000 (« 0026 » mal saisi)."""
    return f"{jour.day:02d}/{jour.month:02d}/{jour.year:04d}"


def _formule(formule: str | None, montant: Decimal | None, colonne: str, jour: date) -> str | None:
    """La formule sans espaces autour, après avoir vérifié qu'elle donne `montant` (409 sinon)."""
    texte = _text(formule)
    if texte is None:
        return None
    if montant is None or formule_service.evaluer(texte) != montant:
        raise ConflictError(
            f"Formule invalide ou différente du montant ({_date(jour)}, {colonne}) : {texte}"
        )
    return texte


def _numeroter(
    lignes: list[LignePrevision],
    rangs_existants: Mapping[date, int],
    codes: Mapping[int, str] | None = None,
) -> tuple[
    dict[PrevisionCell, str | MontantFormule],
    dict[tuple[date, int], dict[str, Decimal | str | None]],
]:
    """Cellules et montants sans banque voulus, par (date, rang). Une ligne entièrement vide est
    ignorée ; les autres sont numérotées dans l'ordre d'envoi, à partir de 1 pour chaque date, ou
    après `rangs_existants` (lignes d'une date antérieure à la page, ajoutées le 09/11/2026).
    Chaque formule doit donner son montant (`codes` nomme les banques dans le message d'erreur)."""
    cells: dict[PrevisionCell, str | MontantFormule] = {}
    days: dict[tuple[date, int], dict[str, Decimal | str | None]] = {}
    rangs: dict[date, int] = dict(rangs_existants)
    for item in lignes:
        if item.jour < PREMIERE_DATE_SOLDE:
            raise ConflictError(f"Date invalide : {_date(item.jour)}.")
        libelle = _text(item.libelle)
        banques = {
            bank_id: _amount(value) for bank_id, value in item.banques.items() if value is not None
        }
        montants = {name: _amount(item.montants.get(name)) for name in JOUR_FIELDS}
        if libelle is None and not banques and all(v is None for v in montants.values()):
            continue
        formules = {
            bank_id: _formule(
                item.formules.get(bank_id),
                montant,
                (codes or {}).get(bank_id, f"banque {bank_id}"),
                item.jour,
            )
            for bank_id, montant in banques.items()
        }
        colonnes: dict[str, Decimal | str | None] = dict(montants)
        for name, title in JOUR_FIELDS.items():
            colonnes[f"formule_{name}"] = _formule(
                item.formules.get(name), montants[name], title, item.jour
            )
        rang = rangs.get(item.jour, 0) + 1
        if rang > LIGNES_PREVISIONS_PAR_DATE:
            raise ConflictError(
                f"Au plus {LIGNES_PREVISIONS_PAR_DATE} lignes par date ({_date(item.jour)})."
            )
        rangs[item.jour] = rang
        if libelle is not None:
            cells[(item.jour, rang, None)] = libelle
        for bank_id, montant in banques.items():
            cells[(item.jour, rang, bank_id)] = MontantFormule(montant, formules[bank_id])
        if any(v is not None for v in montants.values()):
            days[(item.jour, rang)] = colonnes
    return cells, days


def _montant_audite(value: Any) -> Any:
    """Dans l'audit, un montant sans formule reste un montant (comme avant le 10/11/2026)."""
    if isinstance(value, MontantFormule):
        return value.montant if value.formule is None else value._asdict()
    return value


def _ligne_label(jour: date, ligne: int, colonne: str) -> str:
    return f"{_date(jour)} · Ligne {ligne} · {colonne}"


def save_previsions(
    db: Session,
    company_id: int,
    depuis: date,
    lignes: list[LignePrevision],
    *,
    acteur_id: int,
    ip: str | None = None,
) -> tuple[list[SaisiePrevision], list[SaisiePrevisionJour]]:
    """Remplace toutes les lignes datées `depuis` ou plus tard par `lignes` (décision du
    30/10/2026) : une ligne absente est supprimée, les lignes plus anciennes ne bougent pas.
    Une ligne datée avant `depuis` est ajoutée à la suite des lignes déjà enregistrées à sa date
    (décision du 09/11/2026) : rien n'est remplacé ni supprimé avant `depuis`."""
    company = _company(db, company_id)
    banks = _active_banks(db, {bank_id for item in lignes for bank_id in item.banques})
    passees = {item.jour for item in lignes if PREMIERE_DATE_SOLDE <= item.jour < depuis}
    wanted, wanted_days = _numeroter(
        lignes,
        saisie_repository.dernier_rang_previsions(db, company.id, passees),
        {bank_id: bank.code for bank_id, bank in banks.items()},
    )
    existing = {
        (row.jour, row.ligne, row.bank_id): row
        for row in saisie_repository.list_previsions(db, company.id, depuis)
    }

    def value_of(row: SaisiePrevision) -> str | MontantFormule | None:
        if row.bank_id is None:
            return row.libelle
        return None if row.montant is None else MontantFormule(row.montant, row.formule)

    def set_value(row: SaisiePrevision, value: str | MontantFormule) -> None:
        if isinstance(value, MontantFormule):
            row.montant, row.formule = value
        else:
            row.libelle = value
        row.saisi_par_id = acteur_id

    def build(key: PrevisionCell, value: str | MontantFormule) -> SaisiePrevision:
        jour, ligne, bank_id = key
        montant = value if isinstance(value, MontantFormule) else None
        return SaisiePrevision(
            company_id=company.id,
            jour=jour,
            ligne=ligne,
            bank_id=bank_id,
            libelle=value if isinstance(value, str) else None,
            montant=montant.montant if montant else None,
            formule=montant.formule if montant else None,
            saisi_par_id=acteur_id,
        )

    def label(key: PrevisionCell) -> str:
        jour, ligne, bank_id = key
        return _ligne_label(jour, ligne, banks[bank_id].code if bank_id is not None else "libellé")

    avant: dict[str, Any] = {}
    apres: dict[str, Any] = {}
    _sync(
        db,
        existing,
        wanted,
        editable=lambda key: key[2] is None or key[2] in banks,
        value_of=value_of,
        set_value=set_value,
        build=build,
        label=label,
        avant=avant,
        apres=apres,
        shown=_montant_audite,
    )

    # Encaissement, Escompte, Douane : un enregistrement par ligne, supprimé quand les trois sont vides
    days = {
        (row.jour, row.ligne): row
        for row in saisie_repository.list_previsions_jour(db, company.id, depuis)
    }
    for key in sorted(set(days) | set(wanted_days)):
        day = days.get(key)
        new_day = wanted_days.get(key, dict.fromkeys(JOUR_COLUMNS))
        day_changed = False
        for name, title in JOUR_COLUMNS.items():
            old = None if day is None else getattr(day, name)
            if old != new_day[name]:
                avant[_ligne_label(*key, title)] = old
                apres[_ligne_label(*key, title)] = new_day[name]
                day_changed = True
        if not day_changed:
            continue
        if all(new_day[name] is None for name in JOUR_FIELDS):
            saisie_repository.delete(db, day)
            continue
        if day is None:
            day = SaisiePrevisionJour(company_id=company.id, jour=key[0], ligne=key[1])
            saisie_repository.add(db, day)
        for name, value in new_day.items():
            setattr(day, name, value)
        day.saisi_par_id = acteur_id

    if apres:
        audit_service.log(
            db,
            user_id=acteur_id,
            action="saisie_previsions",
            entite="saisie_previsions",
            entite_id=company.id,
            avant={"a_partir_du": depuis, **avant},
            apres={"a_partir_du": depuis, **apres},
            ip=ip,
        )
        db.commit()
    return list_previsions(db, company.id, depuis)
