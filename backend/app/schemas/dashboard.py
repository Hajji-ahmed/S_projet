"""Dashboard (P15, 14/10/2026)."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.services.dashboard_service import Alerte, Banque, CompteDashboard, Dashboard


class KpiOut(BaseModel):
    valeur: Decimal | None
    # Variation en % par rapport à la période précédente de même durée ; None sans comparaison
    variation: Decimal | None


class PointOut(BaseModel):
    date: date
    solde: Decimal | None


class FluxOut(BaseModel):
    date: date
    encaissements: Decimal
    decaissements: Decimal


class FraisOut(BaseModel):
    code: str
    libelle: str
    total: Decimal


class CompteOut(BaseModel):
    id: int
    bank_id: int
    bank_code: str
    bank_nom: str
    bank_logo: str | None
    numero: str
    devise: str
    solde: Decimal | None
    variation: Decimal | None
    # LIGNE d'un compte courant MAD ; null pour un compte en devise
    ligne: Decimal | None
    disponible: Decimal | None

    @classmethod
    def of(cls, item: CompteDashboard) -> "CompteOut":
        account = item.account
        return cls(
            id=account.id,
            bank_id=account.bank_id,
            bank_code=account.bank.code,
            bank_nom=account.bank.nom,
            bank_logo=account.bank.logo,
            numero=account.numero,
            devise=account.devise,
            solde=item.solde,
            variation=item.variation,
            ligne=item.ligne,
            disponible=item.disponible,
        )


class OperationOut(BaseModel):
    id: int
    date_operation: date
    bank_code: str
    devise: str
    libelle: str
    debit: Decimal
    credit: Decimal
    statut: str


class AlerteOut(BaseModel):
    niveau: str
    message: str
    lien: str

    @classmethod
    def of(cls, alerte: Alerte) -> "AlerteOut":
        return cls(niveau=alerte.niveau, message=alerte.message, lien=alerte.lien)


class TachesOut(BaseModel):
    """Travail en attente de la période (onglet « Suivi », 19/10/2026)."""

    propositions_fortes: int
    propositions_a_verifier: int
    operations_ambigues: int
    ecritures_ambigues: int
    a_comptabiliser: int
    a_exporter: int


class BanqueOut(BaseModel):
    code: str
    logo: str | None
    rapprochees: int
    a_rapprocher: int
    total: int
    frais: Decimal

    @classmethod
    def of(cls, item: Banque) -> "BanqueOut":
        return cls(
            code=item.code,
            logo=item.logo,
            rapprochees=item.rapprochees,
            a_rapprocher=item.a_rapprocher,
            total=item.total,
            frais=item.frais,
        )


class BanqueFiltreOut(BaseModel):
    id: int
    code: str
    logo: str | None


class DashboardOut(BaseModel):
    date_from: date
    date_to: date
    # Banque filtrée (19/10/2026) ; null = toutes
    bank_id: int | None
    banques_societe: list[BanqueFiltreOut]
    taches: TachesOut
    banques: list[BanqueOut]
    solde_total: KpiOut
    ligne_totale: Decimal
    disponible: Decimal | None
    encaissements: KpiOut
    decaissements: KpiOut
    rapprochees: int
    a_rapprocher: int
    total_operations: int
    evolution: list[PointOut]
    flux: list[FluxOut]
    a_comptabiliser: int
    frais: list[FraisOut]
    frais_total: Decimal
    comptes: list[CompteOut]
    dernieres_operations: list[OperationOut]
    ecritures_exportees: int
    ecritures_a_exporter: int
    alertes: list[AlerteOut]

    @classmethod
    def of(cls, vue: Dashboard) -> "DashboardOut":
        taches = vue.taches
        return cls(
            date_from=vue.date_from,
            date_to=vue.date_to,
            bank_id=vue.bank_id,
            banques_societe=[
                BanqueFiltreOut(id=i, code=code, logo=logo) for i, code, logo in vue.banques_societe
            ],
            taches=TachesOut(
                propositions_fortes=taches.propositions_fortes if taches else 0,
                propositions_a_verifier=taches.propositions_a_verifier if taches else 0,
                operations_ambigues=taches.operations_ambigues if taches else 0,
                ecritures_ambigues=taches.ecritures_ambigues if taches else 0,
                a_comptabiliser=vue.a_comptabiliser,
                a_exporter=vue.ecritures_a_exporter,
            ),
            banques=[BanqueOut.of(item) for item in vue.banques],
            solde_total=KpiOut(valeur=vue.solde_total, variation=vue.solde_total_variation),
            ligne_totale=vue.ligne_totale,
            disponible=vue.disponible,
            encaissements=KpiOut(valeur=vue.encaissements, variation=vue.encaissements_variation),
            decaissements=KpiOut(valeur=vue.decaissements, variation=vue.decaissements_variation),
            rapprochees=vue.rapprochees,
            a_rapprocher=vue.a_rapprocher,
            total_operations=vue.total_operations,
            evolution=[PointOut(date=jour, solde=solde) for jour, solde in vue.evolution],
            flux=[
                FluxOut(date=jour, encaissements=enc, decaissements=dec)
                for jour, enc, dec in vue.flux
            ],
            a_comptabiliser=vue.a_comptabiliser,
            frais=[FraisOut(code=c, libelle=n, total=t) for c, n, t in vue.frais],
            frais_total=vue.frais_total,
            comptes=[CompteOut.of(item) for item in vue.comptes],
            dernieres_operations=[
                OperationOut(
                    id=tx.id,
                    date_operation=tx.date_operation,
                    bank_code=account.bank.code,
                    devise=account.devise,
                    libelle=tx.libelle,
                    debit=tx.debit,
                    credit=tx.credit,
                    statut=tx.statut,
                )
                for tx, account in vue.dernieres
            ],
            ecritures_exportees=vue.ecritures_exportees,
            ecritures_a_exporter=vue.ecritures_a_exporter,
            alertes=[AlerteOut.of(alerte) for alerte in vue.alertes],
        )


class AlertesOut(BaseModel):
    alertes: list[AlerteOut]
