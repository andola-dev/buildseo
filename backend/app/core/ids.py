"""Identifier generation.

UUIDv7 (RFC 9562) is used for every primary key: it is a UUID, so it fits
``uuid`` columns and leaks no sequential counter, but its leading 48-bit
Unix-millisecond timestamp makes inserts append-mostly in a B-tree. That keeps
index bloat and page splits down on the high-volume tables (opportunities,
audit_logs, ai_usage_records) where a random UUIDv4 would scatter writes.
"""

from __future__ import annotations

import os
import time
from uuid import UUID

_VERSION_7 = 0x7000
_VARIANT_RFC4122 = 0x8000


def uuid7(*, timestamp_ms: int | None = None) -> UUID:
    """Generate a UUIDv7.

    Layout (RFC 9562 §5.7)::

        unix_ts_ms (48 bits) | ver (4) | rand_a (12) | var (2) | rand_b (62)

    ``rand_a``/``rand_b`` come from ``os.urandom``, so ids remain unguessable
    even though the timestamp prefix is monotonic.
    """
    ts = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    if not 0 <= ts < 1 << 48:
        raise ValueError("timestamp out of range for UUIDv7")

    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = (rand >> 62) & 0x0FFF
    rand_b = rand & ((1 << 62) - 1)

    value = ts << 80
    value |= (_VERSION_7 | rand_a) << 64
    value |= (_VARIANT_RFC4122 | (rand_b >> 48)) << 48
    value |= rand_b & ((1 << 48) - 1)
    return UUID(int=value)


def uuid7_timestamp_ms(value: UUID) -> int:
    """Extract the embedded millisecond timestamp from a UUIDv7."""
    if value.version != 7:
        raise ValueError("not a UUIDv7")
    return value.int >> 80
