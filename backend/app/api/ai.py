"""AI Finance Assistant endpoint. Data is sent to the AI provider only with consent for this request."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai import assistant
from ..ai.provider import AnthropicProvider, get_provider
from ..auth.deps import current_user, log_activity
from ..auth.security import limiter
from ..config import Settings, get_settings
from ..db.models import User
from ..db.session import get_db

router = APIRouter(prefix="/api/ai", tags=["ai"])
MAX_ATTACHMENT_BYTES = 300_000


class MessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class AttachmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=40)
    data: Any


class ChatRequest(BaseModel):
    mode: Literal["ask", "red_flags", "model_check", "challenge", "peers", "tutor", "report"] = "ask"
    messages: list[MessageIn] = Field(min_length=1, max_length=40)
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=10)
    consent: bool = False


@router.post("/chat")
def ai_chat(req: ChatRequest, user: User = Depends(current_user), db: Session = Depends(get_db),
            settings: Settings = Depends(get_settings)):
    provider = get_provider(settings)
    status = provider.status()
    if not status.configured or not isinstance(provider, AnthropicProvider):
        raise HTTPException(503, status.message)
    if not req.consent:
        raise HTTPException(400, "Please confirm that your question and the listed data may be sent to Anthropic (Claude).")
    size = len(json.dumps([a.model_dump() for a in req.attachments], default=str))
    if size > MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, f"The attached data is too large ({size // 1000} KB). Attach less, e.g. fewer companies.")
    if not limiter.hit(f"ai:{user.id}", 60, 3600):
        raise HTTPException(429, "AI limit reached (60 questions per hour). Try again later.")
    try:
        result = assistant.chat(provider.client(), settings.fis_ai_model, req.mode,
                                [m.model_dump() for m in req.messages],
                                [assistant.Attachment(a.title, a.kind, a.data) for a in req.attachments])
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # provider errors: never leak keys or internals
        import anthropic

        if isinstance(e, anthropic.AuthenticationError):
            raise HTTPException(502, "The AI provider rejected the API key. Check ANTHROPIC_API_KEY in backend/.env.") from e
        if isinstance(e, anthropic.RateLimitError):
            raise HTTPException(429, "The AI provider is rate-limiting requests. Wait a minute and try again.") from e
        if isinstance(e, anthropic.APIConnectionError):
            raise HTTPException(502, "Could not reach the AI provider. Check the internet connection.") from e
        if isinstance(e, anthropic.APIStatusError):
            raise HTTPException(502, f"The AI provider returned an error ({e.status_code}).") from e
        raise
    log_activity(db, user.id, "ai.chat", mode=req.mode, attachments=[a.title for a in req.attachments],
                 tools=[t["name"] for t in result.tools_used])
    db.commit()
    return {"reply": result.reply, "stop_reason": result.stop_reason, "model": result.model,
            "tools_used": result.tools_used, "usage": result.usage}
