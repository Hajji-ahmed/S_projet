"""Tableaux Banques (P8.1) et Devises (soldes EUR / USD) calculés. Montants et taux en texte
exact ; inconnu = `null`, jamais 0."""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel

from app.services.account_service import fraction_to_pct
from app.services.position_banques_service import TableauDevises
from app.services.position_service import BanqueColonne, LigneTableau, TableauBanques


class BanqueColonneOut(BaseModel):
    bank_id: int
    code: str
    logo: str | None
    bank_account_id: int | None
    taux_pct: Decimal | None
    ligne: Decimal | None

    @classmethod
    def from_colonne(cls, colonne: BanqueColonne) -> "BanqueColonneOut":
        return cls(
            bank_id=colonne.bank_id,
            code=colonne.code,
            logo=colonne.logo,
            bank_account_id=colonne.bank_account_id,
            taux_pct=fraction_to_pct(colonne.taux_interet),
            ligne=colonne.ligne,
        )


class CelluleOut(BaseModel):
    bank_id: int
    valeur: Decimal | None
    date_solde: dt.date | None
    reprise: bool


class LigneOut(BaseModel):
    cellules: list[CelluleOut]
    total: Decimal | None
    depassement: Decimal | None

    @classmethod
    def from_ligne(cls, ligne: LigneTableau, **extra):
        return cls(
            cellules=[
                CelluleOut(
                    bank_id=c.bank_id, valeur=c.valeur, date_solde=c.date_solde, reprise=c.reprise
                )
                for c in ligne.cellules
            ],
            total=ligne.total,
            depassement=ligne.depassement,
            **extra,
        )


class JourOut(LigneOut):
    date: dt.date


class BanquesTableOut(BaseModel):
    company_id: int
    date_fin: dt.date
    banques: list[BanqueColonneOut]
    ligne_total: Decimal | None
    # Du plus ancien au plus récent ; la date de fin en dernier
    jours: list[JourOut]
    disponible: LigneOut

    @classmethod
    def from_table(cls, company_id: int, table: TableauBanques) -> "BanquesTableOut":
        return cls(
            company_id=company_id,
            date_fin=table.date_fin,
            banques=[BanqueColonneOut.from_colonne(colonne) for colonne in table.banques],
            ligne_total=table.ligne_total,
            jours=[JourOut.from_ligne(jour.ligne, date=jour.date) for jour in table.jours],
            disponible=LigneOut.from_ligne(table.disponible),
        )


class BanqueDeviseOut(BaseModel):
    bank_id: int
    code: str
    logo: str | None


class LigneDeviseOut(BaseModel):
    devise: str
    cellules: list[CelluleOut]
    total: Decimal | None


class DevisesSoldesOut(BaseModel):
    """Lignes EUR et USD du tableau Devises, dans leur devise (jamais converties)."""

    company_id: int
    date_fin: dt.date
    # Faux : la société n'a aucun compte en devise ni DH convertible, le tableau n'est pas affiché
    affiche: bool
    banques: list[BanqueDeviseOut]
    lignes: list[LigneDeviseOut]

    @classmethod
    def from_table(cls, company_id: int, table: TableauDevises) -> "DevisesSoldesOut":
        return cls(
            company_id=company_id,
            date_fin=table.date_fin,
            affiche=table.affiche,
            banques=[
                BanqueDeviseOut(bank_id=bank.id, code=bank.code, logo=bank.logo)
                for bank in table.banques
            ],
            lignes=[
                LigneDeviseOut(
                    devise=ligne.devise,
                    cellules=[
                        CelluleOut(
                            bank_id=c.bank_id,
                            valeur=c.valeur,
                            date_solde=c.date_solde,
                            reprise=c.reprise,
                        )
                        for c in ligne.cellules
                    ],
                    total=ligne.total,
                )
                for ligne in table.lignes
            ],
        )
