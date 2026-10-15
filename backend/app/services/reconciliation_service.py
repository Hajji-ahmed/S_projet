"""Rapprochement bancaire 1→1 (P11) : lancement du moteur, décisions des utilisateurs, lectures.

Le moteur (`reconciliation_scoring`) ne fait que PROPOSER. Seul un utilisateur autorisé valide,
rejette ou annule une correspondance, et chaque décision est tracée dans `audit_logs`.

Statuts des opérations et des écritures :
- proposée ou ambiguë → « À vérifier » ;
- validée par un utilisateur (ou rapprochée à la main) → « Rapprochée » ;
- rejetée ou annulée → « Non rapprochée ». Une paire rejetée n'est jamais reproposée.
« Écart » est réservé aux écarts (P12) : le moteur n'y touche pas.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AccountingEntry,
    BankTransaction,
    Company,
    ReconciliationMatch,
    ReconciliationMatchItem,
)
from app.repositories import discrepancy_repository
from app.repositories import reconciliation_repository as repo
from app.services import audit_service
from app.services.errors import ConflictError, NotFoundError
from app.services.position_service import BUSINESS_TZ, business_today
from app.services.reconciliation_groupes import ResultatGroupes, grouper
from app.services.reconciliation_scoring import (
    AUTRE,
    GRILLE_PAR_DEFAUT,
    Ecriture,
    Grille,
    Operation,
    Resultat,
    Score,
    comparable,
    proposer,
    score,
    type_ecriture,
    type_operation,
)
from app.services.reconciliation_scoring import type_operation as _type_de

PAGE_SIZE = 50
# Garde-fou contre une année mal saisie (« 0026 ») : 5 ans au plus par lancement (08/10/2026)
PERIODE_MAX_JOURS = 1827
NB_CANDIDATS = 20
COMMENTAIRE_MAX = 500
ENTITE = "reconciliation_match"
CONCURRENT = "Le rapprochement vient d'être modifié par un autre utilisateur : rechargez la page."


# --- Grille ---------------------------------------------------------------------------------------


# Critères dont la règle désactivée vaut 0 point (et non sa valeur par défaut)
_CRITERES_REGLES = {
    "REFERENCE": "reference",
    "MONTANT": "montant",
    "DATE": "date",
    "LIBELLE": "libelle",
    "TIERS": "tiers",
}


def grille(db: Session) -> Grille:
    """Grille lue dans `reconciliation_rules`.

    Un critère désactivé (`actif = false`) vaut 0 point ; un seuil ou une fenêtre désactivé ou
    absent garde sa valeur par défaut, comme un critère absent de la table.
    """
    valeurs: dict[str, object] = {}
    for rule in repo.all_rules(db):
        if rule.code in _CRITERES_REGLES:
            valeurs[_CRITERES_REGLES[rule.code]] = rule.poids if rule.actif else Decimal("0")
            if rule.code == "DATE" and rule.actif and rule.tolerance is not None:
                valeurs["tolerance_jours"] = int(rule.tolerance)
            continue
        if not rule.actif:
            continue
        match rule.code:
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


def montant_rapprochement(entry: AccountingEntry) -> Decimal:
    """Montant d'une écriture face au relevé : en devise pour un compte EUR / USD (colonne
    « Devise » de Sage, 14/10/2026), sinon le montant MAD. Le montant devise n'est lu que pour un
    compte en devise : une écriture d'un compte MAD n'en a jamais."""
    return entry.montant_devise if entry.montant_devise is not None else entry.montant


def _ecriture(entry: AccountingEntry) -> Ecriture:
    return Ecriture(
        id=entry.id,
        date_ecriture=entry.date_ecriture,
        libelle=entry.libelle,
        reference=entry.reference,
        numero_piece=entry.numero_piece,
        tiers=entry.tiers,
        montant=montant_rapprochement(entry),
        bank_account_id=entry.bank_account_id,
        echeance=entry.echeance,
    )


def _detail_json(resultat: Score, second: Decimal | None = None) -> dict[str, str]:
    """Points par critère ; `second` : score du meilleur autre candidat (concurrente proche)."""
    detail = {code: str(value) for code, value in resultat.detail.items()}
    if second is not None:
        detail["second"] = str(second)
    return detail


def score_second(match: ReconciliationMatch) -> Decimal | None:
    """Score de la 2e meilleure écriture (ou opération) au moment de la proposition."""
    value = (match.detail_score or {}).get("second")
    return None if value is None else Decimal(str(value))


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
    # Groupes N → 1 proposés (12/10/2026)
    nb_groupes: int = 0


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
        raise ConflictError("La période ne peut pas dépasser 5 ans.")
    company = _company(db, company_id, lock=True)
    accounts = repo.company_accounts(db, company.id, bank_account_id)
    if bank_account_id is not None and not accounts:
        raise NotFoundError("Compte bancaire introuvable pour cette société.")
    account_ids = [account.id for account in accounts]
    regles = grille(db)
    moteur = _engine(db, company, account_ids, date_from, date_to, regles)
    result = RunResult(
        nb_operations=moteur.nb_operations,
        nb_ecritures=moteur.nb_ecritures,
        nb_propositions=len(moteur.resultat.propositions),
        nb_fortes=sum(
            1 for p in moteur.resultat.propositions if p.score.total >= regles.seuil_fort
        ),
        nb_operations_ambigues=len(moteur.resultat.operations_ambigues),
        nb_ecritures_ambigues=len(moteur.resultat.ecritures_ambigues),
        nb_groupes=len(moteur.groupes.groupes),
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
            "propositions_remplacees": moteur.nb_remplacees,
            **result.__dict__,
        },
        ip=ip,
    )
    _commit(db)
    return result


@dataclass
class _Moteur:
    resultat: Resultat
    nb_operations: int
    nb_ecritures: int
    nb_remplacees: int
    groupes: ResultatGroupes = field(default_factory=ResultatGroupes)


def _engine(
    db: Session,
    company: Company,
    account_ids: list[int],
    date_from: date,
    date_to: date,
    regles: Grille,
) -> _Moteur:
    """Refait les propositions automatiques en attente des comptes sur la période (sans commit) :
    les correspondances validées, rejetées ou manuelles ne sont jamais modifiées."""
    db.flush()
    # Écritures lues jusqu'à la fenêtre des n° (chèques, effets), la plus large (12/10/2026)
    lecture = max(regles.fenetre_jours, regles.fenetre_numero_jours)
    entry_from = date_from - timedelta(days=lecture)
    entry_to = date_to + timedelta(days=lecture)

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

    # 3. Groupes N → 1 (12/10/2026) sur ce que le 1 → 1 laisse libre : un groupe équilibré passe
    # avant une paire 1 → 1 aux montants différents (qui ne pourrait jamais être validée)
    equilibrees = [
        p
        for p in resultat.propositions
        if by_tx[p.operation_id].montant == -montant_rapprochement(by_entry[p.ecriture_id])
    ]
    bloque_tx = {p.operation_id for p in equilibrees} | resultat.operations_ambigues
    bloque_ec = {p.ecriture_id for p in equilibrees} | resultat.ecritures_ambigues
    groupes = grouper(
        [_operation(tx) for tx in transactions if tx.id not in bloque_tx],
        [_ecriture(entry) for entry in entries if entry.id not in bloque_ec],
        regles,
        repo.rejected_pairs(db, company.id),
    )
    groupe_tx = {i for g in groupes.groupes for i in g.operation_ids}
    groupe_ec = {g.ecriture_id for g in groupes.groupes}
    resultat.propositions = [
        p
        for p in resultat.propositions
        if p in equilibrees or (p.operation_id not in groupe_tx and p.ecriture_id not in groupe_ec)
    ]

    # 4. Chaque proposition est enregistrée, en attente d'une décision humaine
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
                detail_score=_detail_json(proposition.score, proposition.second),
                items=[
                    ReconciliationMatchItem(
                        bank_transaction_id=tx.id, montant_affecte=abs(tx.montant), actif=True
                    ),
                    ReconciliationMatchItem(
                        accounting_entry_id=entry.id,
                        montant_affecte=abs(montant_rapprochement(entry)),
                        actif=True,
                    ),
                ],
            ),
        )
    a_verifier_tx = {p.operation_id for p in resultat.propositions} | resultat.operations_ambigues
    a_verifier_ec = {p.ecriture_id for p in resultat.propositions} | resultat.ecritures_ambigues

    for groupe in groupes.groupes:
        entry = by_entry[groupe.ecriture_id]
        repo.add(
            db,
            ReconciliationMatch(
                company_id=company.id,
                type="N-1",
                score=groupe.score.total,
                statut="Proposée",
                origine="Automatique",
                detail_score={**_detail_json(groupe.score), "explication": groupe.explication},
                items=[
                    *(
                        ReconciliationMatchItem(
                            bank_transaction_id=tx_id,
                            montant_affecte=abs(by_tx[tx_id].montant),
                            actif=True,
                        )
                        for tx_id in groupe.operation_ids
                    ),
                    ReconciliationMatchItem(
                        accounting_entry_id=entry.id,
                        montant_affecte=abs(montant_rapprochement(entry)),
                        actif=True,
                    ),
                ],
            ),
        )
        a_verifier_tx.update(groupe.operation_ids)
        a_verifier_ec.add(entry.id)

    repo.set_transaction_status(db, a_verifier_tx, "À vérifier")
    repo.set_entry_status(db, a_verifier_ec, "À vérifier")
    db.flush()
    return _Moteur(resultat, len(transactions), len(entries), len(anciennes), groupes)


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
        "code": match.code,
        "operations": sorted(tx_ids),
        "ecritures": sorted(entry_ids),
        "commentaire": match.commentaire,
    }


def _decide(match: ReconciliationMatch, statut: str, acteur_id: int) -> None:
    """Nouvelle décision humaine : son auteur et sa date restent dans l'historique."""
    match.statut = statut
    match.decide_par_id = acteur_id
    match.decide_le = datetime.now(UTC)


def _release(
    db: Session,
    match: ReconciliationMatch,
    statut: str,
    commentaire: str | None,
    acteur_id: int,
) -> None:
    """Rejette ou annule : les éléments sont libérés et redeviennent « Non rapprochée »."""
    _decide(match, statut, acteur_id)
    if commentaire is not None:
        match.commentaire = commentaire
    for item in match.items:
        item.actif = False
    tx_ids, entry_ids = _members(match)
    db.flush()
    repo.set_transaction_status(db, tx_ids, "Non rapprochée")
    repo.set_entry_status(db, entry_ids, "Non rapprochée")


MONTANTS_DIFFERENTS = (
    "Les montants de l'opération et de l'écriture diffèrent : ce rapprochement ne peut pas être "
    "validé. Signalez un écart « Montant différent »."
)


def _check_amounts(db: Session, match: ReconciliationMatch) -> None:
    """Un rapprochement validé s'équilibre : la somme des montants (banque + Sage) vaut zéro."""
    tx_ids, entry_ids = _members(match)
    total = sum((db.get(BankTransaction, i).montant for i in tx_ids), Decimal("0")) + sum(
        (montant_rapprochement(db.get(AccountingEntry, i)) for i in entry_ids), Decimal("0")
    )
    if total != 0:
        raise ConflictError(MONTANTS_DIFFERENTS)


def _validate(db: Session, match: ReconciliationMatch, acteur_id: int) -> None:
    _check_amounts(db, match)
    _decide(match, "Validée", acteur_id)
    match.valide_par_id = acteur_id
    match.valide_le = match.decide_le
    tx_ids, entry_ids = _members(match)
    if match.code is None:
        match.code = _new_code(db, min(tx_ids))
    db.flush()
    repo.set_transaction_status(db, tx_ids, "Rapprochée")
    repo.set_entry_status(db, entry_ids, "Rapprochée")


def _new_code(db: Session, transaction_id: int) -> str:
    """Code unique du rapprochement (13/10/2026) : « BP-26-000123 », un compteur par compte
    bancaire et par année de validation (date du Maroc)."""
    tx = db.get(BankTransaction, transaction_id)
    annee = business_today().year
    numero = repo.next_code_number(db, tx.bank_account_id, annee)
    banque = repo.bank_code_of_account(db, tx.bank_account_id)
    return f"{banque}-{annee % 100:02d}-{numero:06d}"


def create_validated(
    db: Session,
    *,
    company_id: int,
    transactions: list[BankTransaction],
    entry: AccountingEntry,
    origine: str,
    detail: dict,
    acteur_id: int,
) -> ReconciliationMatch:
    """Correspondance validée d'emblée entre des opérations et une écriture (comptabilisation des
    frais, 13/10/2026) : mêmes contrôles et même code qu'une validation humaine."""
    match = ReconciliationMatch(
        company_id=company_id,
        type="N-1" if len(transactions) > 1 else "1-1",
        statut="Proposée",
        origine=origine,
        detail_score=detail,
        items=[
            *(
                ReconciliationMatchItem(
                    bank_transaction_id=tx.id, montant_affecte=abs(tx.montant), actif=True
                )
                for tx in transactions
            ),
            ReconciliationMatchItem(
                accounting_entry_id=entry.id,
                montant_affecte=abs(montant_rapprochement(entry)),
                actif=True,
            ),
        ],
    )
    repo.add(db, match)
    db.flush()
    _validate(db, match, acteur_id)
    return match


ECRITURE_SIMTIS = (
    "Cette écriture a été comptabilisée par SIMTIS : supprimez-la depuis « À comptabiliser » "
    "(possible tant qu'elle n'est pas exportée pour Sage)."
)


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
    """Valide en une fois les propositions choisies par l'utilisateur, toutes ou aucune.

    Décision du 07/10/2026 : la sélection peut contenir des propositions faibles, cochées une à
    une par l'utilisateur (l'écran ne coche d'office que les fortes). Chacune doit être encore
    « Proposée » et s'équilibrer (même montant, sens opposé) ; sinon rien n'est validé.
    """
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
                f"La correspondance n° {match.id} n'est plus proposée (statut : {match.statut}) : "
                "rien n'a été validé, rechargez la liste."
            )
        try:
            _check_amounts(db, match)
        except ConflictError as error:
            raise ConflictError(
                f"Correspondance n° {match.id} : {error.message} Rien n'a été validé."
            ) from error
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
            apres={
                **_snapshot(match),
                "en_lot": True,
                "forte": match.score is not None and match.score >= seuil,
            },
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
    _release(db, match, "Rejetée", _clean_comment(commentaire), acteur_id)
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
    _, entry_ids = _members(match)
    if any(db.get(AccountingEntry, i).origine == "SIMTIS" for i in entry_ids):
        raise ConflictError(ECRITURE_SIMTIS)
    avant = _snapshot(match)
    _release(db, match, "Annulée", texte, acteur_id)
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


def release_pending_matches(
    db: Session,
    *,
    transaction_id: int | None,
    entry_id: int | None,
    motif: str,
    acteur_id: int,
    ip: str | None,
) -> list[int]:
    """Rejette (et trace) les propositions en attente qui contiennent l'opération ou l'écriture.

    Un rapprochement validé n'est jamais défait ici : 409, à annuler d'abord. Ne valide pas la
    transaction ; retourne les identifiants des propositions rejetées.
    """
    actives = repo.active_matches_of(db, transaction_id=transaction_id, entry_id=entry_id)
    for active in actives:
        if active.statut == "Validée":
            tx_ids, _ = _members(active)
            quoi = "L'opération" if transaction_id in tx_ids else "L'écriture"
            raise ConflictError(f"{quoi} est déjà rapprochée : annulez d'abord ce rapprochement.")
    remplacees = []
    for active in actives:
        avant = _snapshot(active)
        _release(db, active, "Rejetée", motif, acteur_id)
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
    return remplacees


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
    if tx.montant == 0 or tx.montant != -montant_rapprochement(entry):
        raise ConflictError(
            "Les montants doivent être égaux, en sens opposé (un crédit en banque correspond à "
            "un débit dans Sage)."
        )
    if "Écart" in (tx.statut, entry.statut):
        raise ConflictError("Une ligne en écart se traite dans l'écran Écarts.")
    type_tx, type_ec = type_operation(tx.libelle), type_ecriture(entry.libelle)
    if type_tx and type_ec and type_tx != type_ec:
        raise ConflictError(
            f"Une opération {type_tx} ne se rapproche pas d'une écriture {type_ec}."
        )

    remplacees = release_pending_matches(
        db,
        transaction_id=tx.id,
        entry_id=entry.id,
        motif="Remplacée par un rapprochement manuel.",
        acteur_id=acteur_id,
        ip=ip,
    )

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
                accounting_entry_id=entry.id,
                montant_affecte=abs(montant_rapprochement(entry)),
                actif=True,
            ),
        ],
    )
    repo.add(db, match)
    db.flush()
    _validate(db, match, acteur_id)
    snapshot = _snapshot(match)
    # Les opérations qui convoitaient la même écriture sont départagées à nouveau (08/10/2026) :
    # relance du moteur sur ce compte, autour des deux lignes rapprochées
    regles = grille(db)
    marge = timedelta(days=regles.fenetre_jours)
    moteur = _engine(
        db,
        company,
        [tx.bank_account_id],
        min(tx.date_operation, entry.date_ecriture) - marge,
        max(tx.date_operation, entry.date_ecriture) + marge,
        regles,
    )
    audit_service.log(
        db,
        user_id=acteur_id,
        action="rapprochement_manuel",
        entite=ENTITE,
        entite_id=match.id,
        apres={
            **snapshot,
            "propositions_remplacees": remplacees,
            "relance": {
                "propositions": len(moteur.resultat.propositions),
                "operations_ambigues": len(moteur.resultat.operations_ambigues),
            },
        },
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
    decide_par: str | None = None
    # Critères de la grille actuelle : le détail affiche ceux-ci, plus ceux qui ont rapporté des points
    actifs: tuple[str, ...] = ()
    # Une autre écriture (ou opération) à moins de `ecart_ambiguite` points (08/10/2026)
    score_second: Decimal | None = None
    concurrente_proche: bool = False
    # Toutes les opérations (une seule en 1 → 1, plusieurs pour un groupe N → 1), avec leur banque
    transactions: list[tuple[BankTransaction, str]] = field(default_factory=list)


@dataclass
class TransactionsPage:
    total: int
    page: int
    taille: int
    par_statut: dict[str, int]
    operations: list[tuple[BankTransaction, str, ReconciliationMatch | None]]
    # Écart ouvert de chaque opération de la page qui en a un (P12)
    ecarts: dict[int, int]
    # Frais bancaires non rapprochés du filtre : nombre et total (12/10/2026)
    a_comptabiliser: int = 0
    total_a_comptabiliser: Decimal = Decimal(0)


@dataclass
class Candidate:
    entry: AccountingEntry
    bank_code: str | None
    score: Score
    rejetee: bool
    proposee_ailleurs: bool
    actifs: tuple[str, ...] = ()


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
    sans_a_verifier: bool = False,
    a_comptabiliser: bool = False,
    type_operation: str | None = None,
) -> TransactionsPage:
    """Volet « Transactions bancaires » : 50 par page ; le décompte par statut porte sur tout le
    filtre, hors filtre de statut.

    `sans_a_verifier` : les opérations « À vérifier » ne sont pas listées (elles se traitent dans
    l'onglet Propositions, décision du 07/10/2026) ; elles restent comptées dans `par_statut`.
    """
    company = _company(db, company_id)
    _check_period(date_from, date_to)
    query = repo.transactions_query(
        company.id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
        type_operation=type_operation,
    )
    par_statut = repo.count_by_status(db, query)
    # Frais bancaires non rapprochés : « À comptabiliser », comptés à part (12/10/2026)
    nb_frais, total_frais = repo.a_comptabiliser(db, query)
    par_statut["Non rapprochée"] = par_statut.get("Non rapprochée", 0) - nb_frais
    listed = repo.without_status(query, "À vérifier") if sans_a_verifier else query
    if a_comptabiliser:
        listed = listed.where(BankTransaction.statut == "Non rapprochée", repo.frais_bancaire())
        statut = None
    elif statut == "Non rapprochée":
        listed = listed.where(~repo.frais_bancaire())
    total, rows = repo.page_of_transactions(
        db, listed, statut=statut, offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE
    )
    matches = repo.active_match_by_transaction(db, [tx.id for tx, _ in rows])
    return TransactionsPage(
        total=total,
        page=page,
        taille=PAGE_SIZE,
        par_statut=par_statut,
        a_comptabiliser=nb_frais,
        total_a_comptabiliser=total_frais,
        operations=[(tx, code, matches.get(tx.id)) for tx, code in rows],
        ecarts=discrepancy_repository.open_discrepancy_by_transaction(
            db, [tx.id for tx, _ in rows]
        ),
    )


def _views(db: Session, matches: list[ReconciliationMatch], regles: Grille) -> list[MatchView]:
    tx_ids = {i.bank_transaction_id for m in matches for i in m.items if i.bank_transaction_id}
    entry_ids = {i.accounting_entry_id for m in matches for i in m.items if i.accounting_entry_id}
    transactions = repo.transactions_with_bank(db, tx_ids)
    entries = repo.entries_with_bank(db, entry_ids)
    names = repo.user_names(
        db,
        {m.valide_par_id for m in matches if m.valide_par_id}
        | {m.decide_par_id for m in matches if m.decide_par_id},
    )
    views = []
    for match in matches:
        second = score_second(match)
        # Groupe N → 1 : toutes ses opérations ; la principale (la plus grosse) est affichée en tête
        lignes = [transactions[i.bank_transaction_id] for i in match.items if i.bank_transaction_id]
        lignes.sort(key=lambda ligne: (-abs(ligne[0].montant), ligne[0].id))
        tx, code = lignes[0]
        entry_id = next(i.accounting_entry_id for i in match.items if i.accounting_entry_id)
        entry, entry_code = entries[entry_id]
        views.append(
            MatchView(
                match=match,
                transaction=tx,
                transactions=lignes,
                bank_code=code,
                entry=entry,
                entry_bank_code=entry_code,
                valide_par=names.get(match.valide_par_id) if match.valide_par_id else None,
                decide_par=names.get(match.decide_par_id) if match.decide_par_id else None,
                forte=match.score is not None and match.score >= regles.seuil_fort,
                actifs=regles.criteres_actifs,
                score_second=second,
                concurrente_proche=second is not None
                and match.score is not None
                and match.score - second < regles.ecart_ambiguite,
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
    type_operation: str | None = None,
) -> tuple[Decimal, list[MatchView]]:
    """Correspondances 1→1 de la société (par défaut celles en attente), avec le seuil « forte »."""
    company = _company(db, company_id)
    _check_period(date_from, date_to)
    regles = grille(db)
    matches = repo.matches_of_period(
        db,
        company.id,
        statut=statut,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
    )
    views = _views(db, matches, regles)
    if type_operation is not None:
        # Type de l'opération principale (la seule en 1 → 1, la plus grosse d'un groupe)
        voulu = None if type_operation == AUTRE else type_operation
        views = [view for view in views if _type_de(view.transaction.libelle) == voulu]
    return regles.seuil_fort, views


@dataclass
class HistoryPage:
    total: int
    page: int
    taille: int
    par_statut: dict[str, int]
    seuil_fort: Decimal
    decisions: list[MatchView]


def list_history(
    db: Session,
    company_id: int,
    *,
    statut: str | None = None,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
) -> HistoryPage:
    """Historique des décisions (validées, rejetées, annulées), de la plus récente à la plus
    ancienne, 50 par page ; le décompte par statut porte sur tout le filtre, hors statut."""
    company = _company(db, company_id)
    _check_period(date_from, date_to)
    regles = grille(db)
    query = repo.decisions_query(
        company.id, bank_account_id=bank_account_id, date_from=date_from, date_to=date_to
    )
    total, matches = repo.page_of_decisions(
        db, query, statut=statut, offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE
    )
    return HistoryPage(
        total=total,
        page=page,
        taille=PAGE_SIZE,
        par_statut=repo.count_decisions_by_status(db, query),
        seuil_fort=regles.seuil_fort,
        decisions=_views(db, matches, regles),
    )


def get_match_view(db: Session, match_id: int) -> MatchView:
    match = repo.get_match(db, match_id)
    if match is None:
        raise NotFoundError("Correspondance introuvable.")
    return _views(db, [match], grille(db))[0]


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
    fenetre = timedelta(days=max(regles.fenetre_jours, regles.fenetre_numero_jours))
    entries = repo.candidate_entries(
        db, tx, account.company_id, min(jours) - fenetre, max(jours) + fenetre
    )
    operation = _operation(tx)
    # Seules les écritures comparables sont lues plus loin : la fenêtre de 180 jours (même numéro)
    # ramène des centaines d'écritures par opération (13/10/2026, 20 s pour 50 ambiguës)
    comparables = [
        (entry, ecriture)
        for entry in entries
        if comparable(operation, ecriture := _ecriture(entry), regles)
    ]
    rejetees = repo.rejected_pairs(db, account.company_id)
    actives = repo.active_matches_by_entry(db, [entry.id for entry, _ in comparables])
    codes = repo.entries_with_bank(db, {entry.id for entry, _ in comparables})
    scored = []
    for entry, ecriture in comparables:
        active = actives.get(entry.id)
        scored.append(
            Candidate(
                entry=entry,
                bank_code=codes[entry.id][1],
                score=score(operation, ecriture, regles),
                rejetee=(tx.id, entry.id) in rejetees,
                proposee_ailleurs=active is not None and tx.id not in _members(active)[0],
                actifs=regles.criteres_actifs,
            )
        )
    scored.sort(key=lambda item: (-item.score.total, item.entry.date_ecriture, item.entry.id))
    bank_code = repo.transactions_with_bank(db, {tx.id})[tx.id][1]
    return tx, bank_code, scored[:NB_CANDIDATS], regles.seuil_proposition, regles.seuil_fort


# Opérations ambiguës par page ; le total porte sur tout le filtre (08/10/2026)
PAGE_AMBIGUES = 50


@dataclass
class AmbiguousView:
    transaction: BankTransaction
    bank_code: str
    candidats: list[Candidate]


def list_ambiguous(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    type_operation: str | None = None,
) -> tuple[Decimal, int, list[AmbiguousView]]:
    """Opérations ambiguës de la période (« À vérifier » sans proposition), chacune avec ses
    écritures candidates au-dessus du seuil de proposition, la meilleure d'abord (hors paires déjà
    rejetées). L'utilisateur en choisit une : rapprochement manuel. Retourne aussi le seuil
    « forte »."""
    company = _company(db, company_id)
    _check_period(date_from, date_to)
    regles = grille(db)
    views = []
    total, transactions = repo.ambiguous_transactions(
        db,
        company.id,
        bank_account_id=bank_account_id,
        date_from=date_from,
        date_to=date_to,
        offset=(page - 1) * PAGE_AMBIGUES,
        limit=PAGE_AMBIGUES,
        type_operation=type_operation,
    )
    for tx in transactions:
        _, bank_code, items, seuil_proposition, _ = candidates(db, tx.id)
        views.append(
            AmbiguousView(
                transaction=tx,
                bank_code=bank_code,
                candidats=[
                    item
                    for item in items
                    if item.score.total >= seuil_proposition and not item.rejetee
                ],
            )
        )
    return regles.seuil_fort, total, views


# --- Export du lettrage (14/10/2026) ----------------------------------------------------------------

LETTRAGE_HEADERS = (
    "Code",
    "Côté",
    "Banque",
    "Date",
    "Journal",
    "N° pièce",
    "Libellé",
    "Débit",
    "Crédit",
    "Type",
    "Origine",
    "Score",
    "Validé par",
    "Validé le",
    # Compte en devise (14/10/2026) : le montant devise de la ligne Sage, celui rapproché
    "Montant devise",
)
_LARGEURS = (16, 8, 8, 12, 9, 16, 44, 14, 14, 6, 12, 7, 20, 17, 14)


def _heure_locale(moment: datetime | None) -> datetime | None:
    """Excel ne connaît pas les fuseaux : l'heure du Maroc, sans fuseau."""
    return moment.astimezone(BUSINESS_TZ).replace(tzinfo=None) if moment else None


def export_lettrage(
    db: Session,
    company_id: int,
    *,
    bank_account_id: int | None,
    date_from: date | None,
    date_to: date | None,
    acteur_id: int,
    ip: str | None,
) -> tuple[str, bytes, int]:
    """Lettrage du filtre de l'historique en classeur Excel : tous les rapprochements VALIDÉS dont
    une opération est dans la période (et du compte, s'il est donné). Une ligne par élément,
    regroupées par code : les opérations du relevé, puis les écritures Sage ; chaque code
    s'équilibre (débit d'un côté = crédit de l'autre). Ligne de total en bas."""
    company = _company(db, company_id)
    _check_period(date_from, date_to)
    if date_from and date_to and (date_to - date_from).days > PERIODE_MAX_JOURS:
        raise ConflictError("La période ne peut pas dépasser 5 ans.")
    query = repo.decisions_query(
        company.id, bank_account_id=bank_account_id, date_from=date_from, date_to=date_to
    )
    matches = repo.validated_matches(db, query)
    tx_ids = {i.bank_transaction_id for m in matches for i in m.items if i.bank_transaction_id}
    entry_ids = {i.accounting_entry_id for m in matches for i in m.items if i.accounting_entry_id}
    transactions = repo.transactions_with_bank(db, tx_ids)
    entries = repo.entries_with_bank(db, entry_ids)
    noms = repo.user_names(db, {m.valide_par_id for m in matches if m.valide_par_id})

    def premiere_date(match: ReconciliationMatch) -> date:
        return min(
            transactions[i.bank_transaction_id][0].date_operation
            for i in match.items
            if i.bank_transaction_id
        )

    matches.sort(key=lambda m: (premiere_date(m), m.code or "", m.id))

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lettrage"
    sheet.append(LETTRAGE_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    total_debit = total_credit = Decimal("0.00")
    for match in matches:
        commun = [
            match.type,
            match.origine,
            match.score,
            noms.get(match.valide_par_id),
            _heure_locale(match.valide_le),
        ]
        operations = sorted(
            (transactions[i.bank_transaction_id] for i in match.items if i.bank_transaction_id),
            key=lambda row: (row[0].date_operation, row[0].id),
        )
        ecritures = sorted(
            (entries[i.accounting_entry_id] for i in match.items if i.accounting_entry_id),
            key=lambda row: (row[0].date_ecriture, row[0].id),
        )
        for tx, banque in operations:
            sheet.append(
                [match.code, "Banque", banque, tx.date_operation, None, tx.reference, tx.libelle,
                 tx.debit or None, tx.credit or None, *commun]
            )  # fmt: skip
            total_debit += tx.debit
            total_credit += tx.credit
        for entry, banque in ecritures:
            sheet.append(
                [match.code, "Sage", banque, entry.date_ecriture, entry.journal,
                 entry.numero_piece, entry.libelle, entry.debit or None, entry.credit or None,
                 *commun, entry.montant_devise]
            )  # fmt: skip
            total_debit += entry.debit
            total_credit += entry.credit
    sheet.append(
        [f"Total : {len(matches)} rapprochement{'s' if len(matches) > 1 else ''}", None, None,
         None, None, None, None, total_debit, total_credit]
    )  # fmt: skip
    for cell in sheet[sheet.max_row]:
        cell.font = Font(bold=True)
    for row in sheet.iter_rows(min_row=2):
        row[3].number_format = "DD/MM/YYYY"
        row[7].number_format = row[8].number_format = "#,##0.00"
        row[13].number_format = "DD/MM/YYYY HH:MM"
        row[14].number_format = "#,##0.00"
    for index, largeur in enumerate(_LARGEURS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = largeur
    sheet.freeze_panes = "A2"
    buffer = BytesIO()
    workbook.save(buffer)

    audit_service.log(
        db,
        user_id=acteur_id,
        action="export_lettrage",
        entite="company",
        entite_id=company.id,
        apres={
            "compte": bank_account_id,
            "du": date_from,
            "au": date_to,
            "rapprochements": len(matches),
        },
        ip=ip,
    )
    db.commit()
    banque = (
        repo.bank_code_of_account(db, bank_account_id) if bank_account_id is not None else "tous"
    )
    nom = f"lettrage-{banque}-{date_from or 'debut'}-{date_to or business_today()}.xlsx"
    return nom, buffer.getvalue(), len(matches)
