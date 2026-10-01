"""Gestion des comptes en ligne de commande, en attendant l'écran d'administration (P16).

    python -m app.cli create-user --email admin@simtis.ma --nom "Administrateur" --role ADMIN
    python -m app.cli set-password --email admin@simtis.ma

Le mot de passe est généré aléatoirement et affiché UNE SEULE FOIS : il n'est stocké que haché.
"""

import argparse
import sys

from app.core.db import SessionLocal
from app.services import auth_service
from app.services.auth_service import AccountError


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

    args = parser.parse_args(argv)
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


if __name__ == "__main__":
    sys.exit(main())
