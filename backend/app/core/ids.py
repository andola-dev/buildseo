"""Identifier generation.

UUIDv7 (RFC 9562) is used for every primary key: it is a UUID, so it fits
``uuid`` columns and leaks no sequential counter, but its leading 48-bit
Unix-millisecond timestamp makes inserts append-mostly in a B-tree. That keeps
index bloat and page splits down on the high-volume tables (opportunities,
audit_logs, ai_usage_records) where a random UUIDv4 would scatter writes.

Ids generated without an explicit timestamp are additionally **monotonic**:
RFC 9562 §6.2's monotonic-counter method seeds a counter in the 12 ``rand_a``
bits and increments it within a millisecond. Without that, two ids created in
the same millisecond sort arbitrarily, which would make an id useless as a
stable insertion-order key or a pagination cursor. The 62 ``rand_b`` bits stay
random, so ids remain unguessable.
"""

from __future__ import annotations

import os
import threading
import time
from uuid import UUID

_VERSION_7 = 0x7000
_VARIANT_RFC4122 = 0x8000

#: ``rand_a`` is 12 bits, so 4096 ordered ids per millisecond.
_COUNTER_BITS = 12
_COUNTER_MAX = (1 << _COUNTER_BITS) - 1
#: Seed the counter in the low half, leaving headroom to increment before it
#: overflows while still not being predictable.
_COUNTER_SEED_BITS = 10

_lock = threading.Lock()
_last_timestamp_ms = -1
_counter = 0


def _next_monotonic() -> tuple[int, int]:
    """Return ``(timestamp_ms, counter)``, strictly increasing across calls."""
    global _last_timestamp_ms, _counter

    with _lock:
        now = int(time.time() * 1000)
        if now > _last_timestamp_ms:
            _last_timestamp_ms = now
            _counter = int.from_bytes(os.urandom(2), "big") >> (16 - _COUNTER_SEED_BITS)
        elif _counter >= _COUNTER_MAX:
            # More than 4096 ids in one millisecond: borrow from the next
            # millisecond rather than emit a duplicate or go backwards.
            _last_timestamp_ms += 1
            _counter = int.from_bytes(os.urandom(2), "big") >> (16 - _COUNTER_SEED_BITS)
        else:
            # Same millisecond, or the wall clock stepped backwards (NTP): keep
            # the previous timestamp so ordering never regresses.
            _counter += 1
        return _last_timestamp_ms, _counter


def uuid7(*, timestamp_ms: int | None = None) -> UUID:
    """Generate a UUIDv7.

    Layout (RFC 9562 §5.7)::

        unix_ts_ms (48 bits) | ver (4) | rand_a (12) | var (2) | rand_b (62)

    With no arguments, ids are monotonically increasing. Passing an explicit
    ``timestamp_ms`` produces a fully random ``rand_a`` instead, for
    deterministic tests and back-dated records; ids sharing an explicit
    timestamp are unordered relative to each other.
    """
    if timestamp_ms is None:
        ts, rand_a = _next_monotonic()
    else:
        if not 0 <= timestamp_ms < 1 << 48:
            raise ValueError("timestamp out of range for UUIDv7")
        ts = timestamp_ms
        rand_a = int.from_bytes(os.urandom(2), "big") & _COUNTER_MAX

    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)

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
