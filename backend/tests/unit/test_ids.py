"""UUIDv7 identifier generation."""

from __future__ import annotations

import time

import pytest

from app.core.ids import uuid7, uuid7_timestamp_ms

pytestmark = pytest.mark.unit


def test_generates_valid_uuid_version_7() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_ids_are_unique() -> None:
    assert len({uuid7() for _ in range(10_000)}) == 10_000


def test_ids_sort_by_creation_time() -> None:
    # The property that keeps index writes append-mostly.
    assert uuid7(timestamp_ms=1_000) < uuid7(timestamp_ms=2_000)


def test_ids_are_strictly_monotonic_even_within_one_millisecond() -> None:
    # A tight loop generates thousands of ids inside a single millisecond. A
    # purely random rand_a would order them arbitrarily, which would make an id
    # useless as an insertion-order key or a pagination cursor.
    ids = [uuid7() for _ in range(20_000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_monotonicity_survives_the_per_millisecond_counter_overflowing() -> None:
    # rand_a is 12 bits, so more than ~4096 ids in one millisecond must borrow
    # from the next rather than repeat or regress.
    ids = [uuid7() for _ in range(50_000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_embedded_timestamp_is_recoverable() -> None:
    assert uuid7_timestamp_ms(uuid7(timestamp_ms=1_700_000_000_000)) == 1_700_000_000_000
    assert abs(uuid7_timestamp_ms(uuid7()) - int(time.time() * 1000)) < 5_000


def test_random_bits_differ_within_the_same_millisecond() -> None:
    # Same timestamp prefix must still yield unguessable, distinct ids.
    same_ms = {uuid7(timestamp_ms=1_700_000_000_000) for _ in range(1_000)}
    assert len(same_ms) == 1_000


def test_rejects_an_out_of_range_timestamp() -> None:
    with pytest.raises(ValueError):
        uuid7(timestamp_ms=-1)
    with pytest.raises(ValueError):
        uuid7(timestamp_ms=1 << 48)


def test_rejects_a_non_v7_uuid() -> None:
    from uuid import uuid4

    with pytest.raises(ValueError):
        uuid7_timestamp_ms(uuid4())
