"""Command-line interface.

Run `site-email-finder --help` (after installing) or
`python -m site_email_finder --help` for the full flag list.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from .config import (
    DEFAULT_AUTO_RETRY_PASSES,
    DEFAULT_CONTACT_PATHS,
    DEFAULT_DELAY_SECONDS,
    DEFAULT_FIELD_MAP,
    DEFAULT_OUTPUT_COLUMNS,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_SAVE_EVERY,
    DEFAULT_WORKERS,
)
from .extractor import CONNECTION_ERROR, FOUND, find_emails_on_site, normalize_url
from .io_utils import build_bio, load_already_done, load_rows, open_output_writers, row_get


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


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
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help="Delay after each site check, in seconds (applied per worker, not globally)",
    )
    p.add_argument("--save-every", type=int, default=DEFAULT_SAVE_EVERY, help="Flush output to disk every N rows")
    p.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Number of sites to check in parallel (default: {DEFAULT_WORKERS}). Use 1 for the old sequential "
        "behavior.",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retries per page on connection failure before giving up on that page (default: 2)",
    )
    p.add_argument(
        "--auto-retry-passes",
        type=int,
        default=DEFAULT_AUTO_RETRY_PASSES,
        help=(
            f"After the main pass, automatically re-check any rows that ended in "
            f"'connection_error' this run, up to this many extra passes (default: "
            f"{DEFAULT_AUTO_RETRY_PASSES}). Set to 0 to disable and only retry them by "
            "rerunning the command later."
        ),
    )
    p.add_argument(
        "--outage-threshold",
        type=int,
        default=15,
        help=(
            "Pause and wait for you to confirm before continuing after this many "
            "consecutive connection_error results in a row (default: 15). "
            "Prevents silently burning through your whole list during an internet outage. "
            "Set to 0 to disable."
        ),
    )
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
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the periodic progress line and final summary, not every row",
    )
    return p


def _classify_rows(rows, field_map, already_done):
    """Split input rows into three buckets up front:
    - immediate: no crawl needed (already has email, or no website)
    - to_crawl: needs a live site check, with all the row context it'll need later
    - skipped: already resolved in a previous run
    Each item keeps its original 1-based row index for progress printing.
    """
    immediate = []
    to_crawl = []
    skipped = 0

    for i, row in enumerate(rows, 1):
        name = row_get(row, field_map, "Name")
        profile = row_get(row, field_map, "Profile")
        website = normalize_url(row_get(row, field_map, "Website"))
        resume_key = (name, profile or website or "")

        if resume_key in already_done:
            skipped += 1
            continue

        existing_email = row_get(row, field_map, "Email")
        bio = build_bio(row, field_map)
        item = {
            "index": i,
            "name": name,
            "profile": profile,
            "website": website,
            "bio": bio,
            "existing_email": existing_email,
        }

        if existing_email or not website:
            immediate.append(item)
        else:
            to_crawl.append(item)

    return immediate, to_crawl, skipped


def _write_result(item, email_to_use, status, out_writer, log_writer, output_columns):
    if email_to_use:
        out_row = {col: "" for col in output_columns}
        out_row.update(
            {
                "Name": item["name"],
                "Email": email_to_use,
                "Bio": item["bio"],
                "Company": item["name"],
                "Profile": item["profile"] or item["website"] or "",
            }
        )
        out_writer.writerow({k: out_row.get(k, "") for k in output_columns})

    log_writer.writerow(
        {
            "Name": item["name"],
            "Website": item["website"] or "",
            "Status": status,
            "EmailsFound": status.split("found:", 1)[1] if status.startswith("found:") else "",
        }
    )


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
    found_count = 0
    consecutive_connection_errors = 0
    start_time = time.time()
    workers = max(1, args.workers)
    pending: list = []

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    def crawl(item):
        result = find_emails_on_site(
            item["website"], contact_paths=contact_paths, timeout=args.timeout, retries=args.retries
        )
        time.sleep(args.delay)
        return item, result

    immediate, skipped = [], 0
    try:
        # --- Instant pass: rows needing no network call at all ---
        immediate, to_crawl, skipped = _classify_rows(rows, field_map, already_done)
        log(
            f"Resume check: {skipped} rows already done and skipped, {len(immediate)} need no "
            f"crawl, {len(to_crawl)} need a live site check."
        )

        for item in immediate:
            if item["existing_email"]:
                status = "had_email_already"
                log(f"[{item['index']}/{total}] {item['name'] or '(no name)'} -> already had an email")
                _write_result(item, item["existing_email"], status, out_writer, log_writer, output_columns)
            else:
                status = "no_website"
                log(f"[{item['index']}/{total}] {item['name'] or '(no name)'} -> no website, skipping")
                _write_result(item, "", status, out_writer, log_writer, output_columns)
        out_f.flush()
        log_f.flush()

        # --- Crawl pass(es): main pass, then automatic retries of connection_error rows ---
        pending = to_crawl
        pass_num = 0
        max_passes = 1 + max(0, args.auto_retry_passes)

        while pending and pass_num < max_passes:
            pass_num += 1
            is_last_pass = pass_num >= max_passes
            if pass_num > 1:
                log(
                    f"\n--- Retry pass {pass_num - 1}/{args.auto_retry_passes}: "
                    f"re-checking {len(pending)} sites that had connection errors ---"
                )

            next_pending = []
            processed_this_pass = 0
            pass_start = time.time()

            with ThreadPoolExecutor(max_workers=workers) as executor:
                for item, result in executor.map(crawl, pending):
                    processed_this_pass += 1

                    if result.status == FOUND:
                        email_to_use = result.emails[0]
                        status = "found:" + ";".join(result.emails)
                        found_count += 1
                        consecutive_connection_errors = 0
                        log(f"[{item['index']}/{total}] {item['name'] or '(no name)'} -> FOUND: {email_to_use}")
                        _write_result(item, email_to_use, status, out_writer, log_writer, output_columns)
                        out_f.flush()  # never lose a real find to a hard crash
                    elif result.status == CONNECTION_ERROR:
                        consecutive_connection_errors += 1
                        retry_note = "(will retry on next run)" if is_last_pass else "(will retry)"
                        log(f"[{item['index']}/{total}] {item['name'] or '(no name)'} -> could not connect {retry_note}")
                        if is_last_pass:
                            _write_result(item, "", CONNECTION_ERROR, out_writer, log_writer, output_columns)
                        else:
                            next_pending.append(item)
                    else:
                        consecutive_connection_errors = 0
                        log(f"[{item['index']}/{total}] {item['name'] or '(no name)'} -> no email found")
                        _write_result(item, "", "no_email_found", out_writer, log_writer, output_columns)

                    if processed_this_pass % args.save_every == 0:
                        out_f.flush()
                        log_f.flush()
                        elapsed = time.time() - pass_start
                        remaining = len(pending) - processed_this_pass
                        eta = (elapsed / processed_this_pass) * remaining if processed_this_pass else 0
                        print(
                            f"--- progress | pass {pass_num} | {processed_this_pass}/{len(pending)} checked | "
                            f"found so far: {found_count} | elapsed {format_duration(elapsed)} | "
                            f"ETA (this pass) {format_duration(eta)} ---",
                            file=sys.stderr,
                        )

                    if args.outage_threshold and consecutive_connection_errors >= args.outage_threshold:
                        out_f.flush()
                        log_f.flush()
                        print(
                            f"\n!!! {consecutive_connection_errors} sites in a row failed to connect at all. "
                            "This usually means your internet is down, not that these businesses lack "
                            "emails.\nProgress so far is saved. Check your connection, then press Enter "
                            "to keep going (or Ctrl+C to stop here -- nothing already found is lost).",
                            file=sys.stderr,
                        )
                        input()
                        consecutive_connection_errors = 0

            pending = next_pending
    finally:
        out_f.close()
        log_f.close()

    total_elapsed = time.time() - start_time
    print("\nDone.", file=sys.stderr)
    print(f"Rows skipped (already done): {skipped}", file=sys.stderr)
    print(f"Rows needing no crawl (had email / no website): {len(immediate)}", file=sys.stderr)
    print(f"New emails found this run: {found_count}", file=sys.stderr)
    if pending:
        print(
            f"Still unresolved after {args.auto_retry_passes} auto-retry pass(es): {len(pending)} "
            "(logged as connection_error -- rerun the command later to retry them)",
            file=sys.stderr,
        )
    print(f"Total time: {format_duration(total_elapsed)}", file=sys.stderr)
    print(f"Full results: {args.output}", file=sys.stderr)
    print(f"Per-site log: {args.log}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
