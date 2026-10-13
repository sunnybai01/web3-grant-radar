"""L1 URL deduplication — canonical URL matching + PostgreSQL unique constraint."""
import datetime
import hashlib
import logging
import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from sqlalchemy.orm import Session

from config.settings import settings
from src.db.models import RawSignal
from src.db.queries import claim_raw_signal_retry, find_raw_signal, insert_raw_signal
from src.fetchers.base import FetchedItem

logger = logging.getLogger(__name__)

# Marketing/tracking params to strip. Matched case-insensitively.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "utm_id", "utm_name", "utm_reader", "utm_referrer",
    "ref", "referrer", "referer", "source", "src", "ref_src", "ref_url",
    "fbclid", "gclid", "gclsrc", "dclid", "twclid", "msclkid", "yclid",
    "_ga", "_gl", "_hsenc", "_hsmi", "hsctatracking",
    "mc_cid", "mc_eid", "mkt_tok", "igshid", "si", "trk", "trkCampaign",
    "spm", "scm", "share_id", "shareId", "from", "via", "cmpid", "campaign",
}

# Hosts that serve the same page under both names. Only host-level rewrites that
# are known to be safe belong here.
_HOST_ALIASES = {
    "twitter.com": "x.com",
    "www.twitter.com": "x.com",
    "mobile.twitter.com": "x.com",
}

_DEFAULT_PORTS = {"http": "80", "https": "443"}

# Bare hostnames in scam/short-link lists would be premature; we only drop the
# obvious non-web schemes.
_ALLOWED_SCHEMES = {"http", "https"}


def _normalized_host(parsed) -> str:
    host = (parsed.hostname or "").lower()
    if host.startswith("www.") and len(host) > 4:
        host = host[4:]
    host = _HOST_ALIASES.get(host, host)
    port = parsed.port
    if port is not None and str(port) != _DEFAULT_PORTS.get(parsed.scheme.lower(), ""):
        host = f"{host}:{port}"
    return host


def _normalized_query(query: str) -> str:
    if not query:
        return ""
    kept = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.lower() not in {p.lower() for p in TRACKING_PARAMS}
    ]
    kept.sort()
    return urlencode(kept, doseq=True)


def normalize_url(url: str, base_url: str = "") -> str:
    """Canonicalize a URL for dedup comparisons.

    Handles the variants that produced duplicate raw_signals in production:
    scheme (http/https), leading ``www.``, default ports, tracking params,
    parameter order, trailing slashes, fragments, relative paths and the
    twitter.com/x.com pair. Returns "" for anything that is not a web URL.
    """
    if not url:
        return ""

    candidate = str(url).strip()
    if base_url and not urlparse(candidate).netloc:
        candidate = urljoin(base_url, candidate)

    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()

    if scheme not in _ALLOWED_SCHEMES:
        if not parsed.netloc:
            # "mailto:", "javascript:", "data:" and similar are not dedup keys.
            return ""
        scheme = "https"

    # Force https: the same page served over both schemes produced two signals
    # (with identical content hashes) in production.
    scheme = "https"

    host = _normalized_host(parsed)
    if not host:
        return ""

    path = parsed.path or "/"
    if path != "/":
        # Collapse duplicate slashes and drop the trailing one.
        path = re.sub(r"/{2,}", "/", path).rstrip("/") or "/"

    query = _normalized_query(parsed.query)

    # Fragments are dropped: hash-routed pages ("/#/hackathon/123") otherwise
    # collapse onto the bare host, which is worse than losing the anchor.
    return urlunparse((scheme, host, path, "", query, ""))


_WHITESPACE_RE = re.compile(r"[ \t\u00a0\u202f]+")
_BLANK_LINES_RE = re.compile(r"\n{2,}")
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")
_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?\b"
)


def normalize_content(content: str) -> str:
    """Collapse the presentation-only noise that defeats content hashing.

    Listing pages embed relative timestamps ("2 hours ago", "2026-10-10 01:04")
    and copy-deck whitespace that change on every fetch while the opportunity
    text stays identical. Two signals whose normalized forms match are the same
    content as far as dedup is concerned.
    """
    if not content:
        return ""

    text = _ZERO_WIDTH_RE.sub("", str(content))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TIMESTAMP_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES_RE.sub("\n", text)
    return text.strip()


def generate_content_hash(content: str) -> str:
    """SHA-256 hash of content for dedup indexing."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def process_item_l1(db: Session, item: FetchedItem) -> Optional[int]:
    """L1 dedup: canonical URL + content hash. Returns raw_signal ID if new, None if dup.

    Keyed on the pair rather than the URL alone: listing and index pages keep a
    stable URL while their content rolls over, so a url-only key would silently
    block every opportunity published after the first fetch. Near-identical
    reposts are still caught downstream by L2 semantic dedup.

    The hash is taken over the *normalized* content so a re-fetch that only moved
    a timestamp or changed whitespace is recognised as the same signal instead of
    being re-classified.

    Writes to raw_signals table on success. The PostgreSQL UNIQUE constraint on
    (canonical_url, content_hash) provides the final safety net.

    A signal seen before is only a duplicate once it was processed. One whose
    processing failed, or that a crashed run left pending, is handed out again
    (same id) until RAW_SIGNAL_MAX_ATTEMPTS is reached.
    """
    canonical = normalize_url(item.canonical_url or item.raw_url, base_url=item.raw_url)
    content_hash = generate_content_hash(normalize_content(item.raw_content))

    existing = find_raw_signal(db, canonical, content_hash) if canonical else None
    if existing is not None:
        if not _retryable(existing):
            return None
        claim_raw_signal_retry(db, existing)
        logger.info(
            "Retrying raw signal #%s from %s (attempt %d): %s",
            existing.id, item.source_name, existing.attempts, existing.last_error or existing.status,
        )
        return existing.id

    signal = insert_raw_signal(
        db,
        source_type=item.source_type,
        source_name=item.source_name,
        raw_content=item.raw_content,
        raw_url=item.raw_url,
        canonical_url=canonical,
        content_hash=content_hash,
    )

    return signal.id if signal else None


def _retryable(signal: RawSignal) -> bool:
    if (signal.attempts or 1) >= settings.RAW_SIGNAL_MAX_ATTEMPTS:
        return False
    if signal.status == "failed":
        return True
    if signal.status == "pending" and signal.fetched_at is not None:
        fetched_at = signal.fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=datetime.timezone.utc)
        abandoned_after = datetime.timedelta(minutes=settings.RAW_SIGNAL_PENDING_TIMEOUT_MINUTES)
        return datetime.datetime.now(datetime.timezone.utc) - fetched_at > abandoned_after
    return False
