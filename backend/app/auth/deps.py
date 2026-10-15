"""Request authentication and the activity log helper."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Activity, AuthSession, User, utcnow
from ..db.session import get_db
from .security import token_hash

SESSION_COOKIE = "fis_session"
TOUCH_INTERVAL = dt.timedelta(minutes=5)


def _aware(d: dt.datetime) -> dt.datetime:
    # SQLite returns naive datetimes; PostgreSQL returns aware ones. Treat naive as UTC.
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def current_session(request: Request, db: Session = Depends(get_db)) -> AuthSession:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Please sign in.")
    s = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    now = utcnow()
    if not s or _aware(s.expires_at) <= now:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    if now - _aware(s.last_seen_at) > TOUCH_INTERVAL:
        s.last_seen_at = now
        db.commit()
    request.state.user_id = s.user_id
    return s


def current_user(s: AuthSession = Depends(current_session)) -> User:
    return s.user


def log_activity(db: Session, user_id: uuid.UUID, action: str, *, project_id: uuid.UUID | None = None,
                 entity_type: str | None = None, entity_id: str | None = None, **detail) -> None:
    """Record an event in the user's history. Callers commit."""
    db.add(Activity(user_id=user_id, project_id=project_id, action=action, entity_type=entity_type,
                    entity_id=entity_id, detail=detail))
