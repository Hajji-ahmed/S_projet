"""Accès par société (19/11/2026) : une personne limitée à certaines sociétés ne voit ni ne
modifie rien des autres, par paramètre, chemin, corps ou formulaire ; l'Administrateur voit tout ;
aucune société cochée = toutes."""

from dataclasses import dataclass

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, BankAccount, BankStatement, BankTransaction, User, UserCompany
from app.services import audit_service
from app.services.acces_societe_service import REFUS, RESOLVEURS
from tests.helpers import (
    bearer,
    build_account,
    build_bank,
    build_company,
    build_entry,
    build_transaction,
    login,
    make_auth_user,
    make_currencies,
    save,
)

TOUS_LES_METIERS = ("TRESORERIE", "COMPTABLE", "RESPONSABLE")


@dataclass
class Societe:
    id: int
    account: BankAccount
    statement: BankStatement
    transaction: BankTransaction
    entry_id: int


def _societe(db, bank) -> Societe:
    company = save(db, build_company())
    account = save(db, build_account(company, bank))
    statement = save(db, BankStatement(bank_account_id=account.id))
    transaction = save(db, build_transaction(statement))
    entry = save(db, build_entry(company, bank_account_id=account.id))
    return Societe(company.id, account, statement, transaction, entry.id)


@pytest.fixture
def societes(reference):
    make_currencies(reference)
    bank = save(reference, build_bank())
    return _societe(reference, bank), _societe(reference, bank)


def _limiter(db, user: User, *company_ids: int) -> None:
    for company_id in company_ids:
        db.add(UserCompany(user_id=user.id, company_id=company_id))
    db.flush()


@pytest.fixture
def limite(client, reference, societes):
    """Personne aux droits métier complets, limitée à la société A."""
    a, _b = societes
    user = make_auth_user(reference, *TOUS_LES_METIERS, email="limite@example.com")
    _limiter(reference, user, a.id)
    return user, bearer(login(client, "limite@example.com"))


def _refuse(response) -> None:
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == REFUS


# --- Liste des sociétés et utilisateur connecté ---------------------------------------------------


def test_the_header_lists_only_the_allowed_companies(client, societes, limite):
    a, b = societes
    _user, headers = limite

    ids = {company["id"] for company in client.get("/api/companies", headers=headers).json()}
    me = client.get("/api/auth/me", headers=headers).json()

    assert a.id in ids and b.id not in ids
    assert me["societes"] == [a.id]


def test_without_any_company_ticked_a_person_sees_every_company(client, reference, societes):
    a, b = societes
    make_auth_user(reference, *TOUS_LES_METIERS, email="libre@example.com")
    headers = bearer(login(client, "libre@example.com"))

    ids = {company["id"] for company in client.get("/api/companies", headers=headers).json()}

    assert {a.id, b.id} <= ids
    assert client.get("/api/auth/me", headers=headers).json()["societes"] is None
    assert client.get(f"/api/accounts/{b.account.id}", headers=headers).status_code == 200


def test_the_administrator_always_sees_every_company(client, reference, societes):
    a, b = societes
    admin = make_auth_user(reference, "ADMIN", email="admin.limite@example.com")
    _limiter(reference, admin, a.id)
    headers = bearer(login(client, "admin.limite@example.com"))

    ids = {company["id"] for company in client.get("/api/companies", headers=headers).json()}

    assert b.id in ids
    response = client.get(f"/api/position/banques?company_id={b.id}", headers=headers)
    assert response.status_code == 200


def test_a_new_restriction_applies_at_the_next_request(client, reference, societes):
    _a, b = societes
    user = make_auth_user(reference, *TOUS_LES_METIERS, email="bientot@example.com")
    headers = bearer(login(client, "bientot@example.com"))
    assert client.get(f"/api/accounts/{b.account.id}", headers=headers).status_code == 200

    _limiter(reference, user, _a.id)

    _refuse(client.get(f"/api/accounts/{b.account.id}", headers=headers))


# --- Paramètres de requête et de chemin (dépendance de protected_router) -------------------------


def test_a_company_in_the_query_must_be_allowed(client, societes, limite):
    a, b = societes
    _user, headers = limite

    assert (
        client.get(f"/api/position/banques?company_id={a.id}", headers=headers).status_code == 200
    )
    _refuse(client.get(f"/api/position/banques?company_id={b.id}", headers=headers))
    _refuse(client.get(f"/api/dashboard?company_id={b.id}", headers=headers))
    _refuse(client.get(f"/api/accounts?company_id={b.id}", headers=headers))
    _refuse(client.get(f"/api/reconciliation/transactions?company_id={b.id}", headers=headers))


def test_an_account_of_another_company_is_refused_even_with_an_allowed_company(
    client, societes, limite
):
    a, b = societes
    _user, headers = limite

    _refuse(
        client.get(
            f"/api/reconciliation/transactions?company_id={a.id}&bank_account_id={b.account.id}",
            headers=headers,
        )
    )
    _refuse(client.get(f"/api/accounts/{b.account.id}", headers=headers))
    _refuse(client.get(f"/api/statements/accounts/{b.account.id}", headers=headers))
    assert client.get(f"/api/accounts/{a.account.id}", headers=headers).status_code == 200


def test_statements_operations_and_entries_of_another_company_are_refused(client, societes, limite):
    a, b = societes
    _user, headers = limite

    _refuse(client.get(f"/api/statements/{b.statement.id}/transactions", headers=headers))
    _refuse(
        client.patch(
            f"/api/statements/transactions/{b.transaction.id}",
            json={"commentaire": "x"},
            headers=headers,
        )
    )
    _refuse(client.get(f"/api/accounting/entries/{b.entry_id}", headers=headers))
    _refuse(
        client.get(
            f"/api/reconciliation/candidates?transaction_id={b.transaction.id}", headers=headers
        )
    )
    assert client.get(f"/api/accounting/entries/{a.entry_id}", headers=headers).status_code == 200


def test_an_unknown_id_still_gives_not_found(client, limite):
    _user, headers = limite

    assert client.get("/api/accounts/999999999", headers=headers).status_code == 404


# --- Corps JSON et formulaires --------------------------------------------------------------------


def test_json_bodies_naming_another_company_are_refused(client, societes, limite):
    a, b = societes
    _user, headers = limite

    _refuse(
        client.post(
            "/api/reconciliation/run",
            json={"company_id": b.id, "du": "2026-09-01", "au": "2026-09-30"},
            headers=headers,
        )
    )
    _refuse(
        client.post(
            "/api/reconciliation/run",
            json={
                "company_id": a.id,
                "bank_account_id": b.account.id,
                "du": "2026-09-01",
                "au": "2026-09-30",
            },
            headers=headers,
        )
    )
    _refuse(
        client.post(
            "/api/reconciliation/matches",
            json={"transaction_id": b.transaction.id, "ecriture_id": b.entry_id},
            headers=headers,
        )
    )
    _refuse(
        client.post(
            "/api/reconciliation/transactions/aucune-ecriture",
            json={"ids": [a.transaction.id, b.transaction.id]},
            headers=headers,
        )
    )
    _refuse(
        client.post(
            "/api/reconciliation/entries/aucune-operation",
            json={"ids": [b.entry_id]},
            headers=headers,
        )
    )
    _refuse(
        client.post(
            "/api/frais/manuelle",
            json={
                "company_id": a.id,
                "transaction_ids": [b.transaction.id],
                "libelle": "FRAIS",
                "compte": "61470000",
            },
            headers=headers,
        )
    )
    _refuse(
        client.post(
            "/api/statements/transactions/supprimer-en-cours",
            json={"ids": [b.transaction.id]},
            headers=headers,
        )
    )
    _refuse(
        client.post(
            "/api/accounting/entries",
            json={
                "bank_account_id": b.account.id,
                "journal": "BQ",
                "date_ecriture": "2026-09-24",
                "libelle": "OUBLI",
                "credit": "10.00",
                "motif": "test",
            },
            headers=headers,
        )
    )


def test_creating_an_account_for_another_company_is_refused(client, reference, societes, limite):
    _a, b = societes
    _user, headers = limite

    _refuse(
        client.post(
            "/api/accounts",
            json={
                "company_id": b.id,
                "bank_id": b.account.bank_id,
                "libelle": "Nouveau",
                "numero": "N-NOUVEAU",
                "devise": "MAD",
                "type_compte": "Courant",
                "credit_autorise": "0",
            },
            headers=headers,
        )
    )


def test_import_forms_naming_another_company_are_refused(client, societes, limite):
    _a, b = societes
    _user, headers = limite
    fichier = {"fichier": ("x.xlsx", b"pas un classeur", "application/octet-stream")}

    _refuse(
        client.post(
            "/api/accounting/import/analyse",
            data={"company_id": str(b.id)},
            files=fichier,
            headers=headers,
        )
    )
    _refuse(
        client.post(
            "/api/statements/import/analyse",
            data={"bank_account_id": str(b.account.id)},
            files=fichier,
            headers=headers,
        )
    )


# --- Historique -----------------------------------------------------------------------------------


def test_history_shows_only_the_actions_of_the_allowed_companies(
    client, reference, societes, limite
):
    a, b = societes
    user, headers = limite
    vue_a = audit_service.log(
        reference,
        user_id=user.id,
        action="modification_compte",
        entite="bank_account",
        entite_id=a.account.id,
    )
    vue_b = audit_service.log(
        reference,
        user_id=user.id,
        action="modification_compte",
        entite="bank_account",
        entite_id=b.account.id,
    )
    sans_societe = audit_service.log(
        reference,
        user_id=user.id,
        action="modification_utilisateur",
        entite="user",
        entite_id=user.id,
    )
    ecriture_a = audit_service.log(
        reference,
        user_id=user.id,
        action="saisie_ecriture",
        entite="accounting_entry",
        entite_id=a.entry_id,
    )
    reference.flush()

    lignes = client.get("/api/audit", headers=headers).json()["items"]
    ids = {ligne["id"] for ligne in lignes}

    assert {vue_a.id, ecriture_a.id} <= ids
    assert vue_b.id not in ids and sans_societe.id not in ids
    assert client.get(f"/api/audit/{vue_b.id}", headers=headers).status_code == 404
    assert client.get(f"/api/audit/{vue_a.id}", headers=headers).status_code == 200


# --- Administration -------------------------------------------------------------------------------


@pytest.fixture
def admin(client, reference):
    user = make_auth_user(reference, "ADMIN", email="chef@example.com")
    return user, bearer(login(client, "chef@example.com"))


def _role_ids(client, headers, *codes):
    roles = client.get("/api/admin/roles", headers=headers).json()
    return [role["id"] for role in roles if role["code"] in codes]


def test_the_administrator_ticks_the_companies_of_a_person_and_it_is_audited(
    client, reference, societes, admin
):
    a, _b = societes
    acteur, headers = admin
    cible = make_auth_user(reference, "COMPTABLE", email="cible@example.com")
    role_ids = _role_ids(client, headers, "COMPTABLE")

    response = client.put(
        f"/api/admin/users/{cible.id}",
        json={"nom": cible.nom, "email": cible.email, "role_ids": role_ids, "company_ids": [a.id]},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["company_ids"] == [a.id]
    log = reference.scalar(
        select(AuditLog)
        .where(AuditLog.entite == "user", AuditLog.entite_id == str(cible.id))
        .order_by(AuditLog.id.desc())
    )
    assert log.user_id == acteur.id
    assert log.ancienne_valeur["societes"] == [] and log.nouvelle_valeur["societes"] == [a.id]

    # Liste vide : de nouveau toutes les sociétés ; champ absent : inchangé
    client.put(
        f"/api/admin/users/{cible.id}",
        json={"nom": cible.nom, "email": cible.email, "role_ids": role_ids, "company_ids": []},
        headers=headers,
    )
    response = client.put(
        f"/api/admin/users/{cible.id}",
        json={"nom": "Renommé", "email": cible.email, "role_ids": role_ids},
        headers=headers,
    )
    assert response.json()["company_ids"] == []


def test_a_new_user_can_be_created_with_companies(client, societes, admin):
    a, b = societes
    _acteur, headers = admin

    response = client.post(
        "/api/admin/users",
        json={
            "nom": "Nouvelle",
            "email": "nouvelle@example.com",
            "role_ids": _role_ids(client, headers, "DIRECTION"),
            "company_ids": [b.id, a.id],
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["user"]["company_ids"] == sorted([a.id, b.id])


def test_an_inactive_or_unknown_company_cannot_be_ticked(client, reference, admin):
    _acteur, headers = admin
    inactive = save(reference, build_company(actif=False))
    payload = {
        "nom": "X",
        "email": "x@example.com",
        "role_ids": _role_ids(client, headers, "DIRECTION"),
    }

    refus = client.post(
        "/api/admin/users", json={**payload, "company_ids": [inactive.id]}, headers=headers
    )
    inconnue = client.post(
        "/api/admin/users", json={**payload, "company_ids": [999999999]}, headers=headers
    )

    assert refus.status_code == 409
    assert inconnue.status_code == 404


def test_a_limited_user_manager_only_gives_their_own_companies(client, reference, societes):
    a, b = societes
    gestionnaire = make_auth_user(reference, "DIRECTION", email="rh@example.com")
    from app.models import Permission, UserPermission

    permission = reference.scalar(select(Permission).where(Permission.code == "admin.users"))
    reference.add(
        UserPermission(user_id=gestionnaire.id, permission_id=permission.id, accordee=True)
    )
    _limiter(reference, gestionnaire, a.id)
    headers = bearer(login(client, "rh@example.com"))
    payload = {
        "nom": "Y",
        "email": "y@example.com",
        "role_ids": _role_ids(client, headers, "DIRECTION"),
    }

    _refuse(
        client.post("/api/admin/users", json={**payload, "company_ids": [b.id]}, headers=headers)
    )
    toutes = client.post("/api/admin/users", json={**payload, "company_ids": []}, headers=headers)
    assert toutes.status_code == 403
    ok = client.post("/api/admin/users", json={**payload, "company_ids": [a.id]}, headers=headers)
    assert ok.status_code == 201, ok.text


# --- Garde : toute route qui reçoit un id de donnée métier est couverte --------------------------

# Identifiants qui ne désignent pas une donnée d'une société
IDS_SANS_SOCIETE = {"user_id", "role_id", "audit_id", "bank_id", "mapping_id"}


def test_every_id_parameter_of_a_route_is_checked_or_known_to_have_no_company():
    """Une nouvelle route avec un paramètre `xxx_id` inconnu échoue ici : ajoutez son résolveur à
    `acces_societe_service.RESOLVEURS`, ou son nom à IDS_SANS_SOCIETE s'il n'a pas de société."""
    inconnus = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        params = route.dependant.path_params + route.dependant.query_params
        for param in params:
            nom = param.alias or param.name
            if nom.endswith("_id") and nom not in RESOLVEURS and nom not in IDS_SANS_SOCIETE:
                inconnus.add(f"{route.path} : {nom}")
    assert not inconnus, sorted(inconnus)
