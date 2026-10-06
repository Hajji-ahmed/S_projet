"""Rapprochement bancaire 1→1 (P11) : lancement du moteur, décisions des utilisateurs, lectures.

Le moteur (`reconciliation_scoring`) ne fait que PROPOSER. Seul un utilisateur autorisé valide,
rejette ou annule une correspondance, et chaque décision est tracée dans `audit_logs`.

Statuts des opérations et des écritures :
- proposée ou ambiguë → « À vérifier » ;
- validée par un utilisateur (ou rapprochée à la main) → « Rapprochée » ;
- rejetée ou annulée → « Non rapprochée ». Une paire rejetée n'est jamais reproposée.
« Écart » est réservé aux écarts (P12) : le moteur n'y touche pas.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AccountingEntry,
    BankTransaction,
    Company,
    ReconciliationMatch,
    ReconciliationMatchItem,
)
from app.repositories import reconciliation_repository as repo
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError
from app.services.reconciliation_scoring import (
    GRILLE_PAR_DEFAUT,
    Ecriture,
    Grille,
    Operation,
    Score,
    comparable,
    proposer,
    score,
)

PAGE_SIZE = 50
PERIODE_MAX_JOURS = 366
NB_CANDIDATS = 20
COMMENTAIRE_MAX = 500
ENTITE = "reconciliation_match"
CONCURRENT = "Le rapprochement vient d'être modifié par un autre utilisateur : rechargez la page."


# --- Grille ---------------------------------------------------------------------------------------


def grille(db: Session) -> Grille:
    """Grille lue dans `reconciliation_rules` ; un code absent ou désactivé garde sa valeur par défaut."""
    valeurs: dict[str, object] = {}
    for rule in repo.active_rules(db):
        match rule.code:
            case "REFERENCE" | "MONTANT" | "LIBELLE" | "TIERS":
                valeurs[rule.code.lower()] = rule.poids
            case "DATE":
                valeurs["date"] = rule.poids
                if rule.tolerance is not None:
                    valeurs["tolerance_jours"] = int(rule.tolerance)
            case "FENETRE":
                if rule.tolerance is not None:
                    valeurs["fenetre_jours"] = int(rule.tolerance)
            case "SEUIL_PROPOSITION" | "SEUIL_FORT" | "ECART_AMBIGUITE":
                valeurs[rule.code.lower()] = rule.poids
    return Grille(**{**GRILLE_PAR_DEFAUT.__dict__, **valeurs})


def _operation(tx: BankTransaction) -> Operation:
    return Operation(
        id=tx.id,
        date_operation=tx.date_operation,
        date_valeur=tx.date_valeur,
        libelle=tx.libelle,
        reference=tx.reference,
        montant=tx.montant,
        bank_account_id=tx.bank_account_id,
    )


def _ecriture(entry: AccountingEntry) -> Ecriture:
    return Ecriture(
        id=entry.id,
        date_ecriture=entry.date_ecriture,
        libelle=entry.libelle,
        reference=entry.reference,
        numero_piece=entry.numero_piece,
        tiers=entry.tiers,
        montant=entry.montant,
        bank_account_id=entry.bank_account_id,
    )


def _detail_json(resultat: Score) -> dict[str, str]:
    return {code: str(value) for code, value in resultat.detail.items()}


def _company(db: Session, company_id: int, *, lock: bool = False) -> Company:
    company = repo.lock_company(db, company_id) if lock else db.get(Company, company_id)
    if company is None or not company.actif:
        raise NotFoundError("Société introuvable.")
    return company


def _check_period(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise ConflictError("La date de début doit précéder la date de fin.")


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:  # une même ligne retenue en même temps par une autre action
        db.rollback()
        raise ConflictError(CONCURRENT) from error


# --- Lancement du moteur --------------------------------------------------------------------------


@dataclass
class RunResult:
    nb_operations: int
    nb_ecritures: int
    nb_propositions: int
    nb_fortes: int
    nb_operations_ambigues: int
    nb_ecritures_ambigues: int


def run(
    db: Session,
    *,
    company_id: int,
    bank_account_id: int | None,
    date_from: date,
    date_to: date,
    acteur_id: int,
    ip: str | None,
) -> RunResult:
    """Propose des correspondances pour les opérations de la période.

    Les propositions automatiques encore en attente de la période sont remplacées ; les
    correspondances validées, rejetées ou manuelles ne sont jamais modifiées.
    """
    _check_period(date_from, date_to)
    if (date_to - date_from).days >= PERIODE_MAX_JOURS:
        raise ConflictError(f"La période ne peut pas dépasser {PERIODE_MAX_JOURS} jours.")
    company = _company(db, company_id, lock=True)
    accounts = repo.company_accounts(db, company.id, bank_account_id)
    if bank_account_id is not None and not accounts:
        raise NotFoundError("Compte bancaire introuvable pour cette société.")
    account_ids = [account.id for account in accounts]
    regles = grille(db)
    entry_from = date_from - timedelta(days=regles.fenetre_jours)
    entry_to = date_to + timedelta(days=regles.fenetre_jours)

    # 1. Les propositions en attente de la période sont refaites
    anciennes = repo.automatic_proposals_of_period(db, account_ids, date_from, date_to)
    anciennes_tx = {
        i.bank_transaction_id for m in anciennes for i in m.items if i.bank_transaction_id
    }
    anciennes_ec = {
        i.accounting_entry_id for m in anciennes for i in m.items if i.accounting_entry_id
    }
    repo.delete_matches(db, [match.id for match in anciennes])
    repo.set_transaction_status(db, anciennes_tx, "Non rapprochée")
    repo.set_entry_status(db, anciennes_ec, "Non rapprochée")
    repo.reset_unmatched_to_check(
        db, company.id, account_ids, date_from, date_to, entry_from, entry_to
    )
    db.expire_all()

    # 2. Le moteur compare ce qui reste libre
    transactions = repo.free_transactions(db, account_ids, date_from, date_to)
    entries = repo.free_entries(db, company.id, account_ids, entry_from, entry_to)
    by_tx = {tx.id: tx for tx in transactions}
    by_entry = {entry.id: entry for entry in entries}
    resultat = proposer(
        [_operation(tx) for tx in transactions],
        [_ecriture(entry) for entry in entries],
        regles,
        repo.rejected_pairs(db, company.id),
    )

    # 3. Chaque proposition est enregistrée, en attente d'une décision humaine
    for proposition in resultat.propositions:
        tx, entry = by_tx[proposition.operation_id], by_entry[proposition.ecriture_id]
        repo.add(
            db,
            ReconciliationMatch(
                company_id=company.id,
                type="1-1",
                score=proposition.score.total,
                statut="Proposée",
                origine="Automatique",
                detail_score=_detail_json(proposition.score),
                items=[
                    ReconciliationMatchItem(
                        bank_transaction_id=tx.id, montant_affecte=abs(tx.montant), actif=True
                    ),
                    ReconciliationMatchItem(
                        accounting_entry_id=entry.id,
                        montant_affecte=abs(entry.montant),
                        actif=True,
                    ),
                ],
            ),
        )
    a_verifier_tx = {p.operation_id for p in resultat.propositions} | resultat.operations_ambigues
    a_verifier_ec = {p.ecriture_id for p in resultat.propositions} | resultat.ecritures_ambigues
    repo.set_transaction_status(db, a_verifier_tx, "À vérifier")
    repo.set_entry_status(db, a_verifier_ec, "À vérifier")

    result = RunResult(
        nb_operations=len(transactions),
        nb_ecritures=len(entries),
        nb_propositions=len(resultat.propositions),
        nb_fortes=sum(1 for p in resultat.propositions if p.score.total >= regles.seuil_fort),
        nb_operations_ambigues=len(resultat.operations_ambigues),
        nb_ecritures_ambigues=len(resultat.ecritures_ambigues),
    )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="rapprochement_lance",
        entite="company",
        entite_id=company.id,
        apres={
            "compte": bank_account_id,
            "du": date_from,
            "au": date_to,
            "propositions_remplacees": len(anciennes),
            **result.__dict__,
        },
        ip=ip,
    )
    _commit(db)
    return result


# --- Décisions -----------------------------------------------------------------------------------


def _locked_match(db: Session, match_id: int) -> ReconciliationMatch:
    """Correspondance verrouillée, après le verrou de sa société (même ordre que `run`)."""
    match = repo.get_match(db, match_id)
    if match is None:
        raise NotFoundError("Correspondance introuvable.")
    _company(db, match.company_id, lock=True)
    match = repo.get_match(db, match_id, lock=True)
    if match is None:
        raise NotFoundError("Correspondance introuvable.")
    db.refresh(match)
    return match


def _members(match: ReconciliationMatch) -> tuple[set[int], set[int]]:
    tx_ids = {item.bank_transaction_id for item in match.items if item.bank_transaction_id}
    entry_ids = {item.accounting_entry_id for item in match.items if item.accounting_entry_id}
    return tx_ids, entry_ids


def _snapshot(match: ReconciliationMatch) -> dict:
    tx_ids, entry_ids = _members(match)
    return {
        "statut": match.statut,
        "origine": match.origine,
        "score": match.score,
        "operations": sorted(tx_ids),
        "ecritures": sorted(entry_ids),
        "commentaire": match.commentaire,
    }


def _release(db: Session, match: ReconciliationMatch, statut: str, commentaire: str | None) -> None:
    """Rejette ou annule : les éléments sont libérés et redeviennent « Non rapprochée »."""
    match.statut = statut
    if commentaire is not None:
        match.commentaire = commentaire
    for item in match.items:
        item.actif = False
    tx_ids, entry_ids = _members(match)
    db.flush()
    repo.set_transaction_status(db, tx_ids, "Non rapprochée")
    repo.set_entry_status(db, entry_ids, "Non rapprochée")


def _validate(db: Session, match: ReconciliationMatch, acteur_id: int) -> None:
    match.statut = "Validée"
    match.valide_par_id = acteur_id
    match.valide_le = datetime.now(UTC)
    tx_ids, entry_ids = _members(match)
    db.flush()
    repo.set_transaction_status(db, tx_ids, "Rapprochée")
    repo.set_entry_status(db, entry_ids, "Rapprochée")


def _clean_comment(commentaire: str | None) -> str | None:
    text = " ".join(commentaire.split()) if commentaire else ""
    if len(text) > COMMENTAIRE_MAX:
        raise ConflictError(f"Le commentaire ne peut pas dépasser {COMMENTAIRE_MAX} caractères.")
    return text or None


def validate(db: Session, match_id: int, *, acteur_id: int, ip: str | None) -> ReconciliationMatch:
    """Un utilisateur confirme une proposition du moteur."""
    match = _locked_match(db, match_id)
    if match.statut != "Proposée":
        raise ConflictError(
            f"Seule une correspondance proposée se valide (statut : {match.statut})."
        )
    avant = _snapshot(match)
    _validate(db, match, acteur_id)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="validation_rapprochement",
        entite=ENTITE,
        entite_id=match.id,
        avant=avant,
        apres=_snapshot(match),
        ip=ip,
    )
    _commit(db)
    return match


def validate_batch(
    db: Session, match_ids: list[int], *, acteur_id: int, ip: str | None
) -> list[ReconciliationMatch]:
    """Valide en une fois des propositions FORTES (score ≥ seuil), toutes ou aucune."""
    ids = sorted(set(match_ids))
    found = repo.get_matches(db, ids)
    if len(found) != len(ids):
        raise NotFoundError("Correspondance introuvable.")
    companies = {match.company_id for match in found}
    if len(companies) != 1:
        raise ConflictError("Une validation en lot ne porte que sur une seule société.")
    _company(db, companies.pop(), lock=True)
    matches = repo.get_matches(db, ids, lock=True)
    seuil = grille(db).seuil_fort
    for match in matches:
        db.refresh(match)
        if match.statut != "Proposée":
            raise ConflictError(
                f"La correspondance n° {match.id} n'est plus proposée (statut : {match.statut})."
            )
        if match.score is None or match.score < seuil:
            raise ConflictError(
                f"La correspondance n° {match.id} n'est pas une forte correspondance "
                f"(score inférieur à {seuil:.0f}) : validez-la seule, après vérification."
            )
    for match in matches:
        avant = _snapshot(match)
        _validate(db, match, acteur_id)
        audit_service.log(
            db,
            user_id=acteur_id,
            action="validation_rapprochement",
            entite=ENTITE,
            entite_id=match.id,
            avant=avant,
            apres={**_snapshot(match), "en_lot": True},
            ip=ip,
        )
    _commit(db)
    return matches


def reject(
    db: Session, match_id: int, *, commentaire: str | None, acteur_id: int, ip: str | None
) -> ReconciliationMatch:
    """Un utilisateur refuse une proposition : la paire ne sera plus jamais proposée."""
    match = _locked_match(db, match_id)
    if match.statut != "Proposée":
        raise ConflictError(
            f"Seule une correspondance proposée se rejette (statut : {match.statut})."
        )
    avant = _snapshot(match)
    _release(db, match, "Rejetée", _clean_comment(commentaire))
    audit_service.log(
        db,
        user_id=acteur_id,
        action="rejet_rapprochement",
        entite=ENTITE,
        entite_id=match.id,
        avant=avant,
        apres=_snapshot(match),
        ip=ip,
    )
    _commit(db)
    return match


def cancel(
    db: Session, match_id: int, *, motif: str, acteur_id: int, ip: str | None
) -> ReconciliationMatch:
    """Annule un rapprochement validé ; le motif est obligatoire et la trace conservée."""
    texte = _clean_comment(motif)
    if texte is None:
        raise ConflictError("Indiquez le motif de l'annulation.")
    match = _locked_match(db, match_id)
    if match.statut != "Validée":
        raise ConflictError(
            f"Seul un rapprochement validé s'annule (statut : {match.statut}) ; "
            "une proposition se rejette."
        )
    avant = _snapshot(match)
    _release(db, match, "Annulée", texte)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="annulation_rapprochement",
        entite=ENTITE,
        entite_id=match.id,
        avant=avant,
        apres=_snapshot(match),
        ip=ip,
    )
    _commit(db)
    return match


def match_manually(
    db: Session,
    *,
    transaction_id: int,
    entry_id: int,
    commentaire: str | None,
    acteur_id: int,
    ip: str | None,
) -> ReconciliationMatch:
    """Rapprochement 1→1 choisi par l'utilisateur : validé d'emblée, origine « Manuelle ».

    Exige le même montant, en sens opposé. Une proposition en attente qui contient l'opération ou
    l'écriture est rejetée par ce choix (et tracée) ; un rapprochement validé ne l'est jamais.
    """
    texte = _clean_comment(commentaire)
    found = repo.get_transaction(db, transaction_id)
    if found is None:
        raise NotFoundError("Opération bancaire introuvable.")
    tx, account = found
    entry = repo.get_entry(db, entry_id)
    if entry is None:
        raise NotFoundError("Écriture comptable introuvable.")
    company = _company(db, account.company_id, lock=True)
    db.refresh(tx)
    db.refresh(entry)
    if entry.company_id != company.id:
        raise ConflictError(
            "L'opération et l'écriture appartiennent à deux sociétés différentes : "
            "elles ne se rapprochent jamais."
        )
    if entry.bank_account_id != tx.bank_account_id:
        raise ConflictError(
            "L'écriture n'est pas passée dans le journal Sage de ce compte bancaire."
        )
    if tx.montant == 0 or tx.montant != -entry.montant:
        raise ConflictError(
            "Les montants doivent être égaux, en sens opposé (un crédit en banque correspond à "
            "un débit dans Sage)."
        )
    if "Écart" in (tx.statut, entry.statut):
        raise ConflictError("Une ligne en écart se traite dans l'écran Écarts.")

    remplacees = []
    for active in repo.active_matches_of(db, transaction_id=tx.id, entry_id=entry.id):
        if active.statut == "Validée":
            tx_ids, _ = _members(active)
            quoi = "L'opération" if tx.id in tx_ids else "L'écriture"
            raise ConflictError(f"{quoi} est déjà rapprochée : annulez d'abord ce rapprochement.")
        avant = _snapshot(active)
        _release(db, active, "Rejetée", "Remplacée par un rapprochement manuel.")
        audit_service.log(
            db,
            user_id=acteur_id,
            action="rejet_rapprochement",
            entite=ENTITE,
            entite_id=active.id,
            avant=avant,
            apres=_snapshot(active),
            ip=ip,
        )
        remplacees.append(active.id)

    resultat = score(_operation(tx), _ecriture(entry), grille(db))
    match = ReconciliationMatch(
        company_id=company.id,
        type="1-1",
        score=resultat.total,
        statut="Proposée",
        origine="Manuelle",
        detail_score=_detail_json(resultat),
        commentaire=texte,
        items=[
            ReconciliationMatchItem(
                bank_transaction_id=tx.id, montant_affecte=abs(tx.montant), actif=True
            ),
            ReconciliationMatchItem(
                accounting_entry_id=entry.id, montant_affecte=abs(entry.montant), actif=True
            ),
        ],
    )
    repo.add(db, match)
    db.flush()
    _validate(db, match, acteur_id)
    audit_service.log(
        db,
        user_id=acteur_id,
        action="rapprochement_manuel",
        entite=ENTITE,
        entite_id=match.id,
        apres={**_snapshot(match), "propositions_remplacees": remplacees},
        ip=ip,
    )
    _commit(db)
    return match


# --- Lectures ------------------------------------------------------------------------------------


@dataclass
class MatchView:
    match: ReconciliationMatch
    transaction: BankTransaction
    bank_code: str
    entry: AccountingEntry
    entry_bank_code: str | None
    valide_par: str | None
    forte: bool


@dataclass
class TransactionsPage:
    total: int
    page: int
    taille: int
    par_statut: dict[str, int]
    operations: list[tuple[BankTransaction, str, ReconciliationMatch | None]]


@dataclass
class Candidate:
    entry: AccountingEntry
    bank_code: str | None
    score: Score
    rejetee: bool
    proposee_ailleurs: bool


def list_transactions(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    statut: str | None = None,
    q: str | None = None,
    page: int = 1,
) -> TransactionsPage:
    """Volet « Transactions bancaires » : 50 par page ; le décompte par statut porte sur tout le
    filtre, hors filtre de statut."""
    company = _company(db, company_id)
    _check_period(date_from, date_to)
    query = repo.transactions_query(
        company.id, bank_account_id=bank_account_id, date_from=date_from, date_to=date_to, q=q
    )
    par_statut = repo.count_by_status(db, query)
    total, rows = repo.page_of_transactions(
        db, query, statut=statut, offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE
    )
    matches = repo.active_match_by_transaction(db, [tx.id for tx, _ in rows])
    return TransactionsPage(
        total=total,
        page=page,
        taille=PAGE_SIZE,
        par_statut=par_statut,
        operations=[(tx, code, matches.get(tx.id)) for tx, code in rows],
    )


def _views(db: Session, matches: list[ReconciliationMatch], seuil_fort: Decimal) -> list[MatchView]:
    tx_ids = {i.bank_transaction_id for m in matches for i in m.items if i.bank_transaction_id}
    entry_ids = {i.accounting_entry_id for m in matches for i in m.items if i.accounting_entry_id}
    transactions = repo.transactions_with_bank(db, tx_ids)
    entries = repo.entries_with_bank(db, entry_ids)
    names = repo.user_names(db, {m.valide_par_id for m in matches if m.valide_par_id})
    views = []
    for match in matches:
        tx_id = next(i.bank_transaction_id for i in match.items if i.bank_transaction_id)
        entry_id = next(i.accounting_entry_id for i in match.items if i.accounting_entry_id)
        tx, code = transactions[tx_id]
        entry, entry_code = entries[entry_id]
        views.append(
            MatchView(
                match=match,
                transaction=tx,
                bank_code=code,
                entry=entry,
                entry_bank_code=entry_code,
                valide_par=names.get(match.valide_par_id) if match.valide_par_id else None,
                forte=match.score is not None and match.score >= seuil_fort,
            )
        )
    return views


def list_matches(
    db: Session,
    company_id: int,
    *,
    statut: str = "Proposée",
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[Decimal, list[MatchView]]:
    """Correspondances 1→1 de la société (par défaut celles en attente), avec le seuil « forte »."""
    company = _company(db, company_id)
    _check_period(date_from, date_to)
    seuil = grille(db).seuil_fort
    matches = repo.matches_of_period(
        db,
        company.id,
        statut=statut,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
    )
    return seuil, _views(db, matches, seuil)


def get_match_view(db: Session, match_id: int) -> MatchView:
    match = repo.get_match(db, match_id)
    if match is None:
        raise NotFoundError("Correspondance introuvable.")
    return _views(db, [match], grille(db).seuil_fort)[0]


def candidates(
    db: Session, transaction_id: int
) -> tuple[BankTransaction, str, list[Candidate], Decimal, Decimal]:
    """Écritures qui pourraient correspondre à l'opération, de la meilleure à la moins bonne.

    Même compte, sens opposé, dans la fenêtre de dates ; une écriture déjà rapprochée n'apparaît
    pas. Retourne aussi le seuil de proposition et le seuil « forte ».
    """
    found = repo.get_transaction(db, transaction_id)
    if found is None:
        raise NotFoundError("Opération bancaire introuvable.")
    tx, account = found
    regles = grille(db)
    jours = [tx.date_operation] + ([tx.date_valeur] if tx.date_valeur else [])
    fenetre = timedelta(days=regles.fenetre_jours)
    entries = repo.candidate_entries(
        db, tx, account.company_id, min(jours) - fenetre, max(jours) + fenetre
    )
    operation = _operation(tx)
    rejetees = repo.rejected_pairs(db, account.company_id)
    actives = repo.active_matches_by_entry(db, [entry.id for entry in entries])
    codes = repo.entries_with_bank(db, {entry.id for entry in entries})
    scored = []
    for entry in entries:
        ecriture = _ecriture(entry)
        if not comparable(operation, ecriture, regles):
            continue
        active = actives.get(entry.id)
        scored.append(
            Candidate(
                entry=entry,
                bank_code=codes[entry.id][1],
                score=score(operation, ecriture, regles),
                rejetee=(tx.id, entry.id) in rejetees,
                proposee_ailleurs=active is not None and tx.id not in _members(active)[0],
            )
        )
    scored.sort(key=lambda item: (-item.score.total, item.entry.date_ecriture, item.entry.id))
    bank_code = repo.transactions_with_bank(db, {tx.id})[tx.id][1]
    return tx, bank_code, scored[:NB_CANDIDATS], regles.seuil_proposition, regles.seuil_fort
