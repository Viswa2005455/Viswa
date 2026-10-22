"""AI Finance Assistant endpoint. Data is sent to the AI provider only with consent for this request."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

from ..ai import assistant
from ..ai.provider import MODELS, PRICES_CHECKED_ON, AIError, AnthropicProvider, now_iso, get_provider, health_snapshot, record
from ..auth.deps import current_user, log_activity
from ..auth.security import limiter
from ..config import Settings, get_settings
from ..db.models import User
from ..db.session import get_db
from .base import BaseModel

router = APIRouter(prefix="/api/ai", tags=["ai"])
log = logging.getLogger("fis.ai")
MAX_ATTACHMENT_BYTES = 300_000


class MessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class AttachmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=40)
    data: Any


class ChatRequest(BaseModel):
    mode: Literal["ask", "red_flags", "model_check", "challenge", "peers", "research", "report"] = "ask"
    messages: list[MessageIn] = Field(min_length=1, max_length=40)
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=10)
    consent: bool = False
    model: str | None = Field(default=None, max_length=64)  # one of provider.MODELS; None = server default


def _http(err: AIError) -> HTTPException:
    return HTTPException(err.status_code, {"category": err.category, "message": err.message})


@router.post("/chat")
def ai_chat(req: ChatRequest, user: User = Depends(current_user), db: Session = Depends(get_db),
            settings: Settings = Depends(get_settings)):
    provider = get_provider(settings)
    status = provider.status()
    if not status.configured or not isinstance(provider, AnthropicProvider):
        raise HTTPException(503, status.message)
    try:
        model = provider.resolve_model(req.model)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if not req.consent:
        raise HTTPException(400, "Please confirm that your question and the listed data may be sent to Anthropic (Claude).")
    size = len(json.dumps([a.model_dump() for a in req.attachments], default=str))
    if size > MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, f"The attached data is too large ({size // 1000} KB). Attach less, e.g. fewer companies.")
    if not limiter.hit(f"ai:{user.id}", 60, 3600):
        raise HTTPException(429, "AI limit reached (60 questions per hour). Try again later.")
    start = time.perf_counter()
    try:
        result = assistant.chat(provider.client(), model, req.mode, [m.model_dump() for m in req.messages],
                                [assistant.Attachment(a.title, a.kind, a.data) for a in req.attachments],
                                deadline_seconds=settings.fis_ai_deadline_seconds)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except AIError as e:
        record(model, False, "chat", (time.perf_counter() - start) * 1000, error=e)
        log.warning("ai.chat failed: category=%s detail=%s", e.category, e.detail)  # no keys, no prompt text
        raise _http(e) from e
    record(model, True, "chat", result.latency_ms, served_model=result.model)
    log_activity(db, user.id, "ai.chat", mode=req.mode, model=model, served_model=result.model,
                 attachments=[a.title for a in req.attachments], tools=[t["name"] for t in result.tools_used])
    db.commit()
    notice = None
    if result.model != model or result.fallbacks:
        notice = (f"You chose {MODELS[model]['label']}, but it declined part of this request, so the provider's "
                  f"fallback model {result.model} produced this answer.")
    return {"reply": result.reply, "stop_reason": result.stop_reason, "requested_model": model, "model": result.model,
            "fallbacks": result.fallbacks, "model_notice": notice, "tools_used": result.tools_used, "usage": result.usage,
            "latency_ms": result.latency_ms, "api_calls": result.api_calls, "answered_at": now_iso()}


@router.get("/health")
def ai_health(settings: Settings = Depends(get_settings)):
    """Configuration and the results of past checks and requests. Makes no call to the provider."""
    provider = get_provider(settings)
    status = asdict(provider.status())
    seen = health_snapshot()
    models = [{**m, "health": seen.get(m["id"]) or {"state": "untested"}} for m in status.get("models", [])]
    return {**status, "models": models, "providers_supported": ["anthropic"], "prices_checked_on": PRICES_CHECKED_ON,
            "note": "Results are kept in memory since the server last started. 'untested' means no check or request "
                    "has been made yet; checks run only when you press a button."}


class CheckIn(BaseModel):
    model: str = Field(max_length=64)
    kind: Literal["access", "reply"] = "access"
    confirm: bool = False


@router.post("/health/check")
def ai_health_check(req: CheckIn, user: User = Depends(current_user), settings: Settings = Depends(get_settings)):
    """Run one live check, only when the user asks. 'reply' sends a tiny message and costs a few tokens."""
    provider = get_provider(settings)
    if not isinstance(provider, AnthropicProvider) or not provider.has_key:
        raise HTTPException(503, provider.status().message)
    if not req.confirm:
        raise HTTPException(400, "Confirm the check first: it contacts the AI provider"
                                 + (" and uses a few tokens." if req.kind == "reply" else "."))
    if not limiter.hit(f"ai-check:{user.id}", 20, 3600):
        raise HTTPException(429, "Check limit reached (20 per hour) to respect the provider's rate limits.")
    try:
        h = provider.check(req.model, req.kind)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except AIError as e:
        raise _http(e) from e
    return asdict(h)
