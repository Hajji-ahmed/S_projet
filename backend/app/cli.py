"""Gestion des comptes en ligne de commande, en attendant l'écran d'administration (P16).

    python -m app.cli create-user --email admin@simtis.ma --nom "Administrateur" --role ADMIN
    python -m app.cli set-password --email admin@simtis.ma
    python -m app.cli recalculer-soldes --releve 12 --solde-ouverture 5000000
    python -m app.cli reprise-rapprochement --compte 1907… --banque mouvements.xlsx \
        --compta compta.xlsx --jusqu-au 2026-09-30 --motif "…" --email … [--appliquer]

Le mot de passe est généré aléatoirement et affiché UNE SEULE FOIS : il n'est stocké que haché.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from app.core.db import SessionLocal
from app.services import auth_service, import_service, reprise_service
from app.services.auth_service import AccountError
from app.services.errors import DomainError
from app.services.normalization_service import parse_amount


def _print_password(email: str, password: str) -> None:
    print(f"Compte : {email}")
    print(f"Mot de passe : {password}")
    print("Notez-le maintenant : il ne sera plus jamais affiché.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="créer un compte avec un ou plusieurs rôles")
    create.add_argument("--email", required=True)
    create.add_argument("--nom", required=True)
    create.add_argument(
        "--role",
        dest="roles",
        action="append",
        required=True,
        help="code du rôle (ADMIN, TRESORERIE, COMPTABLE, RESPONSABLE, DIRECTION) ; répétable",
    )

    reset = commands.add_parser(
        "set-password",
        help="générer un nouveau mot de passe (lève le verrouillage, ferme les sessions)",
    )
    reset.add_argument("--email", required=True)

    recompute = commands.add_parser(
        "recalculer-soldes",
        help="calculer les soldes d'un relevé importé sans soldes (solde précédent − débit + crédit)",
    )
    recompute.add_argument("--releve", type=int, required=True, help="numéro du relevé")
    recompute.add_argument(
        "--solde-ouverture", required=True, help="solde du compte juste avant la 1re opération"
    )

    reprise = commands.add_parser(
        "reprise-rapprochement",
        help="reprendre un état de rapprochement Excel : tout le reste du compte est rapproché",
    )
    reprise.add_argument("--compte", required=True, help="numéro du compte bancaire")
    reprise.add_argument("--banque", required=True, help="fichier des opérations non rapprochées")
    reprise.add_argument("--compta", required=True, help="fichier des écritures non rapprochées")
    reprise.add_argument("--feuille-banque", help="feuille à lire (sinon la première qui convient)")
    reprise.add_argument("--feuille-compta", help="feuille à lire (sinon la première qui convient)")
    reprise.add_argument(
        "--jusqu-au", required=True, type=date.fromisoformat, help="date de l'état, AAAA-MM-JJ"
    )
    reprise.add_argument("--motif", help="obligatoire avec --appliquer")
    reprise.add_argument("--email", help="auteur du rapprochement ; obligatoire avec --appliquer")
    reprise.add_argument(
        "--appliquer", action="store_true", help="écrire (sans cette option : simulation)"
    )

    args = parser.parse_args(argv)
    if args.command == "recalculer-soldes":
        return _recompute(args.releve, args.solde_ouverture)
    if args.command == "reprise-rapprochement":
        return _reprise(args)
    password = auth_service.generate_password()

    try:
        with SessionLocal() as db:
            if args.command == "create-user":
                user = auth_service.create_user(
                    db, email=args.email, nom=args.nom, role_codes=args.roles, password=password
                )
            else:
                user = auth_service.set_password(db, email=args.email, password=password)
    except AccountError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1

    _print_password(user.email, password)
    return 0


def _recompute(statement_id: int, opening_text: str) -> int:
    try:
        opening = parse_amount(opening_text)
    except ValueError as error:
        print(f"Erreur : solde d'ouverture illisible ({error})", file=sys.stderr)
        return 1
    if opening is None:
        print("Erreur : solde d'ouverture manquant.", file=sys.stderr)
        return 1
    try:
        with SessionLocal() as db:
            result = import_service.recompute_statement_balances(db, statement_id, opening)
    except DomainError as error:
        print(f"Erreur : {error.message}", file=sys.stderr)
        return 1
    print(f"Relevé n° {statement_id} : {result.nb_operations} soldes calculés.")
    print(f"Solde d'ouverture : {result.solde_ouverture}")
    print(f"Solde de clôture : {result.solde_cloture} (solde du jour : {result.solde_du_jour})")
    return 0


def _afficher(bilan: reprise_service.Bilan) -> None:
    print(f"Compte {bilan.compte}, état au {bilan.jusqu_au:%d/%m/%Y}")
    print(
        f"Fichier banque (feuille « {bilan.feuille_banque} ») : {bilan.lignes_banque} lignes, "
        f"{bilan.banque_sans_montant} sans montant (déjà pointées)"
    )
    print(
        f"Fichier compta (feuille « {bilan.feuille_compta} ») : {bilan.lignes_compta} lignes, "
        f"{bilan.compta_sans_montant} sans montant (déjà pointées)"
    )
    print(
        f"Restent non rapprochées : {len(bilan.gardees_operations)} opérations, "
        f"{len(bilan.gardees_ecritures)} écritures"
    )
    print(
        f"Passent « Rapprochée » : {len(bilan.operations)} opérations "
        f"(crédit − débit {bilan.total_operations}), {len(bilan.ecritures)} écritures "
        f"(montant {bilan.total_ecritures}), écart {bilan.ecart}"
    )
    for ligne in bilan.deja_rapprochees:
        print(f"  Déjà rapprochée ou proposée, laissée telle quelle : {ligne}")
    for probleme in bilan.problemes:
        print(f"  PROBLÈME : {probleme}")


def _reprise(args: argparse.Namespace) -> int:
    try:
        banque, compta = Path(args.banque).read_bytes(), Path(args.compta).read_bytes()
    except OSError as error:
        print(f"Erreur : fichier illisible ({error})", file=sys.stderr)
        return 1
    options = {
        "numero_compte": args.compte,
        "banque": banque,
        "compta": compta,
        "jusqu_au": args.jusqu_au,
        "feuille_banque": args.feuille_banque,
        "feuille_compta": args.feuille_compta,
    }
    try:
        with SessionLocal() as db:
            if not args.appliquer:
                bilan = reprise_service.analyser(db, **options)
                _afficher(bilan)
                print("Simulation : rien n'a été écrit (ajoutez --appliquer).")
                return 1 if bilan.problemes else 0
            if not args.motif or not args.email:
                print("Erreur : --motif et --email sont obligatoires avec --appliquer.")
                return 1
            bilan = reprise_service.appliquer(
                db,
                **options,
                noms_fichiers=(Path(args.banque).name, Path(args.compta).name),
                motif=args.motif,
                email=args.email,
            )
    except DomainError as error:
        print(f"Erreur : {error.message}", file=sys.stderr)
        return 1
    _afficher(bilan)
    print(f"Reprise enregistrée : rapprochement {bilan.code}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
