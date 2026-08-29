import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from site_email_finder.extractor import (
    CONNECTION_ERROR,
    FOUND,
    NO_EMAIL_FOUND,
    clean_emails,
    extract_emails_from_html,
    find_emails_on_site,
    normalize_url,
)


def test_normalize_url_adds_scheme():
    assert normalize_url("example.com") == "http://example.com"
    assert normalize_url("https://example.com") == "https://example.com"
    assert normalize_url("") is None
    assert normalize_url("   ") is None


def test_extract_emails_from_html_finds_plain_and_mailto():
    html = """
    <html><body>
      <p>Contact us at hello@example.com</p>
      <a href="mailto:sales@example.com?subject=Hi">Email sales</a>
    </body></html>
    """
    found = extract_emails_from_html(html)
    assert "hello@example.com" in found
    assert "sales@example.com" in found


def test_clean_emails_dedupes_and_filters_junk():
    raw = [
        "Hello@biz.test",
        "hello@biz.test.",
        "tracking@sentry.io",
        "logo@biz.test.png",
    ]
    cleaned = clean_emails(raw)
    assert cleaned == ["hello@biz.test"]


def test_clean_emails_filters_generic_placeholders():
    raw = [
        "user@domain.com",
        "name@domain.com",
        "you@domain.com",
        "sales@domain.com",  # any @domain.com is a placeholder, not a real business
        "test@test.com",
        "real@biz.test",
    ]
    cleaned = clean_emails(raw)
    assert cleaned == ["real@biz.test"]


def test_clean_emails_filters_empty_mailto():
    """<a href="mailto:"> with no address produces an empty string in the
    raw extraction -- must never be reported as a 'found' email."""
    raw = ["", "   ", "real@biz.test"]
    cleaned = clean_emails(raw)
    assert cleaned == ["real@biz.test"]


@responses.activate
def test_find_emails_on_site_falls_back_to_contact_page():
    responses.add(responses.GET, "http://biz.test", body="<html>no email here</html>", status=200,
                   content_type="text/html")
    responses.add(
        responses.GET,
        "http://biz.test/contact",
        body='<html><a href="mailto:owner@biz.test">Email us</a></html>',
        status=200,
        content_type="text/html",
    )

    result = find_emails_on_site("http://biz.test", contact_paths=["contact", "about"])

    assert result.status == FOUND
    assert result.emails == ["owner@biz.test"]
    assert "http://biz.test/contact" in result.checked_urls


@responses.activate
def test_find_emails_on_site_no_email_found():
    responses.add(responses.GET, "http://noemail.test", body="<html>nothing</html>", status=200,
                   content_type="text/html")
    responses.add(responses.GET, "http://noemail.test/contact", status=404)

    result = find_emails_on_site("http://noemail.test", contact_paths=["contact"])

    assert result.status == NO_EMAIL_FOUND
    assert result.emails == []
    # The site itself DID respond (404 is a real response), so this is a
    # confirmed negative, not a connection problem.
    assert result.pages_successfully_loaded >= 1


@responses.activate
def test_find_emails_on_site_reports_connection_error_not_no_email():
    """If every request fails at the network level (e.g. your internet is
    down), that must be distinguishable from a genuine 'no email here' --
    otherwise an outage silently poisons results as false negatives."""
    responses.add(responses.GET, "http://unreachable.test", body=RequestsConnectionError("simulated outage"))
    responses.add(
        responses.GET, "http://unreachable.test/contact", body=RequestsConnectionError("simulated outage")
    )

    result = find_emails_on_site(
        "http://unreachable.test", contact_paths=["contact"], retries=0
    )

    assert result.status == CONNECTION_ERROR
    assert result.emails == []
    assert result.pages_successfully_loaded == 0


@responses.activate
def test_find_emails_on_site_retries_before_giving_up():
    """A transient failure followed by a success on retry should NOT be
    reported as a connection error."""
    responses.add(responses.GET, "http://flaky.test", body=RequestsConnectionError("blip"))
    responses.add(
        responses.GET,
        "http://flaky.test",
        body='<html><a href="mailto:owner@flaky.test">Email</a></html>',
        status=200,
        content_type="text/html",
    )

    result = find_emails_on_site("http://flaky.test", contact_paths=["contact"], retries=1)

    assert result.status == FOUND
    assert result.emails == ["owner@flaky.test"]


@responses.activate
def test_find_emails_on_site_ignores_empty_mailto_link():
    """A styling-only <a href="mailto:"> with no address must not be
    reported as FOUND with a blank email."""
    responses.add(
        responses.GET,
        "http://emptymailto.test",
        body='<html><a href="mailto:">Contact us</a></html>',
        status=200,
        content_type="text/html",
    )
    responses.add(responses.GET, "http://emptymailto.test/contact", status=404)

    result = find_emails_on_site("http://emptymailto.test", contact_paths=["contact"])

    assert result.status == NO_EMAIL_FOUND
    assert result.emails == []
