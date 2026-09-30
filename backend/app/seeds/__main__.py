import argparse
import sys
from collections import Counter

from app.core.db import SessionLocal
from app.seeds.common import SeedError
from app.seeds.demo import ensure_demo_allowed, seed_demo
from app.seeds.reference import seed_reference


def _format(created: Counter[str]) -> str:
    if not created:
        return "rien à créer (déjà présent)"
    return ", ".join(f"{count} {table}" for table, count in sorted(created.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.seeds",
        description="Charge les données initiales. Ne modifie ni ne supprime jamais une donnée existante.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="ajoute des données de démonstration (développement uniquement)",
    )
    args = parser.parse_args(argv)

    try:
        if args.demo:
            ensure_demo_allowed()  # avant toute écriture : un refus ne doit rien valider
        with SessionLocal() as session:
            reference = seed_reference(session)
            demo = seed_demo(session) if args.demo else None
            session.commit()
    except SeedError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1

    print(f"Seeds de référence : {_format(reference)}")
    if demo is not None:
        print(f"Données de démonstration : {_format(demo)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
