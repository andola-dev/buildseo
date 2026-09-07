"""Domain and URL canonicalisation.

The de-duplication guarantee for publishers rests entirely on these functions:
if two spellings of one site produce different canonical forms, the unique
constraint on ``(tenant_id, normalized_domain)`` stops protecting anything.
"""

from __future__ import annotations

import pytest

from app.core.domains import (
    extract_domain,
    is_public_host,
    mask_secret,
    normalize_domain,
    normalize_url,
    registrable_domain,
    same_site,
)
from app.core.exceptions import ValidationError

pytestmark = pytest.mark.unit


class TestNormalizeDomain:
    @pytest.mark.parametrize(
        "value",
        [
            "example.com",
            "EXAMPLE.com.",
            "www.example.com",
            "https://example.com",
            "https://www.example.com/",
            "http://user:pw@www.example.com:443/listings?utm_source=x#frag",
            "  WWW.Example.COM  ",
            "//example.com",
            "example.com/a/b",
        ],
    )
    def test_every_spelling_of_one_site_collapses_to_one_form(self, value: str) -> None:
        assert normalize_domain(value) == "example.com"

    def test_internationalised_names_fold_to_punycode(self) -> None:
        assert normalize_domain("bücher.de") == "xn--bcher-kva.de"
        assert normalize_domain("xn--bcher-kva.de") == "xn--bcher-kva.de"

    def test_only_a_leading_www_is_stripped(self) -> None:
        assert normalize_domain("sub.www.example.com") == "sub.www.example.com"
        assert normalize_domain("www.www.example.com") == "example.com"

    def test_stripping_www_never_leaves_a_single_label(self) -> None:
        # Otherwise "www.co.uk" would normalise to "uk".
        assert normalize_domain("www.co.uk") == "co.uk"

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "localhost",
            "com",
            "1.2.3.4",
            "http://[::1]/",
            "a..b.com",
            "-bad.com",
            "bad-.com",
            "example.123",
            "x" * 300 + ".com",
        ],
    )
    def test_rejects_anything_that_is_not_a_public_domain(self, value: str) -> None:
        with pytest.raises(ValidationError):
            normalize_domain(value)

    def test_extract_domain_accepts_a_url_or_a_bare_domain(self) -> None:
        assert extract_domain("https://www.example.com/x") == "example.com"
        assert extract_domain("example.com") == "example.com"


class TestRegistrableDomain:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("example.com", "example.com"),
            ("a.b.example.com", "example.com"),
            ("blog.example.co.uk", "example.co.uk"),
            ("shop.example.com.au", "example.com.au"),
        ],
    )
    def test_groups_subdomains_under_their_apex(self, value: str, expected: str) -> None:
        assert registrable_domain(value) == expected


class TestSameSite:
    def test_matches_across_spellings(self) -> None:
        assert same_site("https://www.Example.com/x", "example.com")

    def test_distinguishes_different_sites(self) -> None:
        assert not same_site("example.com", "example.net")

    def test_returns_false_rather_than_raising_on_junk(self) -> None:
        assert not same_site("example.com", "!!!")


class TestNormalizeUrl:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("example.com", "https://example.com"),
            ("HTTP://Example.com:80/Path/?b=1#f", "http://example.com/Path/?b=1"),
            ("https://example.com/", "https://example.com"),
            ("https://example.com:8443/x", "https://example.com:8443/x"),
        ],
    )
    def test_canonicalises_scheme_host_port_and_fragment(self, value: str, expected: str) -> None:
        assert normalize_url(value) == expected

    def test_preserves_path_case(self) -> None:
        # Directory submission paths are frequently case-sensitive.
        assert normalize_url("https://example.com/Submit/Listing") == (
            "https://example.com/Submit/Listing"
        )

    @pytest.mark.parametrize("value", ["ftp://example.com", "file:///etc/passwd", ""])
    def test_rejects_non_http_schemes(self, value: str) -> None:
        with pytest.raises(ValidationError):
            normalize_url(value)


class TestIsPublicHost:
    @pytest.mark.parametrize("host", ["example.com", "8.8.8.8", "1.1.1.1"])
    def test_allows_public_destinations(self, host: str) -> None:
        assert is_public_host(host)

    @pytest.mark.parametrize(
        "host",
        [
            "localhost",
            "127.0.0.1",
            "10.0.0.5",
            "192.168.1.1",
            "172.16.5.5",
            # The cloud metadata endpoint: the reason this guard exists.
            "169.254.169.254",
            "::1",
            "0.0.0.0",
            "foo.internal",
            "bar.local",
            "",
        ],
    )
    def test_blocks_loopback_private_and_metadata_addresses(self, host: str) -> None:
        assert not is_public_host(host)


class TestMaskSecret:
    def test_reveals_only_a_prefix_and_suffix(self) -> None:
        assert mask_secret("sk-proj-1234567890abcd") == "sk-****abcd"

    def test_fully_masks_a_short_secret(self) -> None:
        # Partially revealing a short secret would give away most of it.
        assert mask_secret("short") == "*" * 8

    def test_handles_an_empty_secret(self) -> None:
        assert mask_secret("") == ""
