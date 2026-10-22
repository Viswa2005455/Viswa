"""Accounts: register, sign in/out, sessions, password change, data export and deletion."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..auth.deps import SESSION_COOKIE, current_session, current_user, log_activity
from ..auth.security import DUMMY_HASH, EMAIL_RE, hash_password, limiter, new_session_token, normalise_email, password_problems, token_hash, verify_password
from ..config import Settings, get_settings
from ..db.models import Activity, AuthSession, Project, SavedItem, Upload, User, utcnow
from ..db.session import get_db
from .base import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])
account = APIRouter(prefix="/api/account", tags=["account"])


def client_ip(request: Request) -> str:
    # Behind a reverse proxy, configure uvicorn --proxy-headers so this is the real client address.
    return request.client.host if request.client else "unknown"


def start_session(db: Session, user: User, request: Request, response: Response, settings: Settings) -> None:
    token = new_session_token()
    expires = utcnow() + dt.timedelta(days=settings.fis_session_days)
    db.add(AuthSession(user_id=user.id, token_hash=token_hash(token), expires_at=expires,
                       user_agent=(request.headers.get("user-agent") or "")[:300]))
    user.last_login_at = utcnow()
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.fis_session_days * 86400, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path="/")


def user_out(u: User, settings: Settings) -> dict:
    return {"id": str(u.id), "email": u.email, "display_name": u.display_name, "created_at": u.created_at,
            "retention_days": settings.fis_upload_retention_days, "session_days": settings.fis_session_days}


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


@router.get("/config")
def auth_config(settings: Settings = Depends(get_settings)):
    return {"registration_open": settings.fis_allow_registration, "min_password_length": 10}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db),
             settings: Settings = Depends(get_settings)):
    if not settings.fis_allow_registration:
        raise HTTPException(403, "Registration is closed on this server.")
    if not limiter.hit(f"register:{client_ip(request)}", 10, 3600):
        raise HTTPException(429, "Too many sign-up attempts. Try again later.")
    email = normalise_email(body.email)
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    problems = password_problems(body.password, email)
    if problems:
        raise HTTPException(422, " ".join(problems))
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = User(email=email, display_name=body.display_name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    start_session(db, user, request, response, settings)
    log_activity(db, user.id, "account.created")
    db.commit()
    return user_out(user, settings)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings)):
    email = normalise_email(body.email)
    if not (limiter.hit(f"login-ip:{client_ip(request)}", 30, 900) and limiter.hit(f"login-email:{email}", 10, 900)):
        raise HTTPException(429, "Too many sign-in attempts. Wait 15 minutes and try again.")
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not (user and ok):
        raise HTTPException(401, "Email or password is incorrect.")
    start_session(db, user, request, response, settings)
    log_activity(db, user.id, "account.signed_in")
    db.commit()
    return user_out(user, settings)


@router.post("/logout")
def logout(response: Response, s: AuthSession = Depends(current_session), db: Session = Depends(get_db)):
    db.delete(db.get(AuthSession, s.id))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"signed_out": True}


@router.get("/me")
def me(user: User = Depends(current_user), settings: Settings = Depends(get_settings)):
    return user_out(user, settings)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


@router.post("/change-password")
def change_password(body: PasswordChange, request: Request, s: AuthSession = Depends(current_session), db: Session = Depends(get_db)):
    user = db.get(User, s.user_id)
    if not limiter.hit(f"pwchange:{user.id}", 10, 900):
        raise HTTPException(429, "Too many attempts. Try again later.")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(403, "Current password is incorrect.")
    problems = password_problems(body.new_password, user.email)
    if problems:
        raise HTTPException(422, " ".join(problems))
    user.password_hash = hash_password(body.new_password)
    # Sign out every other device.
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.id != s.id))
    log_activity(db, user.id, "account.password_changed")
    db.commit()
    return {"changed": True}


@router.get("/sessions")
def sessions(s: AuthSession = Depends(current_session), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == s.user_id).order_by(AuthSession.last_seen_at.desc())).all()
    return {"sessions": [{"id": str(x.id), "created_at": x.created_at, "last_seen_at": x.last_seen_at, "expires_at": x.expires_at,
                          "user_agent": x.user_agent, "current": x.id == s.id} for x in rows]}


@router.post("/sessions/revoke-others")
def revoke_others(s: AuthSession = Depends(current_session), db: Session = Depends(get_db)):
    n = db.execute(delete(AuthSession).where(AuthSession.user_id == s.user_id, AuthSession.id != s.id)).rowcount
    log_activity(db, s.user_id, "account.sessions_revoked", count=n)
    db.commit()
    return {"revoked": n}


# ---------------------------------------------------------------- account data


@account.get("/export")
def export_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Everything stored about the user, as JSON (uploaded file bytes are not included)."""
    from .projects import export_payload
    payload = export_payload(db, user.id, project_id=None)
    payload["account"] = {"email": user.email, "display_name": user.display_name, "created_at": user.created_at}
    log_activity(db, user.id, "account.exported")
    db.commit()
    return payload


class ConfirmIn(BaseModel):
    password: str = Field(max_length=200)


@account.post("/delete-data")
def delete_data(body: ConfirmIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete all uploads, projects, saved models and history, but keep the account."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(403, "Password is incorrect.")
    ids = db.scalars(select(Upload.id).where(Upload.user_id == user.id)).all()
    db.execute(delete(Upload).where(Upload.user_id == user.id))
    db.execute(delete(SavedItem).where(SavedItem.user_id == user.id))
    db.execute(delete(Project).where(Project.user_id == user.id))
    db.execute(delete(Activity).where(Activity.user_id == user.id))
    log_activity(db, user.id, "account.data_deleted", uploads=len(ids))
    db.commit()
    return {"deleted_uploads": len(ids)}


@account.post("/delete")
def delete_account(body: ConfirmIn, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Permanently delete the account and everything in it."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(403, "Password is incorrect.")
    # ORM-level deletes so cascades also work on SQLite (test fallback); PostgreSQL cascades via FKs.
    for model in (Upload, SavedItem, Activity, Project, AuthSession):
        db.execute(delete(model).where(model.user_id == user.id))
    db.delete(db.get(User, user.id))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"deleted": True}
