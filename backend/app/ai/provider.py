"""Server-side AI provider adapter.

The provider is selected with FIS_AI_PROVIDER. Only providers that are actually implemented and
configured with credentials are offered: today that is Anthropic (Claude). API keys are read on
the server only and are never returned to the browser or written to logs.

Every provider exposes the same small interface (status, models, health checks, error
classification), so the API layer never depends on SDK details. The adapter never invents a
response: when a call fails, the failure is reported with a category the user can act on.

Calculations are never delegated to the AI model: the assistant (app/ai/assistant.py) calls the
deterministic functions in app.finance as tools and uses the model only to explain them.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from dataclasses import asdict, dataclass, field

from ..config import Settings

# Model allow-list with first-party API prices (USD per million tokens: input, output, cache read,
# cache write). Checked against the Claude API model table on 2026-10-22. Server-side refusal
# fallback ("fallbacks": "default") is offered on Opus 5.5 and Sonnet 5.5 only; Haiku 5.5 has none.
MODELS: dict[str, dict] = {
    "claude-opus-5-5": {"label": "Claude Opus 5.5", "prices": (4.00, 20.00, 0.20, 5.00), "fallback": True,
                        "note": "Most capable; default."},
    "claude-sonnet-5-5": {"label": "Claude Sonnet 5.5", "prices": (2.00, 10.00, 0.20, 2.50), "fallback": True,
                          "note": "Faster and cheaper; good for everyday questions."},
    "claude-haiku-5-5": {"label": "Claude Haiku 5.5", "prices": (0.10, 0.50, 0.01, 0.125), "fallback": False,
                         "note": "Fastest and cheapest; for short answers. Prices shown apply to prompts up to 100K tokens."},
}
PRICES_CHECKED_ON = "2026-10-22"

# Error categories shown to the user. Each maps to one plain-English message and an HTTP status.
ERRORS: dict[str, tuple[int, str]] = {
    "not_configured": (503, "No AI provider is configured on the server."),
    "auth": (502, "The AI provider rejected the API key. Check ANTHROPIC_API_KEY on the server."),
    "permission": (502, "The API key is not allowed to use this model or feature."),
    "model_not_found": (502, "The AI provider does not offer this model to this API key."),
    "invalid_request": (502, "The AI provider rejected the request as invalid."),
    "rate_limit": (429, "The AI provider is rate-limiting requests. Wait a minute and try again."),
    "overloaded": (503, "The AI provider is overloaded right now. Try again shortly."),
    "server": (502, "The AI provider had an internal error. Try again shortly."),
    "timeout": (504, "The AI provider did not answer in time."),
    "network": (502, "Could not reach the AI provider. Check the server's internet connection."),
    "malformed_response": (502, "The AI provider returned a response the app could not read."),
    "unknown": (502, "The AI request failed for an unexpected reason."),
}


class AIError(Exception):
    """A provider failure with a user-facing category. Never carries secrets."""

    def __init__(self, category: str, detail: str = ""):
        self.category = category if category in ERRORS else "unknown"
        self.status_code, self.message = ERRORS[self.category]
        self.detail = detail[:300]
        super().__init__(f"{self.category}: {self.message}")


def classify_error(e: Exception) -> AIError:
    """Map an SDK exception to a category, most specific first."""
    if isinstance(e, AIError):
        return e
    try:
        import anthropic
    except ImportError:  # pragma: no cover - the SDK is a dependency
        return AIError("unknown", type(e).__name__)
    status = getattr(e, "status_code", None)
    checks = [
        (anthropic.AuthenticationError, "auth"),
        (anthropic.PermissionDeniedError, "permission"),
        (anthropic.NotFoundError, "model_not_found"),
        (anthropic.RateLimitError, "rate_limit"),
        (anthropic.BadRequestError, "invalid_request"),
        (anthropic.UnprocessableEntityError, "invalid_request"),
        (anthropic.APITimeoutError, "timeout"),  # subclass of APIConnectionError, so checked first
        (anthropic.APIConnectionError, "network"),
        (anthropic.APIResponseValidationError, "malformed_response"),
    ]
    for cls, cat in checks:
        if isinstance(e, cls):
            return AIError(cat, f"{type(e).__name__}{f' ({status})' if status else ''}")
    if isinstance(e, anthropic.APIStatusError):
        cat = "overloaded" if status == 529 else "server" if status and status >= 500 else "invalid_request"
        return AIError(cat, f"HTTP {status}")
    return AIError("unknown", type(e).__name__)


@dataclass
class AIStatus:
    configured: bool
    provider: str
    model: str | None
    message: str
    external: bool  # True when prompts/documents leave this server
    credentials_present: bool = False
    models: list[dict] = field(default_factory=list)
    timeout_seconds: float | None = None
    max_retries: int | None = None


@dataclass
class HealthRecord:
    """Result of the last health check of one model (kept in memory since the server started)."""
    model: str
    state: str = "untested"  # untested | ok | failed
    kind: str | None = None  # "access" (model lookup, no tokens) | "reply" (tiny message, costs tokens)
    checked_at: str | None = None
    latency_ms: float | None = None
    served_model: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    last_success_at: str | None = None
    successes: int = 0
    failures: int = 0


_health: dict[str, HealthRecord] = {}
_health_lock = threading.Lock()


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def record(model: str, ok: bool, kind: str, latency_ms: float | None, served_model: str | None = None,
           error: AIError | None = None) -> HealthRecord:
    """Record a check or a real request, so the health page shows actual recent behaviour."""
    with _health_lock:
        h = _health.setdefault(model, HealthRecord(model))
        h.checked_at, h.kind, h.latency_ms = now_iso(), kind, None if latency_ms is None else round(latency_ms, 1)
        if ok:
            h.state, h.served_model, h.error_category, h.error_message = "ok", served_model, None, None
            h.last_success_at, h.successes = h.checked_at, h.successes + 1
        else:
            h.state, h.failures = "failed", h.failures + 1
            h.error_category = error.category if error else "unknown"
            h.error_message = error.message if error else None
        return HealthRecord(**asdict(h))


def health_snapshot() -> dict[str, dict]:
    with _health_lock:
        return {m: asdict(h) for m, h in _health.items()}


def reset_health() -> None:
    with _health_lock:
        _health.clear()


class AIProvider:
    name = "none"
    external = False

    def status(self) -> AIStatus:
        return AIStatus(False, "none", None,
                        "No AI provider is configured. Calculations, uploads and reports still work. "
                        "Set FIS_AI_PROVIDER and an API key in backend/.env to enable the assistant.", False)

    def resolve_model(self, requested: str | None) -> str:
        raise AIError("not_configured")

    def check(self, model: str, kind: str) -> HealthRecord:
        raise AIError("not_configured")


class AnthropicProvider(AIProvider):
    name = "anthropic"
    external = True

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def has_key(self) -> bool:
        key = self.settings.anthropic_api_key
        return bool(key and key.get_secret_value())

    def status(self) -> AIStatus:
        models = [{"id": m, "label": v["label"], "note": v["note"], "prices_usd_per_mtok": dict(zip(
                   ("input", "output", "cache_read", "cache_write"), v["prices"])), "refusal_fallback": v["fallback"],
                   "default": m == self.settings.fis_ai_model} for m, v in MODELS.items()]
        common = dict(credentials_present=self.has_key, models=models, timeout_seconds=self.settings.fis_ai_timeout_seconds,
                      max_retries=self.settings.fis_ai_max_retries)
        if not self.has_key:
            return AIStatus(False, self.name, self.settings.fis_ai_model,
                            "FIS_AI_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY is empty.", True, **common)
        if self.settings.fis_ai_model not in MODELS:
            return AIStatus(False, self.name, self.settings.fis_ai_model,
                            f"FIS_AI_MODEL '{self.settings.fis_ai_model}' is not one of the supported models.", True, **common)
        return AIStatus(True, self.name, self.settings.fis_ai_model,
                        "Configured. Documents are only sent to the provider after you give consent for each request.", True, **common)

    def resolve_model(self, requested: str | None) -> str:
        """The model actually sent to the API. Unknown names are refused, never silently replaced."""
        model = requested or self.settings.fis_ai_model
        if model not in MODELS:
            raise ValueError(f"Model '{model}' is not available here. Choose one of: {', '.join(MODELS)}.")
        return model

    def client(self):
        """Server-side Anthropic client. The key never leaves the server.

        The SDK retries connection errors, 408, 409, 429 and 5xx with exponential backoff
        (max_retries); each attempt is bounded by the timeout."""
        import anthropic

        return anthropic.Anthropic(api_key=self.settings.anthropic_api_key.get_secret_value(),
                                   timeout=self.settings.fis_ai_timeout_seconds, max_retries=self.settings.fis_ai_max_retries)

    def check(self, model: str, kind: str) -> HealthRecord:
        """Health check. "access" looks the model up (verifies key, endpoint and model ID; no tokens).
        "reply" sends a tiny message and verifies the response can be parsed (costs a few tokens)."""
        if not self.has_key:
            raise AIError("not_configured", "ANTHROPIC_API_KEY is empty")
        model = self.resolve_model(model)
        start = time.perf_counter()
        try:
            client = self.client().with_options(timeout=20.0, max_retries=0)
            if kind == "access":
                info = client.models.retrieve(model)
                served = getattr(info, "id", None)
                if served != model:
                    raise AIError("malformed_response", "model lookup returned a different id")
            else:
                resp = client.messages.create(model=model, max_tokens=256, output_config={"effort": "low"},
                                              messages=[{"role": "user", "content": "Reply with the single word OK."}])
                served = getattr(resp, "model", None)
                if not isinstance(served, str) or not isinstance(getattr(resp, "content", None), list):
                    raise AIError("malformed_response", "missing model or content")
        except Exception as e:  # noqa: BLE001 - every failure is categorised and recorded
            err = classify_error(e)
            return record(model, False, kind, (time.perf_counter() - start) * 1000, error=err)
        return record(model, True, kind, (time.perf_counter() - start) * 1000, served_model=served)


def get_provider(settings: Settings) -> AIProvider:
    if settings.fis_ai_provider.lower() == "anthropic":
        return AnthropicProvider(settings)
    return AIProvider()
