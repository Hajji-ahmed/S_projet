"""Historique (P16.2) : le journal d'audit en lecture seule."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.services.historique_service import (
    Filtres,
    Ligne,
    Page,
    differences,
    libelle_action,
    libelle_entite,
    resume,
)


class LigneOut(BaseModel):
    id: int
    created_at: datetime
    user_id: int | None
    # None : action système (commande en ligne, migration, tentative anonyme)
    utilisateur: str | None
    action: str
    action_libelle: str
    entite: str
    entite_libelle: str
    entite_id: str | None
    resume: str
    ip: str | None

    @classmethod
    def of(cls, ligne: Ligne) -> "LigneOut":
        entry = ligne.entry
        return cls(
            id=entry.id,
            created_at=entry.created_at,
            user_id=entry.user_id,
            utilisateur=ligne.utilisateur,
            action=entry.action,
            action_libelle=libelle_action(entry.action),
            entite=entry.entite,
            entite_libelle=libelle_entite(entry.entite),
            entite_id=entry.entite_id,
            resume=resume(entry.ancienne_valeur, entry.nouvelle_valeur),
            ip=entry.ip,
        )


class PageOut(BaseModel):
    items: list[LigneOut]
    total: int
    page: int
    pages: int

    @classmethod
    def of(cls, page: Page) -> "PageOut":
        return cls(
            items=[LigneOut.of(ligne) for ligne in page.lignes],
            total=page.total,
            page=page.page,
            pages=page.pages,
        )


class DifferenceOut(BaseModel):
    champ: str
    avant: Any
    apres: Any
    modifie: bool


class DetailOut(LigneOut):
    avant: dict[str, Any] | None
    apres: dict[str, Any] | None
    differences: list[DifferenceOut]

    @classmethod
    def of(cls, ligne: Ligne) -> "DetailOut":
        entry = ligne.entry
        return cls(
            **LigneOut.of(ligne).model_dump(),
            avant=entry.ancienne_valeur,
            apres=entry.nouvelle_valeur,
            differences=[
                DifferenceOut(champ=d.champ, avant=d.avant, apres=d.apres, modifie=d.modifie)
                for d in differences(entry.ancienne_valeur, entry.nouvelle_valeur)
            ],
        )


class OptionOut(BaseModel):
    code: str
    libelle: str
    nb: int | None = None


class UtilisateurOut(BaseModel):
    id: int
    nom: str


class FiltresOut(BaseModel):
    actions: list[OptionOut]
    entites: list[OptionOut]
    utilisateurs: list[UtilisateurOut]

    @classmethod
    def of(cls, filtres: Filtres) -> "FiltresOut":
        return cls(
            actions=[OptionOut(code=c, libelle=lib, nb=n) for c, lib, n in filtres.actions],
            entites=[OptionOut(code=c, libelle=lib) for c, lib in filtres.entites],
            utilisateurs=[UtilisateurOut(id=i, nom=n) for i, n in filtres.utilisateurs],
        )
