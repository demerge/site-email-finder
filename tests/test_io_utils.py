from site_email_finder.config import DEFAULT_FIELD_MAP
from site_email_finder.io_utils import build_bio, row_get


def test_row_get_uses_field_map():
    row = {"name": "Acme Co", "email": "hi@acme.test"}
    assert row_get(row, DEFAULT_FIELD_MAP, "Name") == "Acme Co"
    assert row_get(row, DEFAULT_FIELD_MAP, "Email") == "hi@acme.test"
    assert row_get(row, DEFAULT_FIELD_MAP, "Website") == ""


def test_build_bio_prefers_description():
    row = {"description": "Great little bakery.", "primaryCategory": "Bakery",
           "address/city": "Portland", "address/state": "OR"}
    assert build_bio(row, DEFAULT_FIELD_MAP) == "Great little bakery."


def test_build_bio_falls_back_to_category_and_location():
    row = {"description": "", "primaryCategory": "Bakery",
           "address/city": "Portland", "address/state": "OR"}
    assert build_bio(row, DEFAULT_FIELD_MAP) == "Bakery in Portland, OR"


def test_build_bio_handles_missing_location():
    row = {"description": "", "primaryCategory": "Bakery",
           "address/city": "", "address/state": ""}
    assert build_bio(row, DEFAULT_FIELD_MAP) == "Bakery"
