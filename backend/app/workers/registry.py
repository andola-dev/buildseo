"""Task handler registry.

Handlers register by name, so a job row references a string rather than an
import path — a payload cannot be crafted to import and execute arbitrary code.
An unknown ``task_name`` fails the job rather than resolving to anything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from app.config.logging import get_logger
from app.workers.queue import TaskEnvelope

logger = get_logger(__name__)

#: A handler receives the envelope and the resources it needs, which are bound
#: by the runner (see app.workers.runner.TaskContext).
TaskHandler = Callable[..., Awaitable[None]]

_REGISTRY: dict[str, TaskHandler] = {}

# --------------------------------------------------------------------------- #
# Task names. Referenced by both the enqueuing service and the handler, so a
# typo is an import error rather than a job that never runs.
# --------------------------------------------------------------------------- #
TASK_PUBLISHER_DISCOVERY: Final = "publisher.discovery"
TASK_PUBLISHER_QUALIFY: Final = "publisher.qualify"
TASK_OPPORTUNITY_QUALIFY: Final = "opportunity.qualify"
TASK_CONTENT_GENERATE: Final = "content.generate"
TASK_SUBMISSION_VERIFY: Final = "submission.verify"
TASK_LINK_MONITOR: Final = "link.monitor"


def register(task_name: str) -> Callable[[TaskHandler], TaskHandler]:
    """Decorator registering a coroutine as the handler for ``task_name``."""

    def decorator(handler: TaskHandler) -> TaskHandler:
        if task_name in _REGISTRY:
            raise RuntimeError(f"task '{task_name}' is already registered")
        _REGISTRY[task_name] = handler
        return handler

    return decorator


def resolve(task_name: str) -> TaskHandler | None:
    """Look up a handler. ``None`` when the name is unknown."""
    return _REGISTRY.get(task_name)


def registered_tasks() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def describe(envelope: TaskEnvelope) -> str:
    """Short, non-sensitive description for a log line."""
    return f"{envelope.task_name}#{envelope.job_id}"
