"""AI provider adapters.

The security-critical property here is that a provider's error response — which
several vendors populate with the submitted API key — never reaches a log or an
API error body.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging

import httpx
import pytest

from app.config.logging import configure_logging
from app.core.exceptions import (
    ProviderError,
    ProviderNotSupportedError,
    ProviderUnavailableError,
)
from app.core.http_client import HttpClientConfig, SafeHttpClient
from app.integrations.ai.base import AIProvider, EmbeddingRequest, GenerationRequest
from app.integrations.ai.providers import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_MODELS,
    AnthropicProvider,
    CustomOpenAICompatibleProvider,
    GeminiProvider,
    OpenAIProvider,
    OpenRouterProvider,
)

pytestmark = pytest.mark.unit

API_KEY = "sk-secret-key-1234567890"
SEEN: list[dict] = []


def _handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content) if request.content else {}
    SEEN.append({"url": str(request.url), "headers": dict(request.headers), "body": body})
    path = request.url.path

    if path.endswith("/chat/completions"):
        model = body.get("model")
        if model == "boom":
            return httpx.Response(500)
        if model == "badkey":
            # Providers commonly echo the submitted key back in an error.
            return httpx.Response(401, json={"error": {"message": f"invalid key {API_KEY}"}})
        if model == "throttled":
            return httpx.Response(429)
        if model == "empty":
            return httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]})
        if model == "nochoice":
            return httpx.Response(200, json={"choices": []})
        return httpx.Response(
            200,
            json={
                "id": "cmpl-1",
                "model": "gpt-4o",
                "choices": [{"message": {"content": "Listing text"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    if path.endswith("/embeddings"):
        return httpx.Response(
            200,
            json={
                "model": "text-embedding-3-small",
                "data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}],
                "usage": {"prompt_tokens": 4},
            },
        )

    if path.endswith("/messages"):
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "model": DEFAULT_ANTHROPIC_MODEL,
                "content": [
                    {"type": "thinking", "thinking": ""},
                    {"type": "text", "text": "Anthropic listing"},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 21, "output_tokens": 9},
            },
        )

    if path.endswith(":generateContent"):
        if "blocked" in path:
            return httpx.Response(200, json={"candidates": []})
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Gemini listing"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 13, "candidatesTokenCount": 5},
                "modelVersion": "gemini-2.5-pro",
                "responseId": "g-1",
            },
        )

    if path.endswith(":embedContent"):
        return httpx.Response(200, json={"embedding": {"values": [1.0, 2.0, 3.0]}})

    return httpx.Response(404)


def make(cls, **kwargs):
    client = SafeHttpClient(
        HttpClientConfig(max_retries=0),
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )
    return cls(client=client, api_key=API_KEY, **kwargs)


def run(coro):
    return asyncio.run(coro)


class TestOpenAI:
    def test_maps_the_request_and_response(self) -> None:
        provider = make(OpenAIProvider)
        assert isinstance(provider, AIProvider)
        result = run(
            provider.generate(
                GenerationRequest(
                    prompt="write a listing",
                    model="gpt-4o",
                    system="You are terse",
                    max_tokens=500,
                    temperature=0.2,
                )
            )
        )
        assert result.text == "Listing text"
        assert result.provider == "openai"
        assert result.input_tokens == 11
        assert result.output_tokens == 7
        assert result.finish_reason == "stop"
        assert result.provider_request_id == "cmpl-1"

        body = SEEN[-1]["body"]
        assert body["messages"] == [
            {"role": "system", "content": "You are terse"},
            {"role": "user", "content": "write a listing"},
        ]
        assert body["max_completion_tokens"] == 500

    def test_sends_the_key_in_a_header_never_a_url(self) -> None:
        provider = make(OpenAIProvider)
        run(provider.generate(GenerationRequest(prompt="x", model="gpt-4o")))
        assert SEEN[-1]["headers"]["authorization"] == f"Bearer {API_KEY}"
        assert API_KEY not in SEEN[-1]["url"]

    def test_json_mode_and_tenant_parameters_are_forwarded(self) -> None:
        provider = make(OpenAIProvider)
        run(
            provider.generate(
                GenerationRequest(
                    prompt="x", model="gpt-4o", json_output=True, extra={"top_p": 0.5}
                )
            )
        )
        assert SEEN[-1]["body"]["response_format"] == {"type": "json_object"}
        assert SEEN[-1]["body"]["top_p"] == 0.5

    def test_embeddings(self) -> None:
        provider = make(OpenAIProvider)
        result = run(
            provider.embed(EmbeddingRequest(texts=("a", "b"), model="text-embedding-3-small"))
        )
        assert result.vectors == ((0.1, 0.2), (0.3, 0.4))
        assert result.input_tokens == 4


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("model", "exception", "code", "status"),
        [
            ("badkey", ProviderError, "PROVIDER_CREDENTIAL_REJECTED", 422),
            ("throttled", ProviderError, "PROVIDER_RATE_LIMITED", 429),
            ("boom", ProviderUnavailableError, "PROVIDER_UNAVAILABLE", 503),
        ],
    )
    def test_provider_statuses_map_to_domain_errors(
        self, model: str, exception: type, code: str, status: int
    ) -> None:
        provider = make(OpenAIProvider)
        with pytest.raises(exception) as excinfo:
            run(provider.generate(GenerationRequest(prompt="x", model=model)))
        assert excinfo.value.code == code
        assert excinfo.value.status_code == status

    def test_a_provider_error_echoing_the_key_does_not_leak_it(self) -> None:
        provider = make(OpenAIProvider)
        with pytest.raises(ProviderError) as excinfo:
            run(provider.generate(GenerationRequest(prompt="x", model="badkey")))
        assert API_KEY not in excinfo.value.message
        assert API_KEY not in json.dumps(excinfo.value.details)

    def test_a_provider_error_echoing_the_key_does_not_reach_the_log(self) -> None:
        configure_logging(level="INFO", json_output=True, service="t", environment="test")
        stream = io.StringIO()
        logging.getLogger().handlers[0].stream = stream

        provider = make(OpenAIProvider)
        with pytest.raises(ProviderError):
            run(provider.generate(GenerationRequest(prompt="x", model="badkey")))

        written = stream.getvalue()
        assert API_KEY not in written
        assert "provider_status" in written

    @pytest.mark.parametrize("model", ["empty", "nochoice"])
    def test_an_empty_completion_is_rejected(self, model: str) -> None:
        # Better an error than a blank listing draft stored for review.
        provider = make(OpenAIProvider)
        with pytest.raises(ProviderError) as excinfo:
            run(provider.generate(GenerationRequest(prompt="x", model=model)))
        assert excinfo.value.code == "PROVIDER_EMPTY_RESPONSE"


class TestAnthropic:
    def test_uses_the_messages_api_shape(self) -> None:
        provider = make(AnthropicProvider)
        result = run(
            provider.generate(
                GenerationRequest(
                    prompt="write",
                    model=DEFAULT_ANTHROPIC_MODEL,
                    system="Be brief",
                    max_tokens=300,
                )
            )
        )
        assert result.text == "Anthropic listing"
        assert result.input_tokens == 21
        assert result.output_tokens == 9
        assert result.finish_reason == "end_turn"

        body, headers = SEEN[-1]["body"], SEEN[-1]["headers"]
        # System prompt is top-level, not a message.
        assert body["system"] == "Be brief"
        assert body["max_tokens"] == 300
        assert body["messages"] == [{"role": "user", "content": "write"}]
        assert "temperature" not in body
        assert headers["x-api-key"] == API_KEY
        assert headers["anthropic-version"] == "2023-06-01"
        assert "authorization" not in headers

    def test_only_text_blocks_contribute_to_the_output(self) -> None:
        # The response contains a thinking block alongside the text block.
        provider = make(AnthropicProvider)
        result = run(
            provider.generate(GenerationRequest(prompt="x", model=DEFAULT_ANTHROPIC_MODEL))
        )
        assert result.text == "Anthropic listing"

    def test_json_output_is_requested_through_the_system_prompt(self) -> None:
        provider = make(AnthropicProvider)
        run(
            provider.generate(
                GenerationRequest(prompt="x", model=DEFAULT_ANTHROPIC_MODEL, json_output=True)
            )
        )
        assert "valid JSON object" in SEEN[-1]["body"]["system"]

    def test_embeddings_are_refused_rather_than_faked(self) -> None:
        provider = make(AnthropicProvider)
        with pytest.raises(ProviderNotSupportedError) as excinfo:
            run(provider.embed(EmbeddingRequest(texts=("a",), model="x")))
        assert excinfo.value.code == "EMBEDDING_NOT_SUPPORTED"


class TestGemini:
    def test_maps_the_generate_content_shape(self) -> None:
        provider = make(GeminiProvider)
        result = run(
            provider.generate(
                GenerationRequest(prompt="write", model="gemini-2.5-pro", system="Be brief")
            )
        )
        assert result.text == "Gemini listing"
        assert result.input_tokens == 13
        assert result.output_tokens == 5
        assert SEEN[-1]["body"]["systemInstruction"] == {"parts": [{"text": "Be brief"}]}

    def test_the_key_goes_in_a_header_not_the_query_string(self) -> None:
        # The documented form is ?key=..., which would put a tenant's
        # credential into any access log that records the URL.
        provider = make(GeminiProvider)
        run(provider.generate(GenerationRequest(prompt="x", model="gemini-2.5-pro")))
        assert SEEN[-1]["headers"]["x-goog-api-key"] == API_KEY
        assert "key=" not in SEEN[-1]["url"]
        assert API_KEY not in SEEN[-1]["url"]

    def test_a_filtered_response_with_no_candidates_is_an_error(self) -> None:
        provider = make(GeminiProvider)
        with pytest.raises(ProviderError) as excinfo:
            run(provider.generate(GenerationRequest(prompt="x", model="blocked-model")))
        assert excinfo.value.code == "PROVIDER_EMPTY_RESPONSE"

    def test_embeddings_batch_one_document_per_call(self) -> None:
        provider = make(GeminiProvider)
        result = run(provider.embed(EmbeddingRequest(texts=("a", "b"), model="text-embedding-004")))
        assert result.vectors == ((1.0, 2.0, 3.0), (1.0, 2.0, 3.0))


class TestOpenRouter:
    def test_reuses_the_openai_mapping_with_its_own_headers(self) -> None:
        provider = make(OpenRouterProvider)
        result = run(
            provider.generate(GenerationRequest(prompt="x", model="anthropic/claude-opus-5"))
        )
        assert result.provider == "openrouter"
        assert result.text == "Listing text"
        assert SEEN[-1]["headers"]["x-title"] == "BuildSEO"
        assert SEEN[-1]["url"].startswith("https://openrouter.ai/api/v1/")

    def test_embeddings_are_refused(self) -> None:
        provider = make(OpenRouterProvider)
        with pytest.raises(ProviderNotSupportedError):
            run(provider.embed(EmbeddingRequest(texts=("a",), model="x")))


class TestCustomEndpoint:
    def test_requires_a_base_url(self) -> None:
        with pytest.raises(ProviderError) as excinfo:
            make(CustomOpenAICompatibleProvider, base_url="")
        assert excinfo.value.code == "PROVIDER_BASE_URL_REQUIRED"

    def test_works_against_a_self_hosted_endpoint(self) -> None:
        provider = make(CustomOpenAICompatibleProvider, base_url="https://llm.example.com/v1")
        assert (
            run(provider.generate(GenerationRequest(prompt="x", model="local"))).provider
            == "custom"
        )


class TestRequestPrivacy:
    def test_a_request_repr_does_not_print_the_prompt(self) -> None:
        # A prompt carries a tenant's business content.
        request = GenerationRequest(prompt="confidential client brief", model="m")
        assert "confidential" not in repr(request)
        assert "chars>" in repr(request)


class TestDefaults:
    def test_every_supported_provider_has_a_default_model(self) -> None:
        assert set(DEFAULT_MODELS) >= {"openai", "anthropic", "gemini", "openrouter"}
