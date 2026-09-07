"""Service assembly.

Domain services live in their own packages (``app.auth``, ``app.publishers``,
``app.submissions``, …) so each module owns its vocabulary. This package holds
the single place that *wires* them together from a session and the process-wide
resource container.

One assembler, used by both the HTTP dependency layer and the worker runner, is
what keeps a background job's service graph identical to a request's — same
repositories, same tenant-scoped session, same audit trail.
"""

from app.services.factory import ServiceFactory

__all__ = ["ServiceFactory"]
