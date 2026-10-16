"""Server-side AI provider abstraction.

The provider is selected with FIS_AI_PROVIDER. API keys are read only on the server and are
never returned to the browser. When no provider is configured, every non-AI feature keeps
working and AI-only endpoints return a clear "not configured" response.

Calculations are never delegated to the AI model: the assistant (app/ai/assistant.py) calls the
deterministic functions in app.finance as tools and uses the model for explanation.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings


@dataclass
class AIStatus:
    configured: bool
    provider: str
    model: str | None
    message: str
    external: bool  # True when prompts/documents leave this server


class AIProvider:
    name = "none"

    def status(self) -> AIStatus:
        return AIStatus(False, "none", None,
                        "No AI provider is configured. Calculations, uploads and reports still work. "
                        "Set FIS_AI_PROVIDER and an API key in backend/.env to enable the assistant.", False)


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> AIStatus:
        key = self.settings.anthropic_api_key
        if not key or not key.get_secret_value():
            return AIStatus(False, self.name, self.settings.fis_ai_model,
                            "FIS_AI_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY is empty.", True)
        return AIStatus(True, self.name, self.settings.fis_ai_model,
                        "Configured. Documents are only sent to the provider after you give consent for each request.", True)


    def client(self):
        """Server-side Anthropic client. The key never leaves the server."""
        import anthropic

        return anthropic.Anthropic(api_key=self.settings.anthropic_api_key.get_secret_value(), timeout=180.0, max_retries=2)


def get_provider(settings: Settings) -> AIProvider:
    if settings.fis_ai_provider.lower() == "anthropic":
        return AnthropicProvider(settings)
    return AIProvider()
