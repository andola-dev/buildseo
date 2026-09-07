"""Domain and URL canonicalisation.

Publisher de-duplication is only as good as the canonical form used as its
identity. All of ::

    example.com
    EXAMPLE.com.
    www.example.com
    https://example.com
    https://www.example.com/
    http://user:pw@www.example.com:443/listings?utm_source=x#frag

must resolve to the single canonical domain ``example.com``, which is what the
``UNIQUE (tenant_id, normalized_domain)`` constraint on ``publishers`` relies
on. Internationalised names are folded to punycode so ``bücher.de`` and
``xn--bcher-kva.de`` also collide.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

import idna

from app.core.exceptions import ValidationError

MAX_DOMAIN_LENGTH = 253
MAX_LABEL_LENGTH = 63

_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_DEFAULT_PORTS = {"http": 80, "https": 443}

#: Public-suffix-like second-level registries where the registrable domain has
#: three labels (``example.co.uk``). Deliberately a short, explicit list rather
#: than a bundled PSL snapshot: the canonical form below never *strips* these,
#: it only needs them to decide whether a host is a bare registrable domain.
_MULTI_LABEL_SUFFIXES = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "me.uk",
        "net.uk",
        "sch.uk",
        "com.au",
        "net.au",
        "org.au",
        "edu.au",
        "gov.au",
        "id.au",
        "co.nz",
        "net.nz",
        "org.nz",
        "govt.nz",
        "ac.nz",
        "co.za",
        "org.za",
        "net.za",
        "web.za",
        "com.br",
        "net.br",
        "org.br",
        "gov.br",
        "co.in",
        "net.in",
        "org.in",
        "gen.in",
        "firm.in",
        "ind.in",
        "com.sg",
        "com.my",
        "com.hk",
        "com.tw",
        "com.cn",
        "net.cn",
        "org.cn",
        "co.jp",
        "or.jp",
        "ne.jp",
        "ac.jp",
        "go.jp",
        "com.mx",
        "com.ar",
        "com.co",
        "com.tr",
        "com.ua",
        "com.pl",
        "co.il",
        "co.kr",
        "or.kr",
        "co.th",
        "in.th",
        "com.ph",
        "com.vn",
    }
)


def _strip_scheme_prefix(value: str) -> str:
    """Return the authority+path portion of ``value``, whatever form it arrived in."""
    candidate = value.strip()
    if not candidate:
        raise ValidationError("Domain must not be empty", code="INVALID_DOMAIN")
    # Give urlsplit an authority to parse even for a bare "example.com/path".
    if "//" not in candidate:
        candidate = f"//{candidate}"
    elif not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", candidate):
        candidate = candidate[candidate.index("//") :]
    return candidate


def _to_ascii_host(host: str) -> str:
    """Fold a host to lowercase ASCII, converting IDN labels to punycode."""
    host = host.strip().strip(".").lower()
    if not host:
        raise ValidationError("Domain must not be empty", code="INVALID_DOMAIN")
    if host.isascii():
        return host
    try:
        return idna.encode(host, uts46=True, transitional=False).decode("ascii")
    except idna.IDNAError as exc:
        raise ValidationError(
            "Domain is not a valid internationalised domain name",
            code="INVALID_DOMAIN",
            details={"domain": host},
        ) from exc


def _validate_host(host: str) -> None:
    if len(host) > MAX_DOMAIN_LENGTH:
        raise ValidationError(
            f"Domain exceeds {MAX_DOMAIN_LENGTH} characters", code="INVALID_DOMAIN"
        )
    labels = host.split(".")
    if len(labels) < 2:
        raise ValidationError(
            "Domain must include a top-level domain",
            code="INVALID_DOMAIN",
            details={"domain": host},
        )
    for label in labels:
        if not label or len(label) > MAX_LABEL_LENGTH or not _LABEL_RE.match(label):
            raise ValidationError(
                "Domain contains an invalid label",
                code="INVALID_DOMAIN",
                details={"domain": host, "label": label},
            )
    if labels[-1].isdigit():
        raise ValidationError(
            "Domain top-level label must not be numeric",
            code="INVALID_DOMAIN",
            details={"domain": host},
        )


def normalize_domain(value: str, *, strip_www: bool = True) -> str:
    """Return the canonical, comparable domain for a domain or URL string.

    Raises :class:`~app.core.exceptions.ValidationError` for anything that is
    not a syntactically valid public domain name — including bare IP addresses,
    which are never legitimate listing-directory identities.
    """
    parts = urlsplit(_strip_scheme_prefix(value))
    host = parts.hostname or ""  # hostname drops userinfo and port, already lowered
    if not host:
        raise ValidationError(
            "Could not extract a domain", code="INVALID_DOMAIN", details={"value": value}
        )

    if host.startswith("[") or _is_ip_literal(host):
        raise ValidationError(
            "IP addresses are not accepted as publisher domains",
            code="INVALID_DOMAIN",
            details={"value": value},
        )

    host = _to_ascii_host(host)
    _validate_host(host)

    if strip_www:
        while host.startswith("www."):
            candidate = host[4:]
            if len(candidate.split(".")) < 2:
                break
            host = candidate
    return host


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def normalize_url(value: str, *, default_scheme: str = "https") -> str:
    """Return a canonical absolute URL: lowered scheme/host, no default port,
    no userinfo, no fragment, and no redundant trailing slash.

    The path is preserved verbatim (case included) because directory
    submission paths are frequently case-sensitive.
    """
    candidate = value.strip()
    if not candidate:
        raise ValidationError("URL must not be empty", code="INVALID_URL")

    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", candidate):
        candidate = f"{default_scheme}://{candidate.lstrip('/')}"

    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValidationError(
            "URL scheme must be http or https", code="INVALID_URL", details={"scheme": scheme}
        )

    host = parts.hostname
    if not host:
        raise ValidationError("URL must include a host", code="INVALID_URL")
    if not _is_ip_literal(host):
        host = _to_ascii_host(host)
        _validate_host(host)

    netloc = host
    if parts.port is not None and parts.port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"

    path = parts.path or ""
    if path == "/":
        path = ""

    return urlunsplit((scheme, netloc, path, parts.query, ""))


def extract_domain(value: str) -> str:
    """Canonical domain for a URL, tolerating a bare domain input."""
    return normalize_domain(value)


def registrable_domain(value: str) -> str:
    """Best-effort registrable ("apex") domain, e.g. ``blog.example.co.uk`` →
    ``example.co.uk``.

    Used for grouping and duplicate hints, never for the uniqueness constraint,
    because it relies on the bounded suffix list above rather than a full PSL.
    """
    host = normalize_domain(value)
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in _MULTI_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def same_site(left: str, right: str) -> bool:
    """True when two domains/URLs denote the same canonical site."""
    try:
        return normalize_domain(left) == normalize_domain(right)
    except ValidationError:
        return False


def is_public_host(host: str) -> bool:
    """False for loopback, private, link-local and reserved destinations.

    The crawler and every BYOK provider client route through this so a
    tenant-supplied URL cannot be used to probe internal infrastructure.
    """
    cleaned = host.strip().strip("[]").lower()
    if not cleaned:
        return False
    try:
        address = ipaddress.ip_address(cleaned)
    except ValueError:
        if cleaned in ("localhost", "localhost.localdomain") or cleaned.endswith(
            (".localhost", ".local", ".internal", ".localdomain")
        ):
            return False
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def mask_secret(secret: str, *, visible_prefix: int = 3, visible_suffix: int = 4) -> str:
    """Build the display-only hint stored alongside an encrypted credential.

    Short secrets are fully masked rather than partially revealed.
    """
    if not secret:
        return ""
    if len(secret) <= visible_prefix + visible_suffix + 2:
        return "*" * 8
    return f"{secret[:visible_prefix]}{'*' * 4}{secret[-visible_suffix:]}"
