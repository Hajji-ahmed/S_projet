from sqlalchemy import text
from sqlalchemy.orm import Session


def ping(db: Session) -> None:
    """Lève une exception SQLAlchemy si la base ne répond pas."""
    db.execute(text("SELECT 1"))
