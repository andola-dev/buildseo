"""Concrete AI provider adapters.

One class per vendor, each translating the provider-neutral
:class:`GenerationRequest` into that vendor's wire format and back. Adding a
provider means adding a class here and a row in ``tenant_ai_configs`` — no
business logic changes.

Model defaults are the current flagship of each family. A tenant always
supplies an explicit model in its configuration; these constants only document
a sensible starting point for the seed and the API docs.
"""

from __future__ import annotations

from typing import Any, Final

from app.core.enums import AiProvider
from app.core.exceptions import ProviderError, ProviderNotSupportedError
from app.core.http_client import SafeHttpClient
from app.integrations.ai.base import (
    EmbeddingRequest,
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
)
from app.integrations.ai.http_provider import HttpAIProvider

# --------------------------------------------------------------------------- #
# Recommended defaults, surfaced in the API docs and the seed script.
# --------------------------------------------------------------------------- #
DEFAULT_OPENAI_MODEL: Final = "gpt-4o"
DEFAULT_OPENAI_EMBEDDING_MODEL: Final = "text-embedding-3-small"
DEFAULT_ANTHROPIC_MODEL: Final = "claude-opus-5"
DEFAULT_GEMINI_MODEL: Final = "gemini-2.5-pro"
DEFAULT_GEMINI_EMBEDDING_MODEL: Final = "text-embedding-004"
DEFAULT_OPENROUTER_MODEL: Final = "anthropic/claude-opus-5"

#: Pinned API version for Anthropic's Messages API.
ANTHROPIC_API_VERSION: Final = "2023-06-01"


class OpenAIProvider(HttpAIProvider):
    """OpenAI Chat Completions and Embeddings."""

    provider_key = AiProvider.OPENAI.value

    def __init__(
        self,
        *,
        client: SafeHttpClient,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        super().__init__(client=client, api_key=api_key, base_url=base_url)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_completion_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.json_output:
            payload["response_format"] = {"type": "json_object"}
        payload.update(request.extra)

        body, elapsed = await self._post_json("/chat/completions", payload, headers=self._headers())
        choices = body.get("choices") or []
        if not choices:
            raise ProviderError("OpenAI returned no choices", code="PROVIDER_EMPTY_RESPONSE")
        message = choices[0].get("message") or {}
        usage = body.get("usage") or {}

        return GenerationResult(
            text=self._require_text(message.get("content"), self.provider_key),
            model=str(body.get("model") or request.model),
            provider=self.provider_key,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            finish_reason=choices[0].get("finish_reason"),
            provider_request_id=body.get("id"),
            latency_ms=elapsed,
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        payload: dict[str, Any] = {"model": request.model, "input": list(request.texts)}
        payload.update(request.extra)
        body, elapsed = await self._post_json("/embeddings", payload, headers=self._headers())
        rows = body.get("data") or []
        usage = body.get("usage") or {}
        return EmbeddingResult(
            vectors=tuple(tuple(row.get("embedding") or ()) for row in rows),
            model=str(body.get("model") or request.model),
            provider=self.provider_key,
            input_tokens=usage.get("prompt_tokens"),
            latency_ms=elapsed,
        )


class AnthropicProvider(HttpAIProvider):
    """Anthropic Messages API.

    Notes that differ from the OpenAI shape: the system prompt is a top-level
    field rather than a message, ``max_tokens`` is required, the API version is
    pinned by header, and the key travels in ``x-api-key``.

    Anthropic exposes no embedding endpoint, so :meth:`embed` refuses rather
    than silently degrading — a tenant that wants embeddings configures a
    different provider for the ``embedding`` purpose.
    """

    provider_key = AiProvider.ANTHROPIC.value

    def __init__(
        self,
        *,
        client: SafeHttpClient,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
    ) -> None:
        super().__init__(client=client, api_key=api_key, base_url=base_url)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
        }

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        system = request.system
        if request.json_output:
            # The Messages API has no JSON mode on this endpoint shape, so the
            # instruction goes in the system prompt and the caller validates.
            instruction = "Respond with a single valid JSON object and nothing else."
            system = f"{system}\n\n{instruction}" if system else instruction
        if system:
            payload["system"] = system
        payload.update(request.extra)

        body, elapsed = await self._post_json("/messages", payload, headers=self._headers())

        # content is a list of typed blocks; only text blocks carry output.
        blocks = body.get("content") or []
        text = "".join(
            str(block.get("text", ""))
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        usage = body.get("usage") or {}

        return GenerationResult(
            text=self._require_text(text, self.provider_key),
            model=str(body.get("model") or request.model),
            provider=self.provider_key,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            finish_reason=body.get("stop_reason"),
            provider_request_id=body.get("id"),
            latency_ms=elapsed,
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        raise ProviderNotSupportedError(
            "Anthropic does not provide an embedding endpoint. Configure a "
            "different provider for the 'embedding' purpose.",
            code="EMBEDDING_NOT_SUPPORTED",
            details={"provider": self.provider_key},
        )


class GeminiProvider(HttpAIProvider):
    """Google Gemini generateContent and embedContent.

    The key is sent in the ``x-goog-api-key`` header rather than the documented
    ``?key=`` query parameter, so a tenant's credential cannot end up in a URL
    that gets written to an access log or an error message.
    """

    provider_key = AiProvider.GEMINI.value

    def __init__(
        self,
        *,
        client: SafeHttpClient,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        super().__init__(client=client, api_key=api_key, base_url=base_url)

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._api_key}

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        generation_config: dict[str, Any] = {
            "maxOutputTokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.json_output:
            generation_config["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": generation_config,
        }
        if request.system:
            payload["systemInstruction"] = {"parts": [{"text": request.system}]}
        payload.update(request.extra)

        body, elapsed = await self._post_json(
            f"/models/{request.model}:generateContent", payload, headers=self._headers()
        )
        candidates = body.get("candidates") or []
        if not candidates:
            # Gemini returns no candidate when a safety filter blocks the reply.
            raise ProviderError(
                "Gemini returned no candidates; the request may have been filtered",
                code="PROVIDER_EMPTY_RESPONSE",
                details={"provider": self.provider_key},
            )
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        usage = body.get("usageMetadata") or {}

        return GenerationResult(
            text=self._require_text(text, self.provider_key),
            model=str(body.get("modelVersion") or request.model),
            provider=self.provider_key,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            finish_reason=candidates[0].get("finishReason"),
            provider_request_id=body.get("responseId"),
            latency_ms=elapsed,
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        vectors: list[tuple[float, ...]] = []
        elapsed_total = 0
        # embedContent takes one document per call.
        for text in request.texts:
            body, elapsed = await self._post_json(
                f"/models/{request.model}:embedContent",
                {"content": {"parts": [{"text": text}]}},
                headers=self._headers(),
            )
            elapsed_total += elapsed
            values = (body.get("embedding") or {}).get("values") or []
            vectors.append(tuple(float(value) for value in values))

        return EmbeddingResult(
            vectors=tuple(vectors),
            model=request.model,
            provider=self.provider_key,
            latency_ms=elapsed_total,
        )


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter, which exposes an OpenAI-compatible Chat Completions API.

    Inherits the OpenAI request/response mapping and only changes the base URL,
    the attribution headers OpenRouter asks integrators to send, and the fact
    that it offers no embedding endpoint.
    """

    provider_key = AiProvider.OPENROUTER.value

    def __init__(
        self,
        *,
        client: SafeHttpClient,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        super().__init__(client=client, api_key=api_key, base_url=base_url)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://buildseo.example",
            "X-Title": "BuildSEO",
        }

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        raise ProviderNotSupportedError(
            "OpenRouter does not expose an embedding endpoint. Configure a "
            "different provider for the 'embedding' purpose.",
            code="EMBEDDING_NOT_SUPPORTED",
            details={"provider": self.provider_key},
        )


class CustomOpenAICompatibleProvider(OpenAIProvider):
    """A self-hosted or third-party OpenAI-compatible endpoint.

    The escape hatch for a tenant running vLLM, Ollama behind a gateway, or an
    enterprise proxy. The base URL comes from the credential's non-secret
    ``metadata.base_url``, and the shared HTTP client's public-host guard still
    applies — so this cannot be pointed at an internal address.
    """

    provider_key = AiProvider.CUSTOM.value

    def __init__(self, *, client: SafeHttpClient, api_key: str, base_url: str) -> None:
        if not base_url:
            raise ProviderError(
                "A custom AI provider requires metadata.base_url on its credential",
                code="PROVIDER_BASE_URL_REQUIRED",
                status_code=422,
            )
        super().__init__(client=client, api_key=api_key, base_url=base_url)


#: Recommended model per provider, used by the seed script and the docs.
DEFAULT_MODELS: dict[str, str] = {
    AiProvider.OPENAI.value: DEFAULT_OPENAI_MODEL,
    AiProvider.ANTHROPIC.value: DEFAULT_ANTHROPIC_MODEL,
    AiProvider.GEMINI.value: DEFAULT_GEMINI_MODEL,
    AiProvider.OPENROUTER.value: DEFAULT_OPENROUTER_MODEL,
}

DEFAULT_EMBEDDING_MODELS: dict[str, str] = {
    AiProvider.OPENAI.value: DEFAULT_OPENAI_EMBEDDING_MODEL,
    AiProvider.GEMINI.value: DEFAULT_GEMINI_EMBEDDING_MODEL,
}
