"""Manual submission: the default, and the MVP's primary path.

Nothing is sent anywhere. The provider records that a person is to perform (or
has performed) the submission, which is the honest model for the large
majority of directories: they expect a human, often behind an account or a
CAPTCHA, and automating that would mean circumventing their controls.
"""

from __future__ import annotations

from app.core.enums import SubmissionMethod
from app.integrations.submission.base import (
    SubmissionOutcome,
    SubmissionOutcomeStatus,
    SubmissionRequest,
)


class ManualSubmissionProvider:
    """Records a submission for a human to carry out."""

    method = SubmissionMethod.MANUAL.value

    async def submit(self, request: SubmissionRequest) -> SubmissionOutcome:
        return SubmissionOutcome(
            status=SubmissionOutcomeStatus.RECORDED,
            submitted_url=request.submission_url,
            reason="recorded_for_manual_submission",
            evidence={"method": self.method},
        )
