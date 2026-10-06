"""Écarts (P12) : création manuelle ou automatique, cycle de vie, clôture, lectures.

Cycle : À traiter → En cours → Traité → Clôturé (Traité peut revenir à En cours ; on clôture depuis
tout statut ouvert, avec un commentaire obligatoire ; un écart clôturé est définitif).

Effet sur les lignes : tant que l'écart est ouvert, son opération et son écriture sont « Écart » (le
moteur de rapprochement les ignore) ; à la clôture elles redeviennent « Non rapprochée » et peuvent
de nouveau être rapprochées. Une ligne qui a déjà eu un écart n'en reçoit jamais un automatiquement.
"""

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import PermissionCode
from app.models import AccountingEntry, BankTransaction, Company, Discrepancy, User, enums
from app.repositories import discrepancy_repository as repo
from app.repositories import reconciliation_repository
from app.services import audit_service, reconciliation_service
from app.services.errors import ConflictError, NotFoundError
from app.services.position_service import business_today

PAGE_SIZE = 50
PERIODE_MAX_JOURS = 366
COMMENTAIRE_MAX = 1000
ENTITE = "discrepancy"
CONCURRENT = "Cet écart vient d'être modifié par un autre utilisateur : rechargez la page."

# Lignes de chaque type : (opération, écriture) ; True = obligatoire, False = interdite,
# None = facultative. « Doublon potentiel » porte sur une seule ligne, l'une ou l'autre.
LIGNES_PAR_TYPE: dict[str, tuple[bool | None, bool | None]] = {
    "Banque sans écriture": (True, False),
    "Écriture sans banque": (False, True),
    "Montant différent": (True, True),
    "Date différente": (True, True),
    "Libellé ambigu": (True, None),
    "Doublon potentiel": (None, None),
}
assert set(LIGNES_PAR_TYPE) == set(enums.TYPES_ECART)

# Transitions autorisées par PATCH (la clôture a sa propre route)
TRANSITIONS = {
    "À traiter": {"En cours"},
    "En cours": {"Traité"},
    "Traité": {"En cours"},
}


def _company(db: Session, company_id: int, *, lock: bool = False) -> Company:
    company = (
        reconciliation_repository.lock_company(db, company_id)
        if lock
        else db.get(Company, company_id)
    )
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    return company


def _clean(text: str | None) -> str | None:
    cleaned = " ".join(text.split()) if text else ""
    if len(cleaned) > COMMENTAIRE_MAX:
        raise ConflictError(f"Le commentaire ne peut pas dépasser {COMMENTAIRE_MAX} caractères.")
    return cleaned or None


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:  # un écart ouvert créé en même temps sur la même ligne
        db.rollback()
        raise ConflictError(CONCURRENT) from error


def _snapshot(ecart: Discrepancy) -> dict:
    return {
        "type": ecart.type,
        "statut": ecart.statut,
        "operation": ecart.bank_transaction_id,
        "ecriture": ecart.accounting_entry_id,
        "montant": ecart.montant,
        "difference": ecart.difference,
        "date_ecart": ecart.date_ecart,
        "responsable_id": ecart.responsable_id,
        "commentaire": ecart.commentaire,
    }


def _set_lines_status(
    db: Session, tx_id: int | None, entry_id: int | None, statut: str, *, seulement: str | None
) -> None:
    """Statut des lignes de l'écart ; `seulement` : ne change qu'une ligne qui a ce statut."""
    if tx_id is not None:
        tx = db.get(BankTransaction, tx_id)
        if tx is not None and (seulement is None or tx.statut == seulement):
            tx.statut = statut
    if entry_id is not None:
        entry = db.get(AccountingEntry, entry_id)
        if entry is not None and (seulement is None or entry.statut == seulement):
            entry.statut = statut


def _check_responsable(db: Session, responsable_id: int | None) -> None:
    if responsable_id is None:
        return
    allowed = {user.id for user in repo.responsables(db, PermissionCode.DISCREPANCIES_MANAGE.value)}
    if responsable_id not in allowed:
        raise ConflictError(
            "Le responsable doit être un utilisateur actif autorisé à traiter les écarts."
        )


def _new(
    *,
    company_id: int,
    type_ecart: str,
    tx: BankTransaction | None,
    entry: AccountingEntry | None,
    commentaire: str | None = None,
    responsable_id: int | None = None,
) -> Discrepancy:
    """Écart construit à partir de ses lignes : montant = valeur absolue du montant de la ligne
    (de l'opération s'il y en a une) ; différence = opération + écriture, quand il y a les deux."""
    ligne = tx if tx is not None else entry
    assert ligne is not None
    return Discrepancy(
        company_id=company_id,
        type=type_ecart,
        bank_transaction_id=tx.id if tx else None,
        accounting_entry_id=entry.id if entry else None,
        montant=abs(ligne.montant),
        difference=(tx.montant + entry.montant) if tx and entry else None,
        date_ecart=tx.date_operation if tx else entry.date_ecriture,
        statut="À traiter",
        responsable_id=responsable_id,
        commentaire=commentaire,
    )


# --- Création manuelle ----------------------------------------------------------------------------


def create(
    db: Session,
    *,
    type_ecart: str,
    transaction_id: int | None,
    entry_id: int | None,
    commentaire: str | None,
    responsable_id: int | None,
    acteur_id: int,
    ip: str | None,
) -> Discrepancy:
    """Signale un écart sur une opération et / ou une écriture."""
    operation_requise, ecriture_requise = LIGNES_PAR_TYPE[type_ecart]
    if type_ecart == "Doublon potentiel":
        if (transaction_id is None) == (entry_id is None):
            raise ConflictError(
                "Un doublon potentiel porte sur une seule ligne : une opération ou une écriture."
            )
    else:
        if operation_requise and transaction_id is None:
            raise ConflictError(f"Un écart « {type_ecart} » exige une opération bancaire.")
        if ecriture_requise and entry_id is None:
            raise ConflictError(f"Un écart « {type_ecart} » exige une écriture comptable.")
        if operation_requise is False and transaction_id is not None:
            raise ConflictError(f"Un écart « {type_ecart} » ne porte pas sur une opération.")
        if ecriture_requise is False and entry_id is not None:
            raise ConflictError(f"Un écart « {type_ecart} » ne porte pas sur une écriture.")

    tx = account = entry = None
    if transaction_id is not None:
        found = reconciliation_repository.get_transaction(db, transaction_id)
        if found is None:
            raise NotFoundError("Opération bancaire introuvable.")
        tx, account = found
    if entry_id is not None:
        entry = reconciliation_repository.get_entry(db, entry_id)
        if entry is None:
            raise NotFoundError("Écriture comptable introuvable.")
    company_id = account.company_id if account is not None else entry.company_id
    company = _company(db, company_id, lock=True)
    for row in (tx, entry):
        if row is not None:
            db.refresh(row)

    if tx is not None and entry is not None:
        if entry.company_id != company.id:
            raise ConflictError(
                "L'opération et l'écriture appartiennent à deux sociétés différentes."
            )
        if entry.bank_account_id != tx.bank_account_id:
            raise ConflictError(
                "L'écriture n'est pas passée dans le journal Sage de ce compte bancaire."
            )
        if type_ecart == "Montant différent" and tx.montant + entry.montant == 0:
            raise ConflictError(
                "Les montants s'équilibrent (crédit en banque = débit dans Sage) : "
                "ce n'est pas un écart de montant."
            )
    for row, quoi in ((tx, "L'opération"), (entry, "L'écriture")):
        if row is None:
            continue
        ouvert = repo.open_discrepancy_of(
            db,
            transaction_id=row.id if row is tx else None,
            entry_id=row.id if row is entry else None,
        )
        if ouvert is not None:
            raise ConflictError(f"{quoi} a déjà un écart ouvert (n° {ouvert.id}).")
    texte = _clean(commentaire)
    _check_responsable(db, responsable_id)

    # Une proposition en attente sur ces lignes n'a plus lieu d'être ; un rapprochement validé
    # doit être annulé d'abord (409)
    remplacees = reconciliation_service.release_pending_matches(
        db,
        transaction_id=tx.id if tx else None,
        entry_id=entry.id if entry else None,
        motif=f"Remplacée par un écart « {type_ecart} ».",
        acteur_id=acteur_id,
        ip=ip,
    )
    ecart = _new(
        company_id=company.id,
        type_ecart=type_ecart,
        tx=tx,
        entry=entry,
        commentaire=texte,
        responsable_id=responsable_id,
    )
    repo.add(db, ecart)
    db.flush()
    _set_lines_status(
        db, ecart.bank_transaction_id, ecart.accounting_entry_id, "Écart", seulement=None
    )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="creation_ecart",
        entite=ENTITE,
        entite_id=ecart.id,
        apres={**_snapshot(ecart), "origine": "Manuelle", "propositions_rejetees": remplacees},
        ip=ip,
    )
    _commit(db)
    return ecart


# --- Génération automatique -----------------------------------------------------------------------


@dataclass
class GenerationResult:
    banque_sans_ecriture: int
    ecriture_sans_banque: int
    doublons: int
    date_limite: date

    @property
    def total(self) -> int:
        return self.banque_sans_ecriture + self.ecriture_sans_banque + self.doublons


def _plain(text: str | None) -> str:
    if not text:
        return ""
    raw = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in raw if not unicodedata.combining(c)).upper().split())


ELIGIBLES_DOUBLON = ("Non rapprochée", "À vérifier")


def _duplicates(rows: list, key, in_match: set[int], with_ecart: set[int]) -> list:
    """Lignes à signaler « Doublon potentiel » : dans chaque groupe de lignes identiques, la ligne
    rapprochée (sinon la plus ancienne) est l'originale ; les autres le sont si elles sont libres."""
    groups: dict[tuple, list] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    flagged = []
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda row: row.id)
        original = next((row for row in group if row.statut == "Rapprochée"), group[0])
        for row in group:
            if row is original or row.statut not in ELIGIBLES_DOUBLON:
                continue
            if row.id in in_match or row.id in with_ecart:
                continue
            flagged.append(row)
    return flagged


def generate(
    db: Session,
    *,
    company_id: int,
    bank_account_id: int | None,
    date_from: date,
    date_to: date,
    acteur_id: int,
    ip: str | None,
    today: date | None = None,
) -> GenerationResult:
    """Crée les écarts de la période.

    - Doublon potentiel : opérations du même compte de même date, montant et libellé ; écritures
      du même compte de même date, montant, libellé et pièce.
    - Banque sans écriture / Écriture sans banque : ligne encore « Non rapprochée », sans
      correspondance, datée d'au moins `fenetre_jours` avant aujourd'hui (son pendant peut encore
      arriver avant).
    Une ligne qui a déjà eu un écart (même clôturé) n'en reçoit jamais un ici.
    """
    if date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    if (date_to - date_from).days >= PERIODE_MAX_JOURS:
        raise ConflictError(f"La période ne peut pas dépasser {PERIODE_MAX_JOURS} jours.")
    company = _company(db, company_id, lock=True)
    accounts = reconciliation_repository.company_accounts(db, company.id, bank_account_id)
    if bank_account_id is not None and not accounts:
        raise NotFoundError("Compte bancaire introuvable pour cette société.")
    account_ids = [account.id for account in accounts]
    fenetre = reconciliation_service.grille(db).fenetre_jours
    date_limite = (today or business_today()) - timedelta(days=fenetre)

    # 1. Doublons potentiels
    txs = repo.transactions_of_period(db, account_ids, date_from, date_to)
    tx_ids = [tx.id for tx in txs]
    doublons_tx = _duplicates(
        txs,
        lambda tx: (tx.bank_account_id, tx.date_operation, tx.montant, _plain(tx.libelle)),
        repo.transaction_ids_in_active_match(db, tx_ids),
        repo.transaction_ids_with_discrepancy(db, tx_ids),
    )
    entries = repo.entries_of_period(db, company.id, account_ids, date_from, date_to)
    entry_ids = [entry.id for entry in entries]
    doublons_ec = _duplicates(
        entries,
        lambda e: (
            e.bank_account_id,
            e.date_ecriture,
            e.montant,
            _plain(e.libelle),
            _plain(e.numero_piece),
        ),
        repo.entry_ids_in_active_match(db, entry_ids),
        repo.entry_ids_with_discrepancy(db, entry_ids),
    )
    nouveaux: list[Discrepancy] = []
    for tx in doublons_tx:
        nouveaux.append(
            _new(company_id=company.id, type_ecart="Doublon potentiel", tx=tx, entry=None)
        )
    for entry in doublons_ec:
        nouveaux.append(
            _new(company_id=company.id, type_ecart="Doublon potentiel", tx=None, entry=entry)
        )

    # 2. Lignes restées sans pendant au-delà de la fenêtre du moteur
    deja = {tx.id for tx in doublons_tx}, {entry.id for entry in doublons_ec}
    sans_ecriture = sans_banque = 0
    fin = min(date_to, date_limite)
    if fin >= date_from:
        for tx in repo.unmatched_transactions(db, account_ids, date_from, fin):
            if tx.id not in deja[0]:
                nouveaux.append(
                    _new(
                        company_id=company.id, type_ecart="Banque sans écriture", tx=tx, entry=None
                    )
                )
                sans_ecriture += 1
        for entry in repo.unmatched_entries(db, company.id, account_ids, date_from, fin):
            if entry.id not in deja[1]:
                nouveaux.append(
                    _new(
                        company_id=company.id,
                        type_ecart="Écriture sans banque",
                        tx=None,
                        entry=entry,
                    )
                )
                sans_banque += 1

    for ecart in nouveaux:
        repo.add(db, ecart)
    db.flush()
    for ecart in nouveaux:
        _set_lines_status(
            db, ecart.bank_transaction_id, ecart.accounting_entry_id, "Écart", seulement=None
        )
        audit_service.log(
            db,
            user_id=acteur_id,
            action="creation_ecart",
            entite=ENTITE,
            entite_id=ecart.id,
            apres={**_snapshot(ecart), "origine": "Automatique"},
            ip=ip,
        )
    result = GenerationResult(
        banque_sans_ecriture=sans_ecriture,
        ecriture_sans_banque=sans_banque,
        doublons=len(doublons_tx) + len(doublons_ec),
        date_limite=date_limite,
    )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="generation_ecarts",
        entite="company",
        entite_id=company.id,
        apres={
            "compte": bank_account_id,
            "du": date_from,
            "au": date_to,
            "date_limite": date_limite,
            "banque_sans_ecriture": sans_ecriture,
            "ecriture_sans_banque": sans_banque,
            "doublons": result.doublons,
        },
        ip=ip,
    )
    _commit(db)
    return result


# --- Traitement -----------------------------------------------------------------------------------


def _locked(db: Session, discrepancy_id: int) -> Discrepancy:
    """Écart verrouillé, après le verrou de sa société (même ordre que le rapprochement)."""
    ecart = repo.get(db, discrepancy_id)
    if ecart is None:
        raise NotFoundError("Écart introuvable.")
    _company(db, ecart.company_id, lock=True)
    ecart = repo.get(db, discrepancy_id, lock=True)
    db.refresh(ecart)
    if ecart.statut == "Clôturé":
        raise ConflictError("Un écart clôturé ne se modifie plus.")
    return ecart


_ABSENT = object()


def update(
    db: Session,
    discrepancy_id: int,
    *,
    statut: str | None = None,
    responsable_id: int | None | object = _ABSENT,
    commentaire: str | None | object = _ABSENT,
    acteur_id: int,
    ip: str | None,
) -> Discrepancy:
    """Fait avancer un écart (hors clôture), change son responsable ou son commentaire.

    `responsable_id` / `commentaire` absents : inchangés ; `None` : effacés.
    """
    ecart = _locked(db, discrepancy_id)
    avant = _snapshot(ecart)
    if statut is not None and statut != ecart.statut:
        if statut not in TRANSITIONS.get(ecart.statut, set()):
            raise ConflictError(
                f"Un écart « {ecart.statut} » ne passe pas directement à « {statut} »."
            )
        ecart.statut = statut
        ecart.traite_le = datetime.now(UTC) if statut == "Traité" else None
    if responsable_id is not _ABSENT:
        _check_responsable(db, responsable_id)  # type: ignore[arg-type]
        ecart.responsable_id = responsable_id  # type: ignore[assignment]
    if commentaire is not _ABSENT:
        ecart.commentaire = _clean(commentaire)  # type: ignore[arg-type]
    apres = _snapshot(ecart)
    if apres == avant:
        return ecart
    audit_service.log(
        db,
        user_id=acteur_id,
        action="modification_ecart",
        entite=ENTITE,
        entite_id=ecart.id,
        avant=avant,
        apres=apres,
        ip=ip,
    )
    _commit(db)
    return ecart


def close(
    db: Session, discrepancy_id: int, *, commentaire: str, acteur_id: int, ip: str | None
) -> Discrepancy:
    """Clôture un écart : commentaire obligatoire, auteur et date tracés ; ses lignes redeviennent
    « Non rapprochée »."""
    texte = _clean(commentaire)
    if texte is None:
        raise ConflictError("Indiquez en commentaire comment l'écart a été traité.")
    ecart = _locked(db, discrepancy_id)
    avant = _snapshot(ecart)
    ecart.statut = "Clôturé"
    ecart.commentaire = texte
    ecart.cloture_le = datetime.now(UTC)
    ecart.cloture_par_id = acteur_id
    if ecart.traite_le is None:
        ecart.traite_le = ecart.cloture_le
    _set_lines_status(
        db,
        ecart.bank_transaction_id,
        ecart.accounting_entry_id,
        "Non rapprochée",
        seulement="Écart",
    )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="cloture_ecart",
        entite=ENTITE,
        entite_id=ecart.id,
        avant=avant,
        apres=_snapshot(ecart),
        ip=ip,
    )
    _commit(db)
    return ecart


# --- Lectures -------------------------------------------------------------------------------------


@dataclass
class DiscrepanciesPage:
    total: int
    page: int
    taille: int
    par_statut: dict[str, int]
    montants_ouverts: dict[str, Decimal]
    ecarts: list[repo.Row]


def list_discrepancies(
    db: Session,
    company_id: int,
    *,
    statut: str | None = None,
    type_ecart: str | None = None,
    responsable_id: int | None = None,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    page: int = 1,
) -> DiscrepanciesPage:
    """50 écarts par page ; les compteurs et montants portent sur tout le filtre, hors statut."""
    company = _company(db, company_id)
    if date_from and date_to and date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")
    query = repo.discrepancies_query(
        company.id,
        bank_account_id=bank_account_id,
        type_ecart=type_ecart,
        responsable_id=responsable_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    total, rows = repo.page(
        db, query, statut=statut, offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE
    )
    return DiscrepanciesPage(
        total=total,
        page=page,
        taille=PAGE_SIZE,
        par_statut=repo.count_by_status(db, query),
        montants_ouverts=repo.open_totals_by_currency(db, query),
        ecarts=rows,
    )


@dataclass
class DiscrepancyDetail:
    row: repo.Row
    cloture_par: str | None
    historique: list


def get_detail(db: Session, discrepancy_id: int) -> DiscrepancyDetail:
    row = repo.detail(db, discrepancy_id)
    if row is None:
        raise NotFoundError("Écart introuvable.")
    return DiscrepancyDetail(
        row=row,
        cloture_par=repo.user_name(db, row[0].cloture_par_id),
        historique=repo.history(db, discrepancy_id),
    )


def responsables(db: Session, company_id: int) -> list[User]:
    _company(db, company_id)
    return repo.responsables(db, PermissionCode.DISCREPANCIES_MANAGE.value)
