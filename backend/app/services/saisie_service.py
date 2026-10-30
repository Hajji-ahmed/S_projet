"""Tableaux Devises et Prévisions de la page Position bancaire, saisis à la main (première version).

Règles :
- Devises : une grille par société et par date ; l'enregistrer remplace la grille de cette date ;
- Prévisions : chaque ligne a sa date (30/10/2026) ; l'écran montre et remplace les lignes datées
  du jour choisi ou plus tard ;
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
from typing import Any

from sqlalchemy.orm import Session

from app.models import Bank, Company, SaisieDevise, SaisiePrevision, SaisiePrevisionJour
from app.models.enums import LIGNES_PREVISIONS_PAR_DATE
from app.repositories import account_repository, bank_repository, saisie_repository
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError
from app.services.position_service import PREMIERE_DATE_SOLDE

CENT = Decimal("0.01")
JOUR_FIELDS = {"encaissement": "Encaissement", "escompte": "Escompte", "douane": "Douane"}

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


@dataclass(frozen=True)
class LignePrevision:
    """Une ligne envoyée par l'écran : sa date, son libellé, un montant par banque et Encaissement,
    Escompte, Douane (`montants`)."""

    jour: date
    libelle: str | None
    banques: Mapping[int, Decimal | None] = field(default_factory=dict)
    montants: Mapping[str, Decimal | None] = field(default_factory=dict)


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


def _numeroter(
    depuis: date, lignes: list[LignePrevision]
) -> tuple[dict[PrevisionCell, str | Decimal], dict[tuple[date, int], dict[str, Decimal | None]]]:
    """Cellules et montants sans banque voulus, par (date, rang). Une ligne entièrement vide est
    ignorée ; les autres sont numérotées dans l'ordre d'envoi, à partir de 1 pour chaque date."""
    cells: dict[PrevisionCell, str | Decimal] = {}
    days: dict[tuple[date, int], dict[str, Decimal | None]] = {}
    rangs: dict[date, int] = {}
    for item in lignes:
        if item.jour < depuis:
            raise ConflictError(
                f"Une ligne du {_date(item.jour)} est antérieure à la date affichée "
                f"({_date(depuis)})."
            )
        if item.jour < PREMIERE_DATE_SOLDE:
            raise ConflictError(f"Date invalide : {_date(item.jour)}.")
        libelle = _text(item.libelle)
        banques = {
            bank_id: _amount(value) for bank_id, value in item.banques.items() if value is not None
        }
        montants = {name: _amount(item.montants.get(name)) for name in JOUR_FIELDS}
        if libelle is None and not banques and all(v is None for v in montants.values()):
            continue
        rang = rangs.get(item.jour, 0) + 1
        if rang > LIGNES_PREVISIONS_PAR_DATE:
            raise ConflictError(
                f"Au plus {LIGNES_PREVISIONS_PAR_DATE} lignes par date ({_date(item.jour)})."
            )
        rangs[item.jour] = rang
        if libelle is not None:
            cells[(item.jour, rang, None)] = libelle
        for bank_id, montant in banques.items():
            cells[(item.jour, rang, bank_id)] = montant
        if any(v is not None for v in montants.values()):
            days[(item.jour, rang)] = montants
    return cells, days


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
    30/10/2026) : une ligne absente est supprimée, les lignes plus anciennes ne bougent pas."""
    company = _company(db, company_id)
    banks = _active_banks(db, {bank_id for item in lignes for bank_id in item.banques})
    wanted, wanted_days = _numeroter(depuis, lignes)
    existing = {
        (row.jour, row.ligne, row.bank_id): row
        for row in saisie_repository.list_previsions(db, company.id, depuis)
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
        jour, ligne, bank_id = key
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
    )

    # Encaissement, Escompte, Douane : un enregistrement par ligne, supprimé quand les trois sont vides
    days = {
        (row.jour, row.ligne): row
        for row in saisie_repository.list_previsions_jour(db, company.id, depuis)
    }
    for key in sorted(set(days) | set(wanted_days)):
        day = days.get(key)
        new_day = wanted_days.get(key, dict.fromkeys(JOUR_FIELDS))
        day_changed = False
        for name, title in JOUR_FIELDS.items():
            old = None if day is None else getattr(day, name)
            if old != new_day[name]:
                avant[_ligne_label(*key, title)] = old
                apres[_ligne_label(*key, title)] = new_day[name]
                day_changed = True
        if not day_changed:
            continue
        if all(value is None for value in new_day.values()):
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
