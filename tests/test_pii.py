import pyarrow as pa
import pytest

from datasetvet.checks.health.pii import (
    PiiScanner,
    find_emails,
    find_phones,
    mask_email,
    mask_phone,
)


@pytest.mark.parametrize("text", [
    "jane.doe@example.com", "contact: j_d+tag@mail.example.co.uk.", "<a@b.io>",
])
def test_emails_matched(text):
    assert find_emails(text)


@pytest.mark.parametrize("text", [
    "pip install pkg@1.2.3", "user@localhost", "icon@2x.png", "logo@3x.jpg",
    "version 1.2.3", "2023-01-15", "@mention only", "a@b", "x @ y . com",
])
def test_non_emails_not_matched(text):
    assert find_emails(text) == []


def test_known_false_positive_ssh_remote():
    # An SSH remote is shaped exactly like an address; it counts as a pattern match. This is
    # why the report says "pattern matches", not "personal data".
    assert find_emails("git@github.com:org/repo.git") == ["git@github.com"]


@pytest.mark.parametrize("text", ["call +44 20 7946 0958 now", "+1 (415) 555-2671",
                                  "tel:+33142685300"])
def test_international_phones_matched(text):
    assert find_phones(text)


@pytest.mark.parametrize("text", [
    "2023-01-15", "version 10.2.33.4", "ISBN 978-3-16-148410-0", "+12", "score +1234567",
    "pi is 3.14159265358979", "+0 000 000 0000", "1/2/2024 12:30",
])
def test_non_phones_not_matched(text):
    assert find_phones(text) == []


def test_national_format_needs_region():
    assert find_phones("ring 020 7946 0958") == []
    assert find_phones("ring 020 7946 0958", region="GB")


def test_masking_never_prints_full_value():
    email = "jane.doe@example.com"
    masked = mask_email(email)
    assert masked == "j***@e***.com" and email not in masked and "doe" not in masked
    phone = "+44 20 7946 0958"
    m = mask_phone(phone)
    assert m == "+** ** **** **58" and "7946" not in m


def test_scanner_counts_values_and_masks_examples():
    s = PiiScanner()
    s.add("text", pa.array(["mail jane@example.com", "no pii", None, "+44 20 7946 0958",
                            "both a@example.org +1 415 555 2671"]))
    s.add("id", pa.array([1, 2, 3]))  # not a string column: ignored
    m = s.columns["text"]
    assert m.values_with_email == 2 and m.values_with_phone == 2
    assert all("***" in e for e in m.email_examples)
    assert "id" not in s.columns and s.any_found()
