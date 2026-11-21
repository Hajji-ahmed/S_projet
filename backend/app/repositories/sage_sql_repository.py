"""Lecture de la base Sage 100 Comptabilité (SQL Server), en consultation seule (21/11/2026).

La base est une copie de la comptabilité refaite chaque nuit (vers 23 h - 0 h 30) ;
`T_PAR_SYC_BI.DT_SYC_BI` donne la date de cette copie. Rien n'y est jamais écrit.

Sage 100 : `F_ECRITUREC` = écritures ; la date d'une écriture est le premier jour de sa période
(`JM_Date`) plus son jour (`EC_Jour`) ; `EC_Sens` 0 = débit, 1 = crédit ; une échéance vide vaut
le 01/01/1900.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime

# Colonnes du grand livre, dans l'ordre : les en-têtes du modèle Excel « Export Sage Simtis ».
# Ni référence ni tiers : les exports Excel n'en ont jamais eu, et la référence entre dans
# l'empreinte d'une écriture (une ligne déjà importée doit rester un doublon)
COLONNES_GL = ("DATE", "JOURNAL", "COMPTE", "N°PIECE", "LIBELLE", "ECH", "DEBIT", "CREDIT")

_DATE_ECRITURE = "DATEADD(day, e.EC_Jour - 1, e.JM_Date)"

DELAI_CONNEXION = 10  # secondes
DELAI_REQUETE = 120


@dataclass(frozen=True)
class ConnexionSage:
    host: str
    port: int
    database: str
    user: str
    password: str


@contextmanager
def _curseur(cnx: ConnexionSage) -> Iterator:
    import pymssql  # chargé à la demande : seul le serveur de production joint la base

    connexion = pymssql.connect(
        server=cnx.host,
        port=str(cnx.port),
        user=cnx.user,
        password=cnx.password,
        database=cnx.database,
        login_timeout=DELAI_CONNEXION,
        timeout=DELAI_REQUETE,
    )
    try:
        yield connexion.cursor()
    finally:
        connexion.close()


def derniere_copie(cnx: ConnexionSage) -> datetime | None:
    """Date de la dernière copie de la base (`DT_SYC_BI`)."""
    with _curseur(cnx) as cur:
        cur.execute("SELECT MAX(DT_SYC_BI) FROM T_PAR_SYC_BI")
        row = cur.fetchone()
    return row[0] if row else None


def grand_livre(
    cnx: ConnexionSage,
    *,
    journaux: Sequence[str],
    comptes: Sequence[str],
    du: date,
    au: date,
) -> list[tuple]:
    """Lignes des journaux donnés dont le compte commence par l'un des comptes donnés, entre deux
    dates incluses, dans l'ordre de `COLONNES_GL` ; triées par date, journal, numéro d'écriture."""
    if not journaux or not comptes:
        return []
    params: list[object] = [*journaux]
    journaux_sql = ", ".join(["%s"] * len(journaux))
    comptes_sql = " OR ".join(["e.CG_Num LIKE %s"] * len(comptes))
    params += [f"{compte}%" for compte in comptes]
    # AAAAMMJJ : seul format de date lu pareil quelle que soit la langue de la session SQL Server
    params += [du.strftime("%Y%m%d"), au.strftime("%Y%m%d")]
    sql = f"""
        SELECT
            {_DATE_ECRITURE},
            e.JO_Num,
            e.CG_Num,
            e.EC_Piece,
            e.EC_Intitule,
            NULLIF(e.EC_Echeance, '19000101'),
            CASE WHEN e.EC_Sens = 0 THEN e.EC_Montant END,
            CASE WHEN e.EC_Sens = 1 THEN e.EC_Montant END
        FROM F_ECRITUREC e
        WHERE e.JO_Num IN ({journaux_sql})
          AND ({comptes_sql})
          AND {_DATE_ECRITURE} BETWEEN %s AND %s
        ORDER BY {_DATE_ECRITURE}, e.JO_Num, e.EC_No
    """  # noqa: S608 : seuls des marqueurs %s sont ajoutés, les valeurs passent en paramètres
    with _curseur(cnx) as cur:
        cur.execute(sql, tuple(params))
        return [tuple(row) for row in cur.fetchall()]
