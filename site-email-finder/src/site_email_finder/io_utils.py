"""CSV reading/writing with a configurable field map, so this tool isn't
hard-wired to one particular scraper's export schema."""

from __future__ import annotations

import csv
from pathlib import Path

from .config import DEFAULT_FIELD_MAP, DEFAULT_OUTPUT_COLUMNS


def load_rows(input_csv: str) -> list[dict]:
    with open(input_csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def build_bio(row: dict, field_map: dict) -> str:
    """Prefer a description column if present and non-empty; otherwise
    fall back to '<category> in <city>, <state>'."""
    desc_col = field_map.get("Bio")
    desc = (row.get(desc_col) or "").strip() if desc_col else ""
    if desc:
        return desc

    category = (row.get(field_map.get("Category", "")) or "").strip()
    city = (row.get(field_map.get("City", "")) or "").strip()
    state = (row.get(field_map.get("State", "")) or "").strip()
    loc = ", ".join(p for p in [city, state] if p)

    if category and loc:
        return f"{category} in {loc}"
    return category or loc


def row_get(row: dict, field_map: dict, output_field: str) -> str:
    col = field_map.get(output_field)
    if not col:
        return ""
    return (row.get(col) or "").strip()


def load_already_done(output_csv: str) -> set[tuple[str, str]]:
    """Resume support: identify rows already written in a previous run."""
    done = set()
    p = Path(output_csv)
    if not p.exists():
        return done
    with open(p, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            done.add((row.get("Name", ""), row.get("Profile", "")))
    return done


def open_output_writers(output_csv: str, log_csv: str, output_columns=None):
    output_columns = output_columns or DEFAULT_OUTPUT_COLUMNS
    out_exists = Path(output_csv).exists()
    log_exists = Path(log_csv).exists()

    # Intentionally kept open for the life of the crawl (not a `with` block):
    # the caller writes to these incrementally, row by row, and closes them
    # itself once the run finishes (see cli.py's try/finally).
    out_f = open(output_csv, "a", newline="", encoding="utf-8")  # noqa: SIM115
    log_f = open(log_csv, "a", newline="", encoding="utf-8")  # noqa: SIM115

    out_writer = csv.DictWriter(out_f, fieldnames=output_columns)
    log_writer = csv.DictWriter(log_f, fieldnames=["Name", "Website", "Status", "EmailsFound"])

    if not out_exists:
        out_writer.writeheader()
    if not log_exists:
        log_writer.writeheader()

    return out_f, log_f, out_writer, log_writer


__all__ = [
    "DEFAULT_FIELD_MAP",
    "build_bio",
    "load_already_done",
    "load_rows",
    "open_output_writers",
    "row_get",
]
