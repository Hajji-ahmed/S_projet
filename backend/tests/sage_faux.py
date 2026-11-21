"""Faux dépôt Sage des tests (21/11/2026) : la base Sage 100 n'est joignable que depuis le
serveur de production. Fixture `sage` : base configurée, lignes dans `sage.lignes` par journal."""

from datetime import datetime
from decimal import Decimal

import pytest

from app.core.config import get_settings
from app.repositories import sage_sql_repository
from app.services import sage_sql_service

COPIE = datetime(2025, 9, 30, 0, 33)


class FauxSage:
    """Remplace la base Sage : lignes par journal, et trace des lectures."""

    def __init__(self) -> None:
        self.lignes: dict[str, list[tuple]] = {}
        self.lectures: list[dict] = []
        self.panne = False

    def derniere_copie(self, cnx):
        if self.panne:
            raise OSError("connexion refusée")
        return COPIE

    def grand_livre(self, cnx, *, journaux, comptes, du, au):
        if self.panne:
            raise OSError("connexion refusée")
        self.lectures.append({"journaux": list(journaux), "comptes": list(comptes)})
        return [
            row
            for journal in journaux
            for row in self.lignes.get(journal, [])
            if row[2].startswith(tuple(comptes)) and du <= row[0].date() <= au
        ]

    def _toutes(self, comptes, du=None, au=None):
        if self.panne:
            raise OSError("connexion refusée")
        return [
            row
            for rows in self.lignes.values()
            for row in rows
            if row[2].startswith(tuple(comptes))
            and (du is None or du <= row[0].date())
            and (au is None or row[0].date() <= au)
        ]

    def debut_solde(self, cnx, *, comptes, jour):
        rows = self._toutes(comptes, au=jour)
        a_nouveaux = [row[0].date() for row in rows if row[1] == "9000"]
        dates = a_nouveaux or [row[0].date() for row in rows]
        return (max if a_nouveaux else min)(dates) if dates else None

    def totaux_par_journal(self, cnx, *, comptes, du, au):
        totaux: dict[str, list] = {}
        for row in self._toutes(comptes, du, au):
            item = totaux.setdefault(row[1], [Decimal(0), Decimal(0), 0])
            item[0] += row[6] or 0
            item[1] += row[7] or 0
            item[2] += 1
        return [(journal, d, c, n) for journal, (d, c, n) in sorted(totaux.items())]

    def lignes_hors_journaux(self, cnx, *, comptes, journaux_exclus, du, au, limite):
        rows = [r for r in self._toutes(comptes, du, au) if r[1] not in journaux_exclus]
        return sorted(rows, key=lambda r: r[0], reverse=True)[:limite]


@pytest.fixture
def sage(monkeypatch) -> FauxSage:
    faux = FauxSage()
    monkeypatch.setattr(sage_sql_repository, "derniere_copie", faux.derniere_copie)
    monkeypatch.setattr(sage_sql_repository, "grand_livre", faux.grand_livre)
    for nom in ("debut_solde", "totaux_par_journal", "lignes_hors_journaux"):
        monkeypatch.setattr(sage_sql_repository, nom, getattr(faux, nom))
    configure = get_settings().model_copy(
        update={
            "sage_sql_host": "10.0.0.1",
            "sage_sql_database": "SF_TEST",
            "sage_sql_user": "Consultation",
            "sage_sql_password": "secret",
            "sage_sql_societe": "SIMTIS",
        }
    )
    monkeypatch.setattr(sage_sql_service, "get_settings", lambda: configure)
    return faux
