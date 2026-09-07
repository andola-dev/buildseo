"""The AI provider contract.

``AIProvider`` is the only AI-shaped thing the business layer knows about. It
asks for a *purpose* (``content_generation``) and receives an implementation
chosen from the tenant's configuration, so no service ever names a vendor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

DEFAULT_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.4


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """A text-generation call, expressed provider-neutrally."""

    prompt: str
    model: str
    system: str | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    #: Ask the provider for JSON. Providers that cannot enforce it fall back to
    #: instructing the model, and the caller validates the result either way.
    json_output: bool = False
    #: Extra provider-specific parameters from the tenant's configuration.
    #: Validated to exclude secret-shaped keys before it is stored.
    extra: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        """Redacted: a prompt can contain a tenant's business content."""
        return (
            f"GenerationRequest(model={self.model!r}, max_tokens={self.max_tokens}, "
            f"prompt=<{len(self.prompt)} chars>)"
        )


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """The provider's answer plus the accounting fields."""

    text: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    #: The provider's own request identifier, for correlating support tickets.
    provider_request_id: str | None = None
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    """An embedding call."""

    texts: tuple[str, ...]
    model: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    model: str
    provider: str
    input_tokens: int | None = None
    latency_ms: int | None = None


@runtime_checkable
class AIProvider(Protocol):
    """What the application requires of any LLM provider."""

    #: Stable key matching ``credentials.provider`` and ``tenant_ai_configs.provider``.
    provider_key: str

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Produce text.

        Raises:
            ProviderError / ProviderUnavailableError / ProviderTimeoutError:
                normalised failures. Implementations must never surface a raw
                provider response body, which can echo the submitted API key.
        """
        ...

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        """Produce embedding vectors.

        Raises:
            ProviderNotSupportedError: the provider offers no embedding model.
        """
        ...
