"""Form submission adapter — future-ready, and deliberately conservative.

This exists so the architecture has a place for automated form submission
where it is technically and legally appropriate: a directory with a plain,
open, POST-able form that invites submissions.

It performs a **pre-flight check only** and, in this MVP, always hands the
submission back to a human. That is not an unfinished feature; it is the
correct default:

* If the page presents a CAPTCHA or an anti-bot challenge, the answer is a
  human — solving or evading either is out of scope and always will be.
* If the page requires an account or a login, the answer is a human.
* If ``robots.txt`` or the page's terms restrict automated submission, the
  answer is a human.
* Even with none of those present, blindly POSTing a discovered form risks
  submitting garbage to a real directory under a client's name. Enabling
  automatic delivery is a decision for a specific, reviewed directory, which
  is why it is gated behind ``allow_automatic_submission`` and defaults off.

The pre-flight result is recorded as evidence, so the human doing the work
knows what the form looks like before they open it.
"""

from __future__ import annotations

import re

from app.config.logging import get_logger
from app.core.enums import SubmissionMethod
from app.core.exceptions import ProviderError, ValidationError
from app.core.http_client import SafeHttpClient
from app.integrations.submission.base import (
    SubmissionOutcome,
    SubmissionOutcomeStatus,
    SubmissionRequest,
)

logger = get_logger(__name__)

_FORM_RE = re.compile(r"<form\b[^>]*>", re.IGNORECASE)
_INPUT_NAME_RE = re.compile(r"<(?:input|textarea|select)\b[^>]*name=[\"']([^\"']+)", re.IGNORECASE)

#: Markers that mean a human must do this. Each one is a hard stop.
_HUMAN_REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "captcha_present": (
        "recaptcha",
        "g-recaptcha",
        "hcaptcha",
        "turnstile",
        "captcha",
        "are you human",
    ),
    "login_required": (
        "sign in to submit",
        "log in to submit",
        "you must be logged in",
        "create an account to submit",
        "register to submit",
    ),
    "anti_bot_challenge": (
        "checking your browser",
        "enable javascript and cookies to continue",
        "cf-challenge",
        "ddos protection by",
    ),
    "automation_prohibited": (
        "automated submissions are not permitted",
        "no automated submissions",
        "bots are not allowed",
        "manual review required before submission",
    ),
}


class FormSubmissionProvider:
    """Inspects a submission form and reports whether a human is required."""

    method = SubmissionMethod.FORM.value

    def __init__(
        self,
        *,
        client: SafeHttpClient,
        allow_automatic_submission: bool = False,
    ) -> None:
        self._client = client
        # Off by default and never flipped on globally: enabling delivery is a
        # per-directory decision made by a person who has read the form.
        self._allow_automatic = allow_automatic_submission

    async def submit(self, request: SubmissionRequest) -> SubmissionOutcome:
        if not request.submission_url:
            return SubmissionOutcome(
                status=SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL,
                reason="no_submission_url_known",
            )

        try:
            response = await self._client.get(
                request.submission_url, headers={"Accept": "text/html"}
            )
        except (ProviderError, ValidationError) as exc:
            # Could not even look at the form, so a human should.
            return SubmissionOutcome(
                status=SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL,
                reason=f"preflight_failed:{exc.code.lower()}",
                evidence={"submission_url": request.submission_url},
            )

        if not response.is_success:
            return SubmissionOutcome(
                status=SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL,
                reason=f"preflight_http_{response.status_code}",
            )

        html = response.text
        lowered = html.lower()
        blockers = [
            marker
            for marker, phrases in _HUMAN_REQUIRED_MARKERS.items()
            if any(phrase in lowered for phrase in phrases)
        ]
        has_form = bool(_FORM_RE.search(html))
        field_names = sorted(set(_INPUT_NAME_RE.findall(html)))[:40]

        evidence: dict[str, object] = {
            "submission_url": request.submission_url,
            "form_detected": has_form,
            "form_fields": field_names,
            "blockers": blockers,
        }

        if blockers:
            logger.info(
                "form submission requires a human",
                extra={"blockers": blockers, "method": self.method},
            )
            return SubmissionOutcome(
                status=SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL,
                reason=f"requires_human:{','.join(blockers)}",
                evidence=evidence,
            )

        if not has_form:
            return SubmissionOutcome(
                status=SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL,
                reason="no_form_found",
                evidence=evidence,
            )

        if not self._allow_automatic:
            # The MVP's terminal branch. The form looks clean, and the
            # inspection is handed to the person who will fill it in.
            return SubmissionOutcome(
                status=SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL,
                reason="automatic_submission_disabled",
                evidence={**evidence, "preflight": "clean"},
            )

        # Reached only if an operator has explicitly enabled delivery for a
        # reviewed directory. Left unimplemented rather than guessed: mapping
        # arbitrary form fields onto listing data is per-directory work, and a
        # wrong guess submits nonsense to a real publisher under a client's
        # name.
        logger.warning(
            "automatic form delivery is enabled but not implemented for this target",
            extra={"method": self.method},
        )
        return SubmissionOutcome(
            status=SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL,
            reason="automatic_delivery_not_implemented_for_target",
            evidence={**evidence, "preflight": "clean"},
        )
