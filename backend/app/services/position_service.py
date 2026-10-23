"""Calculs de position (CDC §5.2). Fonctions pures, en `Decimal`, sans accès à la base.

    Crédit disponible   = Crédit autorisé (LIGNE) − Crédit utilisé
    Position disponible = Solde bancaire + Crédit disponible
    facilité de caisse  = Solde du jour + LIGNE (solde : dernière opération du jour, sinon solde
                          du jour saisi, sinon dernier connu)
    DEPASSEMENT         = TOTAL de la ligne − somme des LIGNES des mêmes banques
    Disponible Fc reel  = facilité de caisse du dernier jour − LIGNE (décision du 03/10/2026, qui
                          remplace « Solde + LIGNE » du CDC pour le tableau Banques)

Une valeur inconnue (jamais saisie) reste inconnue (`None`) : elle n'est jamais remplacée par zéro.
Réutilisé par la position bancaire (P8).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

# Les dates de solde sont celles du Maroc, pas celles du serveur (UTC)
BUSINESS_TZ = ZoneInfo("Africa/Casablanca")


# Aucun solde avant cette date : une année mal saisie (« 0026 ») ferait générer au tableau Banques
# une ligne par jour sur des siècles
PREMIERE_DATE_SOLDE = date(2000, 1, 1)


def business_today() -> date:
    return datetime.now(BUSINESS_TZ).date()


class BalanceLike(Protocol):
    date_solde: date
    solde: Decimal | None
    credit_utilise: Decimal | None


@dataclass(frozen=True)
class LatestValues:
    solde: Decimal | None
    credit_utilise: Decimal | None
    date_maj: date | None


@dataclass(frozen=True)
class AccountFigures:
    solde: Decimal | None
    credit_utilise: Decimal | None
    credit_disponible: Decimal | None
    position_disponible: Decimal | None
    date_maj: date | None
    # Le solde vient du relevé importé (solde de clôture), jamais d'une saisie (08/10/2026)
    solde_releve: bool = False


def _somme_connue(valeurs: Iterable[Decimal | None]) -> Decimal | None:
    connues = [v for v in valeurs if v is not None]
    return sum(connues, Decimal("0.00")) if connues else None


def somme_figures(figures: Sequence[AccountFigures]) -> AccountFigures:
    """Chiffres d'une banque qui a plusieurs comptes courants MAD (23/10/2026) : somme de chaque
    chiffre connu (un chiffre inconnu n'est jamais compté comme 0), dernière date de mise à jour."""
    if len(figures) == 1:
        return figures[0]
    dates = [f.date_maj for f in figures if f.date_maj is not None]
    return AccountFigures(
        solde=_somme_connue(f.solde for f in figures),
        credit_utilise=_somme_connue(f.credit_utilise for f in figures),
        credit_disponible=_somme_connue(f.credit_disponible for f in figures),
        position_disponible=_somme_connue(f.position_disponible for f in figures),
        date_maj=max(dates) if dates else None,
        solde_releve=all(f.solde_releve for f in figures),
    )


def credit_disponible(credit_autorise: Decimal, credit_utilise: Decimal | None) -> Decimal | None:
    """Peut être négatif : le crédit utilisé dépasse alors la LIGNE (dépassement)."""
    if credit_utilise is None:
        return None
    return credit_autorise - credit_utilise


def position_disponible(solde: Decimal | None, credit_dispo: Decimal | None) -> Decimal | None:
    if solde is None or credit_dispo is None:
        return None
    return solde + credit_dispo


def latest_values(balances: Iterable[BalanceLike], as_of: date | None = None) -> LatestValues:
    """Dernière valeur connue de chaque champ, jusqu'à `as_of` inclus.

    Le solde et le crédit utilisé peuvent venir de dates différentes ; la date de mise à jour est la
    dernière date où l'un des deux a été renseigné.
    """
    solde: tuple[date, Decimal] | None = None
    utilise: tuple[date, Decimal] | None = None
    for balance in balances:
        if as_of is not None and balance.date_solde > as_of:
            continue
        if balance.solde is not None and (solde is None or balance.date_solde > solde[0]):
            solde = (balance.date_solde, balance.solde)
        if balance.credit_utilise is not None and (
            utilise is None or balance.date_solde > utilise[0]
        ):
            utilise = (balance.date_solde, balance.credit_utilise)

    dates = [value[0] for value in (solde, utilise) if value is not None]
    return LatestValues(
        solde=solde[1] if solde else None,
        credit_utilise=utilise[1] if utilise else None,
        date_maj=max(dates) if dates else None,
    )


def account_figures(
    credit_autorise: Decimal, latest: LatestValues, *, solde_releve: bool = False
) -> AccountFigures:
    dispo = credit_disponible(credit_autorise, latest.credit_utilise)
    return AccountFigures(
        solde=latest.solde,
        credit_utilise=latest.credit_utilise,
        credit_disponible=dispo,
        position_disponible=position_disponible(latest.solde, dispo),
        date_maj=latest.date_maj,
        solde_releve=solde_releve,
    )


# --- Tableau Banques (P8.1, décisions du 02/10/2026) -----------------------------------------------


@dataclass(frozen=True)
class CompteColonne:
    """Un compte d'une colonne : son numéro, sa LIGNE et ses soldes (date, solde) (23/10/2026)."""

    numero: str
    soldes: tuple[tuple[date, Decimal], ...]
    ligne: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class BanqueColonne:
    """Une colonne du tableau : une banque active et ses comptes courants MAD actifs.

    Depuis le 23/10/2026 une banque peut en avoir plusieurs : `soldes` est alors la somme de leurs
    soldes (`somme_soldes`), `ligne` la somme de leurs LIGNES, et `comptes` le détail par compte.
    `ligne` et `bank_account_id` (premier compte) sont `None` sans compte.
    """

    bank_id: int
    code: str
    logo: str | None
    bank_account_id: int | None
    taux_interet: Decimal | None
    ligne: Decimal | None
    soldes: tuple[tuple[date, Decimal], ...]
    comptes: tuple[CompteColonne, ...] = ()


@dataclass(frozen=True)
class Cellule:
    bank_id: int
    valeur: Decimal | None
    # Date du solde utilisé ; `reprise` quand ce n'est pas le jour de la ligne
    date_solde: date | None
    reprise: bool
    # Plusieurs comptes dans la cellule (23/10/2026) : (numéro, solde) de chacun, pour l'infobulle
    detail: tuple[tuple[str, Decimal], ...] = ()


@dataclass(frozen=True)
class LigneTableau:
    cellules: tuple[Cellule, ...]
    total: Decimal | None
    depassement: Decimal | None


@dataclass(frozen=True)
class JourTableau:
    date: date
    ligne: LigneTableau


@dataclass(frozen=True)
class TableauBanques:
    date_fin: date
    banques: tuple[BanqueColonne, ...]
    ligne_total: Decimal | None
    jours: tuple[JourTableau, ...]
    disponible: LigneTableau


def facilite_de_caisse(solde: Decimal, ligne: Decimal) -> Decimal:
    return solde + ligne


def depassement(total: Decimal | None, total_lignes: Decimal) -> Decimal | None:
    return None if total is None else total - total_lignes


def fusion_soldes(
    operations: Iterable[tuple[date, Decimal]], saisies: Iterable[tuple[date, Decimal]]
) -> tuple[tuple[date, Decimal], ...]:
    """Solde retenu par jour : celui de la dernière opération du jour s'il existe, sinon le solde
    du jour (saisi ou écrit par l'import). Trié par date."""
    par_jour = dict(saisies)
    par_jour.update(operations)
    return tuple(sorted(par_jour.items()))


def solde_connu(soldes: Iterable[tuple[date, Decimal]], jour: date) -> tuple[date, Decimal] | None:
    """Dernier (date, solde) connu au `jour` inclus, sans les soldes d'avant PREMIERE_DATE_SOLDE."""
    connus = [(d, s) for d, s in soldes if PREMIERE_DATE_SOLDE <= d <= jour]
    return max(connus) if connus else None


def somme_soldes(
    series: Sequence[Sequence[tuple[date, Decimal]]],
) -> tuple[tuple[date, Decimal], ...]:
    """Solde d'une banque qui a plusieurs comptes dans la même devise (23/10/2026) : chaque jour où
    l'un d'eux a un solde, la somme du dernier solde connu de chaque compte. Un compte qui n'a encore
    aucun solde n'entre pas dans la somme (jamais compté comme 0)."""
    if len(series) == 1:
        return tuple(series[0])
    jours = sorted({d for serie in series for d, _ in serie})
    resultat = []
    for jour in jours:
        connus = [connu for serie in series if (connu := solde_connu(serie, jour))]
        if connus:
            resultat.append((jour, sum((s for _, s in connus), Decimal("0.00"))))
    return tuple(resultat)


def detail_comptes(comptes: Sequence[CompteColonne], jour: date) -> tuple[tuple[str, Decimal], ...]:
    """(numéro, dernier solde connu) de chaque compte au `jour`, quand la cellule en regroupe
    plusieurs ; vide pour un seul compte."""
    if len(comptes) < 2:
        return ()
    return tuple(
        (compte.numero, connu[1])
        for compte in comptes
        if (connu := solde_connu(compte.soldes, jour))
    )


def ligne_au(banque: "BanqueColonne", jour: date) -> Decimal | None:
    """LIGNE d'une colonne au `jour` : avec plusieurs comptes, seulement celle des comptes qui ont
    déjà un solde connu (comme une banque sans solde n'entre pas dans la somme des LIGNES)."""
    if len(banque.comptes) < 2:
        return banque.ligne
    lignes = [c.ligne for c in banque.comptes if solde_connu(c.soldes, jour)]
    return sum(lignes, Decimal("0.00")) if lignes else None


def montant_en_cours(
    ajustements: Iterable[tuple[date, date | None, Decimal]], jour: date
) -> Decimal:
    """Somme des opérations en cours actives le `jour` : de leur date à celle de leur définitive
    (exclue), 20/10/2026."""
    return sum(
        (m for debut, fin, m in ajustements if debut <= jour and (fin is None or jour < fin)),
        Decimal("0.00"),
    )


def avec_en_cours(
    soldes: Sequence[tuple[date, Decimal]], ajustements: Sequence[tuple[date, date | None, Decimal]]
) -> tuple[tuple[date, Decimal], ...]:
    """Soldes du compte + opérations en cours d'un fichier à part (20/10/2026) : la banque les a
    déjà passées dans son solde, pas encore dans son relevé. Un jour où une opération en cours
    commence ou finit devient un jour de solde ; avant le premier solde connu, rien."""
    if not ajustements:
        return tuple(soldes)
    jours = sorted(
        {jour for jour, _ in soldes}
        | {debut for debut, _, _ in ajustements}
        | {fin for _, fin, _ in ajustements if fin is not None}
    )
    resultat = []
    for jour in jours:
        connus = [solde for date_solde, solde in soldes if date_solde <= jour]
        if not connus:
            continue
        resultat.append((jour, connus[-1] + montant_en_cours(ajustements, jour)))
    return tuple(resultat)


def _disponible(banques: Sequence[BanqueColonne], fin: LigneTableau, jour: date) -> LigneTableau:
    """Disponible Fc reel : facilité de caisse du dernier jour − LIGNE, banque par banque ;
    TOTAL = somme des banques renseignées ; DEPASSEMENT = TOTAL, la LIGNE étant déjà retirée
    (correction du 03/10/2026)."""
    cellules: list[Cellule] = []
    total: Decimal | None = None
    for banque, cellule in zip(banques, fin.cellules, strict=True):
        ligne = ligne_au(banque, jour)
        if cellule.valeur is None or ligne is None:
            cellules.append(cellule)
            continue
        valeur = cellule.valeur - ligne
        cellules.append(
            Cellule(cellule.bank_id, valeur, cellule.date_solde, cellule.reprise, cellule.detail)
        )
        total = valeur if total is None else total + valeur
    return LigneTableau(tuple(cellules), total, total)


def _ligne(
    banques: Sequence[BanqueColonne], jour: date, retenus: dict[int, tuple[date, Decimal]]
) -> LigneTableau:
    """Une ligne du tableau : chaque banque avec son solde retenu, TOTAL et DEPASSEMENT.

    Une banque sans solde retenu (pas de compte, ou avant son premier solde) n'entre ni dans le
    TOTAL ni dans la somme des LIGNES.
    """
    cellules: list[Cellule] = []
    total: Decimal | None = None
    lignes = Decimal("0")
    for banque in banques:
        retenu = retenus.get(banque.bank_id)
        ligne = ligne_au(banque, jour)
        if retenu is None or ligne is None:
            cellules.append(Cellule(banque.bank_id, None, None, False))
            continue
        date_solde, solde = retenu
        valeur = facilite_de_caisse(solde, ligne)
        cellules.append(
            Cellule(
                banque.bank_id,
                valeur,
                date_solde,
                date_solde != jour,
                detail_comptes(banque.comptes, jour),
            )
        )
        total = valeur if total is None else total + valeur
        lignes += ligne
    return LigneTableau(tuple(cellules), total, depassement(total, lignes))


def tableau_banques(banques: Sequence[BanqueColonne], date_fin: date) -> TableauBanques:
    """Tableau Banques jusqu'à `date_fin` incluse : une ligne par jour calendaire depuis le premier
    solde connu ; un jour sans solde reprend le dernier solde connu de la banque. Un solde daté
    avant PREMIERE_DATE_SOLDE (année mal saisie) est ignoré."""
    soldes = {
        banque.bank_id: {
            jour: solde for jour, solde in banque.soldes if PREMIERE_DATE_SOLDE <= jour <= date_fin
        }
        for banque in banques
        if banque.bank_account_id is not None
    }
    dates = [jour for par_jour in soldes.values() for jour in par_jour]

    retenus: dict[int, tuple[date, Decimal]] = {}
    jours: list[JourTableau] = []
    if dates:
        jour = min(dates)
        while jour <= date_fin:
            for bank_id, par_jour in soldes.items():
                if jour in par_jour:
                    retenus[bank_id] = (jour, par_jour[jour])
            jours.append(JourTableau(jour, _ligne(banques, jour, retenus)))
            jour += timedelta(days=1)

    lignes = [banque.ligne for banque in banques if banque.ligne is not None]
    return TableauBanques(
        date_fin=date_fin,
        banques=tuple(banques),
        ligne_total=sum(lignes, Decimal("0")) if lignes else None,
        jours=tuple(jours),
        disponible=_disponible(
            banques, jours[-1].ligne if jours else _ligne(banques, date_fin, {}), date_fin
        ),
    )


# --- Tableau Devises : soldes des comptes EUR / USD (décision du 05/10/2026) ---------------------

DEVISES_CALCULEES = ("EUR", "USD")


@dataclass(frozen=True)
class LigneDevise:
    devise: str
    cellules: tuple[Cellule, ...]
    total: Decimal | None


def ligne_devise(
    devise: str,
    bank_ids: Sequence[int],
    soldes: dict[int, Sequence[tuple[date, Decimal]]],
    date_fin: date,
    comptes: dict[int, Sequence[CompteColonne]] | None = None,
) -> LigneDevise:
    """Une ligne EUR ou USD : solde du compte de chaque banque à `date_fin`, dans sa devise, sans
    conversion (dernier solde connu, repris d'un jour précédent au besoin). TOTAL = somme des soldes
    de cette seule devise ; `None` si aucune banque n'a de solde. `soldes` : par banque, (date,
    solde) déjà fusionnés (dernière opération du jour, sinon solde du jour) et, pour une banque qui a
    plusieurs comptes dans cette devise, déjà additionnés (`somme_soldes`) ; `comptes` donne alors
    le détail par compte de la cellule (23/10/2026)."""
    cellules: list[Cellule] = []
    total: Decimal | None = None
    for bank_id in bank_ids:
        connus = [
            (jour, solde)
            for jour, solde in soldes.get(bank_id, ())
            if PREMIERE_DATE_SOLDE <= jour <= date_fin
        ]
        if not connus:
            cellules.append(Cellule(bank_id, None, None, False))
            continue
        jour, solde = max(connus)
        cellules.append(
            Cellule(
                bank_id,
                solde,
                jour,
                jour != date_fin,
                detail_comptes((comptes or {}).get(bank_id, ()), date_fin),
            )
        )
        total = solde if total is None else total + solde
    return LigneDevise(devise, tuple(cellules), total)
