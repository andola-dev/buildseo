"""Submission providers.

The form adapter's contract is mostly about what it refuses to do: any CAPTCHA,
anti-bot challenge, login requirement or stated automation restriction is a
hard stop that routes the submission to a person.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.http_client import HttpClientConfig, SafeHttpClient
from app.integrations.submission.base import (
    SubmissionOutcomeStatus,
    SubmissionProvider,
    SubmissionRequest,
)
from app.integrations.submission.form import FormSubmissionProvider
from app.integrations.submission.manual import ManualSubmissionProvider

pytestmark = pytest.mark.unit

CLEAN_FORM = """<html><body><form action="/add" method="post">
<input name="business_name"><input name="url"><textarea name="description"></textarea>
</form></body></html>"""

CAPTCHA_FORM = """<html><body><form action="/add" method="post">
<input name="url"><div class="g-recaptcha" data-sitekey="x"></div>
</form></body></html>"""

LOGIN_REQUIRED = """<html><body><p>You must be logged in to submit a listing.</p>
<form><input name="url"></form></body></html>"""

ANTI_BOT = """<html><body>Checking your browser before accessing.
Please enable JavaScript and cookies to continue.</body></html>"""

NO_AUTOMATION = """<html><body><form><input name="url"></form>
<p>Automated submissions are not permitted.</p></body></html>"""

NO_FORM = "<html><body><p>Contact us by post.</p></body></html>"


def _handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    pages = {
        "clean.example": CLEAN_FORM,
        "captcha.example": CAPTCHA_FORM,
        "login.example": LOGIN_REQUIRED,
        "antibot.example": ANTI_BOT,
        "noautomation.example": NO_AUTOMATION,
        "noform.example": NO_FORM,
    }
    if host in pages:
        return httpx.Response(200, text=pages[host])
    if host == "gone.example":
        return httpx.Response(500)
    if host == "dead.example":
        raise httpx.ConnectError("no route")
    return httpx.Response(404)


def make_form_provider(*, allow_automatic: bool = False) -> FormSubmissionProvider:
    client = SafeHttpClient(
        HttpClientConfig(max_retries=0),
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )
    return FormSubmissionProvider(client=client, allow_automatic_submission=allow_automatic)


def request_for(submission_url: str | None) -> SubmissionRequest:
    return SubmissionRequest(
        target_url="https://client.example/",
        submission_url=submission_url,
        title="Client",
        description="A description",
        anchor_text="Client",
    )


def run(coro):
    return asyncio.run(coro)


class TestManualProvider:
    def test_satisfies_the_protocol(self) -> None:
        assert isinstance(ManualSubmissionProvider(), SubmissionProvider)

    def test_records_without_sending_anything(self) -> None:
        provider = ManualSubmissionProvider()
        outcome = run(provider.submit(request_for("https://dir.example/submit")))
        assert outcome.status is SubmissionOutcomeStatus.RECORDED
        assert outcome.submitted_url == "https://dir.example/submit"
        assert not outcome.needs_human


class TestFormProviderHardStops:
    @pytest.mark.parametrize(
        ("host", "expected_blocker"),
        [
            ("captcha.example", "captcha_present"),
            ("login.example", "login_required"),
            ("antibot.example", "anti_bot_challenge"),
            ("noautomation.example", "automation_prohibited"),
        ],
    )
    def test_every_blocker_routes_the_submission_to_a_human(
        self, host: str, expected_blocker: str
    ) -> None:
        provider = make_form_provider(allow_automatic=True)
        outcome = run(provider.submit(request_for(f"https://{host}/submit")))
        assert outcome.status is SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL
        assert outcome.needs_human
        assert expected_blocker in (outcome.reason or "")
        assert expected_blocker in outcome.evidence["blockers"]

    def test_a_captcha_is_never_bypassed_even_with_automation_enabled(self) -> None:
        # There is deliberately no configuration that changes this.
        provider = make_form_provider(allow_automatic=True)
        outcome = run(provider.submit(request_for("https://captcha.example/submit")))
        assert outcome.needs_human


class TestFormProviderPreflight:
    def test_a_clean_form_still_goes_to_a_human_by_default(self) -> None:
        # The MVP's terminal branch: the inspection is handed over, not acted on.
        provider = make_form_provider()
        outcome = run(provider.submit(request_for("https://clean.example/submit")))
        assert outcome.status is SubmissionOutcomeStatus.BLOCKED_REQUIRES_MANUAL
        assert outcome.reason == "automatic_submission_disabled"
        assert outcome.evidence["preflight"] == "clean"

    def test_the_form_fields_are_recorded_for_the_person_doing_the_work(self) -> None:
        provider = make_form_provider()
        outcome = run(provider.submit(request_for("https://clean.example/submit")))
        assert outcome.evidence["form_detected"] is True
        assert set(outcome.evidence["form_fields"]) == {
            "business_name",
            "url",
            "description",
        }

    def test_a_page_with_no_form_is_reported(self) -> None:
        provider = make_form_provider()
        outcome = run(provider.submit(request_for("https://noform.example/submit")))
        assert outcome.reason == "no_form_found"

    def test_a_missing_submission_url_needs_a_human(self) -> None:
        provider = make_form_provider()
        outcome = run(provider.submit(request_for(None)))
        assert outcome.reason == "no_submission_url_known"

    @pytest.mark.parametrize("host", ["gone.example", "dead.example"])
    def test_an_unreachable_target_needs_a_human(self, host: str) -> None:
        provider = make_form_provider()
        outcome = run(provider.submit(request_for(f"https://{host}/submit")))
        assert outcome.needs_human
        assert "preflight" in (outcome.reason or "")

    def test_a_non_public_target_is_refused(self) -> None:
        provider = make_form_provider()
        outcome = run(provider.submit(request_for("http://127.0.0.1/submit")))
        assert outcome.needs_human
