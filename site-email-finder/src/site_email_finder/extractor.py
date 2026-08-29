"""HTML fetching and email-extraction logic, kept separate from the CLI so
it can be imported and reused (e.g. in tests, notebooks, or other scripts).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import (
    DEFAULT_BLOCKLIST_SUBSTRINGS,
    DEFAULT_CONTACT_PATHS,
    DEFAULT_HEADERS,
    DEFAULT_REQUEST_TIMEOUT,
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Network-level failure: could mean the site is genuinely unreachable, OR
# your own internet connection is down. Treated differently from
# "no_email_found" (a page loaded fine, it just had no email on it) so the
# CLI can retry these on a rerun and warn you about outages instead of
# quietly recording hundreds of false negatives.
CONNECTION_ERROR = "connection_error"
NO_EMAIL_FOUND = "no_email_found"
FOUND = "found"


@dataclass
class CrawlResult:
    emails: list[str] = field(default_factory=list)
    checked_urls: list[str] = field(default_factory=list)
    status: str = NO_EMAIL_FOUND  # found | no_email_found | connection_error
    pages_successfully_loaded: int = 0  # any 200 response, whether or not it had an email


def normalize_url(url: str) -> str | None:
    url = (url or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def clean_emails(raw_emails, blocklist=None) -> list[str]:
    """Dedupe, lowercase, and drop obvious junk / tracking-script matches."""
    blocklist = blocklist if blocklist is not None else DEFAULT_BLOCKLIST_SUBSTRINGS
    seen: list[str] = []
    for e in raw_emails:
        e_clean = e.strip().strip(".,;:").lower()
        if any(b in e_clean for b in blocklist):
            continue
        if e_clean not in seen:
            seen.append(e_clean)
    return seen


def fetch(
    url: str,
    timeout: int = DEFAULT_REQUEST_TIMEOUT,
    headers: dict | None = None,
    retries: int = 2,
    retry_backoff: float = 1.5,
) -> tuple[str | None, bool]:
    """Returns (html_or_None, connection_ok).

    connection_ok is False only when every attempt raised a network-level
    exception (timeout, DNS failure, connection refused, etc.) -- i.e. it
    could not even reach the server. A clean 4xx/5xx response, or a 200
    that isn't HTML, counts as connection_ok=True (the internet is fine,
    the page just isn't useful), so it won't trigger outage handling.
    """
    headers = headers or DEFAULT_HEADERS
    last_exception = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                return resp.text, True
            return None, True  # reached the server fine, just nothing usable
        except requests.RequestException as e:
            last_exception = e
            if attempt < retries:
                time.sleep(retry_backoff * (attempt + 1))
    del last_exception
    return None, False


def extract_emails_from_html(html: str) -> list[str]:
    found = EMAIL_RE.findall(html)
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a["href"].lower().startswith("mailto:"):
            found.append(a["href"].split(":", 1)[1].split("?")[0])
    return found


def find_emails_on_site(
    base_url: str,
    contact_paths=None,
    timeout: int = DEFAULT_REQUEST_TIMEOUT,
    headers: dict | None = None,
    blocklist=None,
    retries: int = 2,
) -> CrawlResult:
    """Check the homepage first; if nothing turns up, try likely contact
    pages on the same domain (in order) until one yields an email.

    Distinguishes "loaded fine, no email there" from "couldn't connect at
    all" so callers can tell a real negative apart from a network blip.
    """
    contact_paths = contact_paths if contact_paths is not None else DEFAULT_CONTACT_PATHS
    result = CrawlResult()

    html, connection_ok = fetch(base_url, timeout=timeout, headers=headers, retries=retries)
    result.checked_urls.append(base_url)
    if connection_ok:
        result.pages_successfully_loaded += 1
    if html:
        result.emails = clean_emails(extract_emails_from_html(html), blocklist)

    if not result.emails:
        parsed = urlparse(base_url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        for guess in contact_paths:
            contact_url = urljoin(root + "/", guess)
            result.checked_urls.append(contact_url)
            html, connection_ok = fetch(contact_url, timeout=timeout, headers=headers, retries=retries)
            if connection_ok:
                result.pages_successfully_loaded += 1
            if html:
                result.emails = clean_emails(extract_emails_from_html(html), blocklist)
            if result.emails:
                break

    if result.emails:
        result.status = FOUND
    elif result.pages_successfully_loaded == 0:
        # Every single attempt on every URL failed to even connect --
        # almost certainly your internet, a firewall, or the site being
        # fully down, not "this business has no email".
        result.status = CONNECTION_ERROR
    else:
        result.status = NO_EMAIL_FOUND

    return result

