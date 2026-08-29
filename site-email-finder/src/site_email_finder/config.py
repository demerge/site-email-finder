"""Default configuration values.

Everything here can be overridden either via CLI flags (see cli.py --help)
or a YAML config file passed with --config. CLI flags always win over the
YAML file, and the YAML file always wins over these defaults.
"""

from __future__ import annotations

DEFAULT_CONTACT_PATHS = [
    "contact",
    "contact-us",
    "contactus",
    "about",
    "about-us",
    "get-in-touch",
]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
        "site-email-finder/0.1"
    )
}

# Substrings that mark a regex match as junk rather than a real contact email
DEFAULT_BLOCKLIST_SUBSTRINGS = [
    "example.com",
    "yourdomain",
    "sentry.io",
    "wixpress.com",
    "godaddy.com",
    "schema.org",
    "w3.org",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".css",
    ".js",
    ".webp",
    # Generic placeholder addresses seen embedded in page templates/widgets
    "user@domain.com",
    "name@domain.com",
    "you@domain.com",
    "email@domain.com",
    "your@email.com",
    "@domain.com",
    "@yourcompany.com",
    "test@test.com",
]

# Default mapping from *output* field name -> *input* CSV column name.
# Override with --map or a config file to point this at any CSV schema.
DEFAULT_FIELD_MAP = {
    "Name": "name",
    "Email": "email",
    "Bio": "description",
    "Company": "name",
    "Profile": "profileUrl",
    "Website": "website",
    "Category": "primaryCategory",
    "City": "address/city",
    "State": "address/state",
}

# Order of columns in the output CSV
DEFAULT_OUTPUT_COLUMNS = ["Name", "Email", "Bio", "Company", "Profile"]

DEFAULT_REQUEST_TIMEOUT = 10
DEFAULT_DELAY_SECONDS = 1.0
DEFAULT_SAVE_EVERY = 25
