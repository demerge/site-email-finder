"""HTML fetching and email-extraction logic, kept separate from the CLI so
it can be imported and reused (e.g. in tests, notebooks, or other scripts).
"""

from __future__ import annotations

import re
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


@dataclass
class CrawlResult:
    emails: list[str] = field(default_factory=list)
    checked_urls: list[str] = field(default_factory=list)
    status: str = "no_email_found"  # no_website | no_email_found | found | error


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


def fetch(url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT, headers: dict | None = None) -> str | None:
    headers = headers or DEFAULT_HEADERS
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            return resp.text
    except requests.RequestException:
        return None
    return None


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
) -> CrawlResult:
    """Check the homepage first; if nothing turns up, try likely contact
    pages on the same domain (in order) until one yields an email."""
    contact_paths = contact_paths if contact_paths is not None else DEFAULT_CONTACT_PATHS
    result = CrawlResult()

    html = fetch(base_url, timeout=timeout, headers=headers)
    result.checked_urls.append(base_url)
    if html:
        result.emails = clean_emails(extract_emails_from_html(html), blocklist)

    if not result.emails:
        parsed = urlparse(base_url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        for guess in contact_paths:
            contact_url = urljoin(root + "/", guess)
            result.checked_urls.append(contact_url)
            html = fetch(contact_url, timeout=timeout, headers=headers)
            if html:
                result.emails = clean_emails(extract_emails_from_html(html), blocklist)
            if result.emails:
                break

    result.status = "found" if result.emails else "no_email_found"
    return result
