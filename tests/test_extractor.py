import responses

from site_email_finder.extractor import (
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

    assert result.status == "found"
    assert result.emails == ["owner@biz.test"]
    assert "http://biz.test/contact" in result.checked_urls


@responses.activate
def test_find_emails_on_site_no_email_found():
    responses.add(responses.GET, "http://noemail.test", body="<html>nothing</html>", status=200,
                   content_type="text/html")
    responses.add(responses.GET, "http://noemail.test/contact", status=404)

    result = find_emails_on_site("http://noemail.test", contact_paths=["contact"])

    assert result.status == "no_email_found"
    assert result.emails == []
