"""Les contraintes de la base protègent les données, même si le code applicatif se trompe.

Pour chaque règle : un cas refusé (avec le nom de la contrainte) et, quand c'est utile, un cas voisin
accepté, pour prouver que la règle ne refuse pas trop.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import DataError

from app.models import (
    AuditLog,
    BalanceCheck,
    BankAccountBalance,
    BankStatement,
    CashForecast,
    Discrepancy,
    ExchangeRate,
    ImportBatch,
    ReconciliationMatch,
    ReconciliationMatchItem,
)
from tests.helpers import (
    World,
    assert_rejected,
    build_account,
    build_bank,
    build_company,
    build_entry,
    build_transaction,
    build_user,
    make_world,
    save,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def world(db) -> World:
    return make_world(db)


# --- Comptes bancaires ---------------------------------------------------------------------------


def test_account_number_must_be_unique(db, world):
    duplicate = build_account(world.company, world.bank, numero=world.account.numero)

    assert_rejected(db, "uq_bank_accounts_numero", duplicate)


def test_authorized_credit_cannot_be_negative(db, world):
    account = build_account(world.company, world.bank, credit_autorise=Decimal("-1"))

    assert_rejected(db, "ck_bank_accounts_credit_autorise_positif", account)


def test_dh_convertible_account_must_be_in_mad(db, world):
    in_eur = build_account(world.company, world.bank, type_compte="DH convertible", devise="EUR")

    assert_rejected(db, "ck_bank_accounts_dh_convertible_en_mad", in_eur)


def test_dh_convertible_account_in_mad_is_accepted(db, world):
    account = build_account(world.company, world.bank, type_compte="DH convertible", devise="MAD")

    save(db, account)


def test_unknown_account_type_is_rejected(db, world):
    account = build_account(world.company, world.bank, type_compte="Épargne")

    assert_rejected(db, "ck_bank_accounts_type_compte", account)


# --- Soldes journaliers (lignes « facilité de caisse ») ------------------------------------------


def test_one_balance_per_account_and_day(db, world):
    save(
        db,
        BankAccountBalance(
            bank_account_id=world.account.id, date_solde=date(2026, 9, 30), solde=Decimal("10")
        ),
    )
    same_day = BankAccountBalance(
        bank_account_id=world.account.id, date_solde=date(2026, 9, 30), solde=Decimal("20")
    )

    assert_rejected(db, "uq_bank_account_balances_compte_date", same_day)


def test_balance_needs_at_least_one_amount(db, world):
    empty = BankAccountBalance(bank_account_id=world.account.id, date_solde=date(2026, 9, 30))

    assert_rejected(db, "ck_bank_account_balances_un_montant_renseigne", empty)


def test_used_credit_can_exceed_authorized_credit(db, world):
    """Un dépassement de ligne doit pouvoir être enregistré : c'est l'objet de la colonne DEPASSEMENT."""
    world.account.credit_autorise = Decimal("100000")
    balance = BankAccountBalance(
        bank_account_id=world.account.id,
        date_solde=date(2026, 9, 30),
        solde=Decimal("-50"),
        credit_utilise=Decimal("150000"),
    )

    save(db, balance)


def test_used_credit_cannot_be_negative(db, world):
    balance = BankAccountBalance(
        bank_account_id=world.account.id, date_solde=date(2026, 9, 30), credit_utilise=Decimal("-1")
    )

    assert_rejected(db, "ck_bank_account_balances_credit_utilise_positif", balance)


def test_a_balance_can_be_negative(db, world):
    """Un compte à découvert a un solde négatif."""
    save(
        db,
        BankAccountBalance(
            bank_account_id=world.account.id,
            date_solde=date(2026, 9, 30),
            solde=Decimal("-1500.25"),
        ),
    )


# --- Taux de change ------------------------------------------------------------------------------


def test_one_exchange_rate_per_currency_and_day(db, world):
    save(db, ExchangeRate(devise="EUR", taux=Decimal("10.8"), date_taux=date(2026, 9, 30)))
    duplicate = ExchangeRate(devise="EUR", taux=Decimal("10.9"), date_taux=date(2026, 9, 30))

    assert_rejected(db, "uq_exchange_rates_devise_date", duplicate)


def test_exchange_rate_must_be_positive(db, world):
    zero = ExchangeRate(devise="EUR", taux=Decimal("0"), date_taux=date(2026, 9, 30))

    assert_rejected(db, "ck_exchange_rates_taux_positif", zero)


# --- Transactions bancaires ----------------------------------------------------------------------


def test_same_line_cannot_be_imported_twice_in_an_account(db, world):
    save(db, build_transaction(world.statement, hash_ligne="abc"))
    again = build_transaction(world.statement, hash_ligne="abc")

    assert_rejected(db, "uq_bank_transactions_compte_hash", again)


def test_same_line_hash_is_allowed_in_another_account(db, world):
    other_account = save(db, build_account(world.company, world.bank))
    other_statement = save(db, BankStatement(bank_account_id=other_account.id))
    save(db, build_transaction(world.statement, hash_ligne="abc"))

    save(db, build_transaction(other_statement, hash_ligne="abc"))


def test_transaction_debit_cannot_be_negative(db, world):
    tx = build_transaction(
        world.statement, debit=Decimal("-5"), credit=Decimal("0"), montant=Decimal("5")
    )

    assert_rejected(db, "ck_bank_transactions_debit_positif", tx)


def test_transaction_credit_cannot_be_negative(db, world):
    tx = build_transaction(world.statement, credit=Decimal("-5"), montant=Decimal("-5"))

    assert_rejected(db, "ck_bank_transactions_credit_positif", tx)


def test_transaction_amount_must_equal_credit_minus_debit(db, world):
    tx = build_transaction(
        world.statement, credit=Decimal("100"), debit=Decimal("0"), montant=Decimal("99")
    )

    assert_rejected(db, "ck_bank_transactions_montant_coherent", tx)


def test_debit_transaction_has_negative_amount(db, world):
    save(
        db,
        build_transaction(
            world.statement, debit=Decimal("12500"), credit=Decimal("0"), montant=Decimal("-12500")
        ),
    )


def test_transaction_status_must_be_known(db, world):
    tx = build_transaction(world.statement, statut="Validée")

    assert_rejected(db, "ck_bank_transactions_statut", tx)


def test_new_transaction_is_not_reconciled_by_default(db, world):
    tx = save(db, build_transaction(world.statement))
    db.refresh(tx)

    assert tx.statut == "Non rapprochée"


# --- Écritures comptables ------------------------------------------------------------------------


def test_same_entry_cannot_be_imported_twice_for_a_company(db, world):
    save(db, build_entry(world.company, hash_ligne="e1"))
    again = build_entry(world.company, hash_ligne="e1")

    assert_rejected(db, "uq_accounting_entries_societe_hash", again)


def test_same_entry_hash_is_allowed_for_another_company(db, world):
    other = save(db, build_company())
    save(db, build_entry(world.company, hash_ligne="e1"))

    save(db, build_entry(other, hash_ligne="e1"))


def test_entry_amount_must_equal_credit_minus_debit(db, world):
    entry = build_entry(world.company, montant=Decimal("1"))

    assert_rejected(db, "ck_accounting_entries_montant_coherent", entry)


def test_entry_status_must_be_known(db, world):
    entry = build_entry(world.company, statut="Inconnue")

    assert_rejected(db, "ck_accounting_entries_statut", entry)


# --- Imports de fichiers -------------------------------------------------------------------------


def import_batch(world: World, *, statut: str, company_id: int | None = None) -> ImportBatch:
    return ImportBatch(
        type="Banque",
        company_id=company_id or world.company.id,
        fichier_nom="releve.xlsx",
        fichier_hash="f" * 64,
        statut=statut,
    )


def test_a_file_cannot_be_confirmed_twice(db, world):
    save(db, import_batch(world, statut="Confirmé"))
    again = import_batch(world, statut="Confirmé")

    assert_rejected(db, "uq_import_batches_fichier_confirme", again)


def test_an_analysed_file_can_be_uploaded_again(db, world):
    """Seule la confirmation est unique : on peut analyser plusieurs fois avant de confirmer."""
    save(db, import_batch(world, statut="Confirmé"))

    save(db, import_batch(world, statut="Analysé"), import_batch(world, statut="Analysé"))


def test_the_same_file_can_be_confirmed_for_another_company(db, world):
    other = save(db, build_company())
    save(db, import_batch(world, statut="Confirmé"))

    save(db, import_batch(world, statut="Confirmé", company_id=other.id))


# --- Rapprochement -------------------------------------------------------------------------------


def test_match_item_needs_exactly_one_link(db, world):
    match = save(db, ReconciliationMatch(company_id=world.company.id, type="1-1"))
    tx = save(db, build_transaction(world.statement))
    entry = save(db, build_entry(world.company))

    no_link = ReconciliationMatchItem(match_id=match.id, montant_affecte=Decimal("100"))
    both_links = ReconciliationMatchItem(
        match_id=match.id,
        bank_transaction_id=tx.id,
        accounting_entry_id=entry.id,
        montant_affecte=Decimal("100"),
    )

    assert_rejected(db, "ck_reconciliation_match_items_un_seul_lien", no_link)
    assert_rejected(db, "ck_reconciliation_match_items_un_seul_lien", both_links)


def test_match_item_with_one_link_is_accepted(db, world):
    match = save(db, ReconciliationMatch(company_id=world.company.id, type="1-N"))
    tx = save(db, build_transaction(world.statement))
    entry = save(db, build_entry(world.company))

    save(
        db,
        ReconciliationMatchItem(
            match_id=match.id, bank_transaction_id=tx.id, montant_affecte=Decimal("100")
        ),
        ReconciliationMatchItem(
            match_id=match.id, accounting_entry_id=entry.id, montant_affecte=Decimal("100")
        ),
    )


def test_match_item_amount_must_be_positive(db, world):
    match = save(db, ReconciliationMatch(company_id=world.company.id, type="1-1"))
    tx = save(db, build_transaction(world.statement))
    item = ReconciliationMatchItem(
        match_id=match.id, bank_transaction_id=tx.id, montant_affecte=Decimal("0")
    )

    assert_rejected(db, "ck_reconciliation_match_items_montant_affecte_positif", item)


def test_match_type_must_be_known(db, world):
    assert_rejected(
        db,
        "ck_reconciliation_matches_type",
        ReconciliationMatch(company_id=world.company.id, type="2-2"),
    )


def test_match_score_is_between_0_and_100(db, world):
    too_high = ReconciliationMatch(company_id=world.company.id, type="1-1", score=Decimal("100.01"))

    assert_rejected(db, "ck_reconciliation_matches_score_0_100", too_high)


def test_validated_match_must_record_who_validated_and_when(db, world):
    """Le moteur ne fait que proposer : une validation sans validateur est impossible."""
    unsigned = ReconciliationMatch(company_id=world.company.id, type="1-1", statut="Validée")

    assert_rejected(db, "ck_reconciliation_matches_validation_tracee", unsigned)


def test_validated_match_with_validator_is_accepted(db, world):
    signed = ReconciliationMatch(
        company_id=world.company.id,
        type="1-1",
        statut="Validée",
        valide_par_id=world.user.id,
        valide_le=NOW,
    )

    save(db, signed)


# --- Écarts --------------------------------------------------------------------------------------


def discrepancy(world: World, **over) -> Discrepancy:
    return Discrepancy(
        **{
            "company_id": world.company.id,
            "type": "Montant différent",
            "montant": Decimal("50"),
            "date_ecart": date(2026, 9, 30),
            **over,
        }
    )


def test_closed_discrepancy_needs_a_comment(db, world):
    closed = dict(statut="Clôturé", cloture_le=NOW, cloture_par_id=world.user.id)

    assert_rejected(
        db,
        "ck_discrepancies_cloture_avec_commentaire",
        discrepancy(world, commentaire=None, **closed),
    )
    assert_rejected(
        db,
        "ck_discrepancies_cloture_avec_commentaire",
        discrepancy(world, commentaire="   ", **closed),
    )


def test_closed_discrepancy_needs_date_and_person(db, world):
    no_date = discrepancy(
        world, statut="Clôturé", commentaire="Justifié", cloture_par_id=world.user.id
    )
    no_person = discrepancy(world, statut="Clôturé", commentaire="Justifié", cloture_le=NOW)

    assert_rejected(db, "ck_discrepancies_cloture_avec_commentaire", no_date)
    assert_rejected(db, "ck_discrepancies_cloture_avec_commentaire", no_person)


def test_fully_documented_closure_is_accepted(db, world):
    save(
        db,
        discrepancy(
            world,
            statut="Clôturé",
            commentaire="Frais justifiés",
            cloture_le=NOW,
            cloture_par_id=world.user.id,
        ),
    )


def test_open_discrepancy_needs_no_comment(db, world):
    save(db, discrepancy(world, statut="À traiter"))


def test_discrepancy_type_and_status_must_be_known(db, world):
    assert_rejected(db, "ck_discrepancies_type", discrepancy(world, type="Autre chose"))
    assert_rejected(db, "ck_discrepancies_statut", discrepancy(world, statut="Fermé"))


def test_balance_check_status_must_be_known(db, world):
    check = BalanceCheck(
        bank_account_id=world.account.id,
        date_controle=date(2026, 9, 30),
        solde_releve=Decimal("100"),
        solde_enregistre=Decimal("100"),
        ecart=Decimal("0"),
        statut="Bon",
    )

    assert_rejected(db, "ck_balance_checks_statut", check)


# --- Prévisions ----------------------------------------------------------------------------------


def forecast(world: World, **over) -> CashForecast:
    return CashForecast(
        **{
            "company_id": world.company.id,
            "category_id": world.category.id,
            "sens": "Entrée",
            "date_prevue": date(2026, 10, 1),
            "montant": Decimal("450000"),
            **over,
        }
    )


def test_forecast_without_bank_is_a_day_level_amount(db, world):
    saved = save(db, forecast(world, bank_id=None))

    assert saved.bank_id is None


def test_forecast_for_a_bank_is_accepted(db, world):
    save(db, forecast(world, bank_id=world.bank.id))


def test_forecast_amount_must_be_positive(db, world):
    assert_rejected(db, "ck_cash_forecasts_montant_positif", forecast(world, montant=Decimal("0")))
    assert_rejected(
        db, "ck_cash_forecasts_montant_positif", forecast(world, montant=Decimal("-10"))
    )


def test_forecast_direction_and_status_must_be_known(db, world):
    assert_rejected(db, "ck_cash_forecasts_sens", forecast(world, sens="Neutre"))
    assert_rejected(db, "ck_cash_forecasts_statut", forecast(world, statut="Terminé"))


def test_realised_forecast_needs_a_realisation_date(db, world):
    assert_rejected(db, "ck_cash_forecasts_realisation_datee", forecast(world, statut="Réalisé"))
    save(db, forecast(world, statut="Réalisé", date_realisation=date(2026, 10, 1)))


# --- Utilisateurs et journal d'audit -------------------------------------------------------------


def test_email_must_be_lowercase(db):
    assert_rejected(db, "ck_users_email_minuscules", build_user(email="Salma@Example.com"))


def test_email_must_be_unique(db):
    save(db, build_user(email="salma@example.com"))

    assert_rejected(db, "uq_users_email", build_user(email="salma@example.com"))


def test_audit_log_accepts_new_entries(db):
    entry = save(
        db,
        AuditLog(
            action="import", entite="bank_statement", entite_id="1", nouvelle_valeur={"lignes": 12}
        ),
    )
    db.refresh(entry)

    assert entry.created_at is not None


def test_audit_log_cannot_be_modified(db):
    save(db, AuditLog(action="import", entite="bank_statement", entite_id="1"))

    assert_rejected(
        db, "audit_logs est en ajout seul", sql="UPDATE audit_logs SET action = 'falsifié'"
    )


def test_audit_log_cannot_be_deleted(db):
    save(db, AuditLog(action="import", entite="bank_statement", entite_id="1"))

    assert_rejected(db, "audit_logs est en ajout seul", sql="DELETE FROM audit_logs")


def test_audit_log_cannot_be_truncated(db):
    assert_rejected(db, "audit_logs est en ajout seul", sql="TRUNCATE audit_logs")


def test_audit_log_survives_user_deletion(db):
    """Le journal n'a pas de clé étrangère vers users : supprimer un utilisateur ne l'efface pas."""
    user = save(db, build_user())
    save(db, AuditLog(user_id=user.id, action="login", entite="user", entite_id=str(user.id)))

    db.delete(user)
    db.flush()

    assert db.query(AuditLog).filter_by(action="login").count() == 1


# --- Précision des montants ----------------------------------------------------------------------


def test_large_amount_is_stored_exactly(db, world):
    exact = Decimal(
        "1234567890123456.78"
    )  # 16 chiffres avant la virgule, 2 après : le maximum de NUMERIC(18,2)
    balance = save(
        db,
        BankAccountBalance(
            bank_account_id=world.account.id, date_solde=date(2026, 9, 30), solde=exact
        ),
    )

    db.expire(balance)

    assert balance.solde == exact
    assert isinstance(balance.solde, Decimal)


def test_amounts_add_exactly_unlike_floats(db, world):
    balance = save(
        db,
        BankAccountBalance(
            bank_account_id=world.account.id, date_solde=date(2026, 9, 30), solde=Decimal("0.10")
        ),
    )
    other = save(
        db,
        BankAccountBalance(
            bank_account_id=world.account.id, date_solde=date(2026, 9, 29), solde=Decimal("0.20")
        ),
    )

    db.expire_all()

    assert balance.solde + other.solde == Decimal("0.30")  # avec des float : 0.30000000000000004


def test_amount_beyond_18_digits_is_refused(db, world):
    too_big = BankAccountBalance(
        bank_account_id=world.account.id,
        date_solde=date(2026, 9, 30),
        solde=Decimal("12345678901234567.00"),
    )

    with pytest.raises(DataError):
        with db.begin_nested():
            db.add(too_big)
            db.flush()


def test_interest_rate_keeps_six_decimals(db, world):
    account = save(db, build_account(world.company, world.bank, taux_interet=Decimal("0.045125")))

    db.expire(account)

    assert account.taux_interet == Decimal("0.045125")


def test_two_banks_cannot_share_a_code(db):
    save(db, build_bank(code="AWB"))

    assert_rejected(db, "uq_banks_code", build_bank(code="AWB"))
