"""Resolve URL-shortener links to the page they lead to."""
import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Shorteners seen in apply links copied from tweets and newsletters.
SHORTENER_HOSTS = {
    "t.co", "bit.ly", "ow.ly", "buff.ly", "lnkd.in", "tinyurl.com", "goo.gl",
    "ethglob.al", "dub.sh", "rebrand.ly", "shorturl.at",
}


def expand_short_link(url: Optional[str], client: Optional[httpx.Client] = None, timeout: float = 5.0) -> Optional[str]:
    """The destination of a shortener link; any other link, or a failure, returns it unchanged."""
    if not url or (urlparse(url).hostname or "").lower() not in SHORTENER_HOSTS:
        return url
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=timeout,
                                    headers={"User-Agent": "Web3GrantRadar/1.0"})
    try:
        response = client.head(url, follow_redirects=True, timeout=timeout)
        return str(response.url) or url
    except Exception as e:
        logger.debug("Could not expand %s: %s", url, e)
        return url
    finally:
        if owns_client:
            client.close()
