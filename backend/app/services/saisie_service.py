"""Tableaux Devises et Prévisions de la page Position bancaire, saisis à la main (première version).

Règles :
- une grille par société et par date ; l'enregistrer remplace la grille de cette date ;
- une cellule vide n'est pas enregistrée, jamais remplacée par 0 ; rien n'est calculé (pas de TOTAL
  automatique) en attendant P9 (devises) et P14 (prévisions) ;
- seules les colonnes des banques actives se saisissent ; les valeurs d'une banque désactivée sont
  conservées telles quelles ;
- l'audit ne garde que les cellules réellement changées.
"""

from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import Bank, Company, SaisieDevise, SaisiePrevision, SaisiePrevisionJour
from app.repositories import account_repository, bank_repository, saisie_repository
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError

CENT = Decimal("0.01")
JOUR_FIELDS = {"encaissement": "Encaissement", "escompte": "Escompte", "douane": "Douane"}

# Cellule du tableau Devises : (ligne, colonne, banque). La banque n'existe que pour la colonne « Banque ».
DeviseCell = tuple[str, str, int | None]
# Cellule du bloc de 14 lignes des Prévisions : (ligne, banque). Sans banque, c'est le libellé.
PrevisionCell = tuple[int, int | None]


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
) -> None:
    """Aligne les cellules enregistrées sur la grille voulue : ajoute, corrige ou supprime."""
    keys = set(wanted) | {key for key in existing if editable(key)}
    for key in keys:
        row = existing.get(key)
        old = None if row is None else value_of(row)
        new = wanted.get(key)
        if old == new:
            continue
        avant[label(key)] = old
        apres[label(key)] = new
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


def list_previsions(
    db: Session, company_id: int, jour: date
) -> tuple[list[SaisiePrevision], SaisiePrevisionJour | None]:
    _company(db, company_id)
    return (
        saisie_repository.list_previsions(db, company_id, jour),
        saisie_repository.get_previsions_jour(db, company_id, jour),
    )


def save_previsions(
    db: Session,
    company_id: int,
    jour: date,
    cells: Mapping[PrevisionCell, str | Decimal | None],
    jour_values: Mapping[str, Decimal | None],
    *,
    acteur_id: int,
    ip: str | None = None,
) -> tuple[list[SaisiePrevision], SaisiePrevisionJour | None]:
    """`cells` : libellé (sans banque) ou montant par banque. `jour_values` : Encaissement, Escompte
    et Douane, les trois cellules fusionnées de la journée."""
    company = _company(db, company_id)
    banks = _active_banks(db, {bank_id for _, bank_id in cells if bank_id is not None})
    wanted: dict[PrevisionCell, str | Decimal] = {}
    for key, value in cells.items():
        clean = _text(value) if key[1] is None else _amount(value)
        if clean is not None:
            wanted[key] = clean
    existing = {
        (row.ligne, row.bank_id): row
        for row in saisie_repository.list_previsions(db, company.id, jour)
    }

    def value_of(row: SaisiePrevision) -> str | Decimal | None:
        return row.libelle if row.bank_id is None else row.montant

    def set_value(row: SaisiePrevision, value: str | Decimal) -> None:
        if row.bank_id is None:
            row.libelle = value
        else:
            row.montant = value
        row.saisi_par_id = acteur_id

    def build(key: PrevisionCell, value: str | Decimal) -> SaisiePrevision:
        ligne, bank_id = key
        return SaisiePrevision(
            company_id=company.id,
            jour=jour,
            ligne=ligne,
            bank_id=bank_id,
            libelle=value if bank_id is None else None,
            montant=value if bank_id is not None else None,
            saisi_par_id=acteur_id,
        )

    def label(key: PrevisionCell) -> str:
        ligne, bank_id = key
        return f"Ligne {ligne} · {banks[bank_id].code if bank_id is not None else 'libellé'}"

    avant: dict[str, Any] = {}
    apres: dict[str, Any] = {}
    _sync(
        db,
        existing,
        wanted,
        editable=lambda key: key[1] is None or key[1] in banks,
        value_of=value_of,
        set_value=set_value,
        build=build,
        label=label,
        avant=avant,
        apres=apres,
    )

    # Les trois cellules fusionnées de la journée : une ligne, supprimée quand elles sont vides
    day = saisie_repository.get_previsions_jour(db, company.id, jour)
    new_day = {field: _amount(jour_values.get(field)) for field in JOUR_FIELDS}
    day_changed = False
    for field, title in JOUR_FIELDS.items():
        old = None if day is None else getattr(day, field)
        if old != new_day[field]:
            avant[title] = old
            apres[title] = new_day[field]
            day_changed = True
    if day_changed:
        if all(value is None for value in new_day.values()):
            saisie_repository.delete(db, day)
        else:
            if day is None:
                day = SaisiePrevisionJour(company_id=company.id, jour=jour)
                saisie_repository.add(db, day)
            for field, value in new_day.items():
                setattr(day, field, value)
            day.saisi_par_id = acteur_id

    if apres:
        audit_service.log(
            db,
            user_id=acteur_id,
            action="saisie_previsions",
            entite="saisie_previsions",
            entite_id=company.id,
            avant={"jour": jour, **avant},
            apres={"jour": jour, **apres},
            ip=ip,
        )
        db.commit()
    return list_previsions(db, company.id, jour)
