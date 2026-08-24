"""Command-line interface.

Run `site-email-finder --help` (after installing) or
`python -m site_email_finder --help` for the full flag list.
"""

from __future__ import annotations

import argparse
import sys
import time

from .config import (
    DEFAULT_CONTACT_PATHS,
    DEFAULT_DELAY_SECONDS,
    DEFAULT_FIELD_MAP,
    DEFAULT_OUTPUT_COLUMNS,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_SAVE_EVERY,
)
from .extractor import find_emails_on_site, normalize_url
from .io_utils import build_bio, load_already_done, load_rows, open_output_writers, row_get


def parse_field_map(pairs: list[str] | None, base: dict) -> dict:
    """Parse --map OutputField=csv_column pairs on top of a base mapping."""
    field_map = dict(base)
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--map value must be OutputField=csv_column, got: {pair!r}")
        key, val = pair.split("=", 1)
        field_map[key.strip()] = val.strip()
    return field_map


def load_config_file(path: str | None) -> dict:
    if not path:
        return {}
    try:
        import yaml
    except ImportError:
        raise SystemExit("--config requires PyYAML. Install it with: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="site-email-finder",
        description="Crawl business websites listed in a CSV and extract contact email addresses.",
    )
    p.add_argument("input_csv", help="Path to the input CSV (e.g. a scraper export)")
    p.add_argument("-o", "--output", default="contacts_with_found_emails.csv", help="Output CSV path")
    p.add_argument("--log", default="crawl_log.csv", help="Per-site crawl log CSV path")
    p.add_argument("--config", help="Optional YAML file overriding field mapping / options")
    p.add_argument(
        "--map",
        action="append",
        metavar="OutputField=csv_column",
        help="Override a single field mapping, e.g. --map Email=contact_email. Repeatable.",
    )
    p.add_argument(
        "--contact-paths",
        nargs="*",
        default=None,
        help=f"Contact-page paths to try if the homepage has no email (default: {DEFAULT_CONTACT_PATHS})",
    )
    p.add_argument("--timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT, help="Per-request timeout in seconds")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Delay between sites, in seconds")
    p.add_argument("--save-every", type=int, default=DEFAULT_SAVE_EVERY, help="Flush output to disk every N rows")
    p.add_argument("--limit", type=int, default=None, help="Only process the first N rows (useful for testing)")
    p.add_argument(
        "--skip-existing-email",
        dest="skip_existing_email",
        action="store_true",
        default=True,
        help="(default) Don't re-crawl rows that already have an email in the input CSV",
    )
    p.add_argument(
        "--recrawl-existing-email",
        dest="skip_existing_email",
        action="store_false",
        help="Crawl every row's website even if the input CSV already has an email",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    cfg = load_config_file(args.config)
    field_map = parse_field_map(cfg.get("map_list"), DEFAULT_FIELD_MAP)
    field_map = parse_field_map(args.map, field_map)
    contact_paths = args.contact_paths or cfg.get("contact_paths") or DEFAULT_CONTACT_PATHS
    output_columns = cfg.get("output_columns") or DEFAULT_OUTPUT_COLUMNS

    rows = load_rows(args.input_csv)
    if args.limit:
        rows = rows[: args.limit]

    already_done = load_already_done(args.output)
    out_f, log_f, out_writer, log_writer = open_output_writers(args.output, args.log, output_columns)

    total = len(rows)
    processed = 0
    found_count = 0

    try:
        for i, row in enumerate(rows, 1):
            name = row_get(row, field_map, "Name")
            profile = row_get(row, field_map, "Profile")

            if (name, profile) in already_done:
                continue

            existing_email = row_get(row, field_map, "Email")
            website = normalize_url(row_get(row, field_map, "Website"))
            bio = build_bio(row, field_map)

            email_to_use = existing_email
            status = "had_email_already" if existing_email else ""

            if not email_to_use and website and args.skip_existing_email is not None:
                print(f"[{i}/{total}] Checking {name or '(no name)'} -> {website}", file=sys.stderr)
                result = find_emails_on_site(
                    website, contact_paths=contact_paths, timeout=args.timeout
                )
                if result.emails:
                    email_to_use = result.emails[0]
                    status = "found:" + ";".join(result.emails)
                    found_count += 1
                    print(f"    -> FOUND: {email_to_use}", file=sys.stderr)
                else:
                    status = "no_email_found"
                time.sleep(args.delay)
            elif not website:
                status = "no_website"

            if email_to_use:
                out_row = {col: "" for col in output_columns}
                out_row.update(
                    {
                        "Name": name,
                        "Email": email_to_use,
                        "Bio": bio,
                        "Company": name,
                        "Profile": profile or website or "",
                    }
                )
                out_writer.writerow({k: out_row.get(k, "") for k in output_columns})

            log_writer.writerow(
                {
                    "Name": name,
                    "Website": website or "",
                    "Status": status,
                    "EmailsFound": status.split("found:", 1)[1] if status.startswith("found:") else "",
                }
            )

            processed += 1
            if processed % args.save_every == 0:
                out_f.flush()
                log_f.flush()
                print(f"--- progress saved ({processed} rows processed this run) ---", file=sys.stderr)
    finally:
        out_f.close()
        log_f.close()

    print("\nDone.", file=sys.stderr)
    print(f"New emails found this run: {found_count}", file=sys.stderr)
    print(f"Full results: {args.output}", file=sys.stderr)
    print(f"Per-site log: {args.log}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
