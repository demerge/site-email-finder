"""End-to-end CLI tests, focused on the resume behavior across runs.

These use `responses` to mock the HTTP layer and call `cli.main()` directly
(rather than shelling out) so they run fast and don't need real network
access.
"""

import csv

import responses

from site_email_finder.cli import main


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@responses.activate
def test_resume_skips_already_found_rows_when_profile_column_is_unmapped(tmp_path):
    """Regression test: when the input CSV has no column mapped to
    'Profile' (e.g. a Google-Places-style export), a completed row's
    Profile in the output file falls back to its Website. The resume
    check must use that SAME fallback, or every row looks 'new' on every
    run and the whole crawl restarts from scratch instead of resuming."""

    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    log_csv = tmp_path / "log.csv"

    # Schema with NO profile/profileUrl column at all -- like the Google
    # Places export that exposed this bug.
    _write_csv(
        input_csv,
        [
            {"title": "Found Biz", "website": "http://foundbiz.test", "category": "Bakery"},
            {"title": "No Email Biz", "website": "http://noemailbiz.test", "category": "Cafe"},
        ],
        fieldnames=["title", "website", "category"],
    )

    responses.add(
        responses.GET,
        "http://foundbiz.test",
        body='<html><a href="mailto:owner@foundbiz.test">Email</a></html>',
        status=200,
        content_type="text/html",
    )
    responses.add(responses.GET, "http://noemailbiz.test", body="<html>nothing</html>", status=200,
                   content_type="text/html")
    for path in ("contact", "contact-us", "contactus", "about", "about-us", "get-in-touch"):
        responses.add(responses.GET, f"http://noemailbiz.test/{path}", status=404)

    map_args = ["--map", "Name=title", "--map", "Email=email", "--map", "Website=website", "--workers", "1"]

    # --- First run: should find one email, log one no_email_found ---
    main(
        [
            str(input_csv),
            "-o", str(output_csv),
            "--log", str(log_csv),
            "--delay", "0",
            "--retries", "0",
            *map_args,
        ]
    )

    first_output = _read_csv(output_csv)
    assert len(first_output) == 1
    assert first_output[0]["Name"] == "Found Biz"
    assert first_output[0]["Email"] == "owner@foundbiz.test"
    # Profile fell back to the website since no Profile column was mapped
    assert first_output[0]["Profile"] == "http://foundbiz.test"

    # --- Second run, same command: the found row must be SKIPPED. We prove
    # this directly by checking no HTTP request was made to foundbiz.test at
    # all in the second run, rather than just inspecting the output file
    # (a weaker check: a connection error on recrawl can also leave the
    # output file looking unchanged, for the wrong reason). ---
    responses.reset()
    responses.add(responses.GET, "http://noemailbiz.test", body="<html>still nothing</html>", status=200,
                   content_type="text/html")
    for path in ("contact", "contact-us", "contactus", "about", "about-us", "get-in-touch"):
        responses.add(responses.GET, f"http://noemailbiz.test/{path}", status=404)
    # Deliberately do NOT register a response for foundbiz.test -- if the
    # resume bug is present and it tries to recrawl, that request will show
    # up in responses.calls below.

    main(
        [
            str(input_csv),
            "-o", str(output_csv),
            "--log", str(log_csv),
            "--delay", "0",
            "--retries", "0",
            *map_args,
        ]
    )

    called_urls = [c.request.url for c in responses.calls]
    assert not any("foundbiz.test" in url for url in called_urls), (
        f"Resume bug: foundbiz.test was re-crawled even though it was already "
        f"in the output file. Calls made: {called_urls}"
    )

    second_output = _read_csv(output_csv)
    # Still exactly one row -- "Found Biz" was recognized as already done
    # and not appended a second time.
    assert len(second_output) == 1
    assert second_output[0]["Name"] == "Found Biz"
