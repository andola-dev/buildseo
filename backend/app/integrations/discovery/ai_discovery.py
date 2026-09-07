"""AI-assisted discovery.

Asks the tenant's configured LLM to name directories that fit a brief. Useful
for niches a keyword search misses, and it costs the tenant's own AI budget.

The model's output is treated as untrusted suggestion, not fact: every
candidate goes through the same domain canonicalisation, public-host guard,
de-duplication and qualification as any other source. A hallucinated domain
simply fails to resolve during qualification and is rejected.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from app.config.logging import get_logger
from app.core.domains import is_public_host, normalize_url
from app.core.enums import PublisherCategory, SubmissionMethod
from app.core.exceptions import ProviderError, ValidationError
from app.integrations.ai.base import AIProvider, GenerationRequest
from app.integrations.discovery.base import (
    DiscoveredPublisher,
    DiscoveryProviderInfo,
    DiscoveryQuery,
)

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are a research assistant for a link-building platform \
that only works with legitimate, free online listing and directory sites.

Suggest real, currently-operating directory or listing websites that accept \
free submissions and that fit the brief.

Rules you must follow:
- Only free directories, free business/company listings, free local listings, \
free startup or software directories, review platforms with free profiles, and \
similar legitimate listing sites.
- Never suggest paid guest post sites, sponsored article placements, link \
marketplaces, private blog networks, link farms, or any site whose purpose is \
selling links.
- Never invent a domain. If you are not confident a site exists, omit it.

Reply with a single JSON object of the form:
{"publishers": [{"website_url": "...", "name": "...", "category": "...", \
"country": "US or null", "description": "..."}]}

Valid category values: %s
""" % ", ".join(  # noqa: UP031 - readable inline substitution of the enum list
    category.value for category in PublisherCategory
)


class AiDiscoveryProvider:
    """Uses the tenant's LLM to brainstorm directory candidates."""

    info = DiscoveryProviderInfo(
        key="ai",
        name="AI suggestions",
        description=(
            "Asks the workspace's configured AI provider to suggest free listing "
            "sites for a brief. Suggestions are treated as unverified candidates "
            "and must pass qualification like any other."
        ),
        requires_credential=True,
        credential_provider="(the workspace's configured AI provider)",
    )

    def __init__(self, *, provider: AIProvider, model: str) -> None:
        self._provider = provider
        self._model = model

    async def search(self, query: DiscoveryQuery) -> list[DiscoveredPublisher]:
        result = await self._provider.generate(
            GenerationRequest(
                prompt=self._build_prompt(query),
                model=self._model,
                system=_SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.5,
                json_output=True,
            )
        )
        return self._parse(result.text, limit=query.limit)

    @staticmethod
    def _build_prompt(query: DiscoveryQuery) -> str:
        lines = [f"Suggest up to {query.limit} free listing sites."]
        if query.keywords:
            lines.append(f"Industry or topic: {', '.join(query.keywords)}.")
        if query.country:
            lines.append(f"Target country: {query.country}.")
        if query.language:
            lines.append(f"Target language: {query.language}.")
        if query.category:
            lines.append(f"Preferred category: {query.category.value}.")
        return " ".join(lines)

    def _parse(self, text: str, *, limit: int) -> list[DiscoveredPublisher]:
        """Parse the model's JSON, discarding anything malformed.

        A model can return prose around its JSON or an unexpected shape, so
        parsing failures raise (the run is recorded FAILED) while individual
        unusable entries are skipped.
        """
        payload = _extract_json(text)
        entries = payload.get("publishers")
        if not isinstance(entries, list):
            raise ProviderError(
                "The AI provider did not return a 'publishers' list",
                code="AI_DISCOVERY_BAD_SHAPE",
            )

        candidates: list[DiscoveredPublisher] = []
        seen: set[str] = set()
        for entry in entries[: limit * 2]:
            candidate = self._to_candidate(entry)
            if candidate is None or candidate.website_url in seen:
                continue
            seen.add(candidate.website_url)
            candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return candidates

    @staticmethod
    def _to_candidate(entry: Any) -> DiscoveredPublisher | None:
        if not isinstance(entry, dict):
            return None
        raw_url = str(entry.get("website_url") or "").strip()
        if not raw_url:
            return None
        try:
            website_url = normalize_url(raw_url)
        except ValidationError:
            # A hallucinated or malformed domain: drop it silently.
            return None

        host = urlsplit(website_url).hostname or ""
        if not is_public_host(host):
            return None

        raw_category = str(entry.get("category") or "").strip().upper()
        category = (
            PublisherCategory(raw_category)
            if raw_category in {member.value for member in PublisherCategory}
            else None
        )
        raw_country = str(entry.get("country") or "").strip().upper()

        return DiscoveredPublisher(
            website_url=website_url,
            name=str(entry.get("name") or "").strip() or None,
            description=str(entry.get("description") or "").strip() or None,
            category=category,
            country=raw_country if len(raw_country) == 2 and raw_country.isalpha() else None,
            submission_method=SubmissionMethod.UNKNOWN,
            source_metadata={"source": "ai"},
        )


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a model reply, tolerating stray prose."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        raise ProviderError("The AI provider did not return JSON", code="AI_DISCOVERY_BAD_SHAPE")
    try:
        parsed = json.loads(stripped[start : end + 1])
    except ValueError as exc:
        raise ProviderError(
            "The AI provider returned malformed JSON", code="AI_DISCOVERY_BAD_SHAPE"
        ) from exc
    if not isinstance(parsed, dict):
        raise ProviderError(
            "The AI provider returned an unexpected JSON shape",
            code="AI_DISCOVERY_BAD_SHAPE",
        )
    return parsed
