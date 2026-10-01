from sqlalchemy.orm import Session

from app.models import AuditLog


def add(db: Session, entry: AuditLog) -> AuditLog:
    db.add(entry)
    db.flush()
    return entry
