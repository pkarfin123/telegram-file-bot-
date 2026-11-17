"""Excel validation, login-secret rejection, safe file handling."""
import hashlib
import zipfile

import pytest

from services import file_service as fs
from services.google_sheets import extract_sheet_id

MB = 1024 * 1024


def test_valid_xlsx_is_accepted(xlsx_factory):
    p = xlsx_factory("ok.xlsx", [["Product", "Qty"], ["Pen", 10], ["Book", 5]])
    r = fs.validate_xlsx(p, 5 * MB)
    assert r.ok, r.error
    assert r.sheets == 1
    assert r.rows >= 3


def test_text_file_renamed_to_xlsx_is_rejected(tmp_path):
    p = tmp_path / "fake.xlsx"
    p.write_text("hello")
    assert fs.validate_xlsx(p, 5 * MB).ok is False


def test_empty_file_is_rejected(tmp_path):
    p = tmp_path / "empty.xlsx"
    p.write_bytes(b"")
    r = fs.validate_xlsx(p, 5 * MB)
    assert r.ok is False
    assert "empty" in r.error.lower()


def test_oversized_file_is_rejected(xlsx_factory):
    p = xlsx_factory("big.xlsx", [["A", "B"], [1, 2]])
    r = fs.validate_xlsx(p, 100)
    assert r.ok is False
    assert "too large" in r.error.lower()


def test_workbook_without_data_is_rejected(xlsx_factory):
    p = xlsx_factory("blank.xlsx", [])
    r = fs.validate_xlsx(p, 5 * MB)
    assert r.ok is False
    assert "no data" in r.error.lower()


def test_macro_workbook_is_rejected(xlsx_factory):
    p = xlsx_factory("macro.xlsx", [["A", "B"], [1, 2]])
    with zipfile.ZipFile(p, "a") as zf:
        zf.writestr("xl/vbaProject.bin", b"x")
    r = fs.validate_xlsx(p, 5 * MB)
    assert r.ok is False
    assert "macro" in r.error.lower()


@pytest.mark.parametrize("header", [
    "Password", "OTP", "2FA Code", "Access Token", "Cookie", "Recovery Code", "c_user",
])
def test_login_secret_headers_are_rejected(xlsx_factory, header):
    p = xlsx_factory("secret.xlsx", [[header, "Name"], ["x", "y"]])
    r = fs.validate_xlsx(p, 5 * MB)
    assert r.ok is False
    assert "login-secret" in r.error


def test_cookie_value_is_rejected(xlsx_factory):
    p = xlsx_factory("cookie.xlsx", [["Name", "Note"],
                                     ["a", "c_user=100012345678901; xs=abcdefghij1234567890"]])
    assert fs.validate_xlsx(p, 5 * MB).ok is False


def test_access_token_value_is_rejected(xlsx_factory):
    p = xlsx_factory("tok.xlsx", [["Name", "Note"], ["a", "EAA" + "B" * 45]])
    assert fs.validate_xlsx(p, 5 * MB).ok is False


@pytest.mark.parametrize("header", ["Product", "Quantity", "Price", "Email", "Address"])
def test_normal_headers_are_not_flagged(header):
    assert fs.is_secret_header(header) is False


@pytest.mark.parametrize("name,expected", [
    ("a.xlsx", True), ("A.XLSX", True), ("a.xls", False),
    ("a.csv", False), ("a.xlsx.exe", False), ("noextension", False),
])
def test_extension_check(name, expected):
    assert fs.has_allowed_extension(name) is expected


def test_sanitize_filename_removes_path_tricks():
    out = fs.sanitize_filename("../../etc/passwd.xlsx")
    assert "/" not in out and ".." not in out
    assert out.endswith(".xlsx")


def test_store_path_stays_inside_upload_dir(tmp_path):
    base = tmp_path / "up"
    p = fs.build_store_path(base, 5, "../../evil name.xlsx")
    assert (base / "5").resolve() in p.resolve().parents
    assert p.name.endswith("evil_name.xlsx")


def test_sha256_matches_hashlib(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello world")
    assert fs.sha256_file(p) == hashlib.sha256(b"hello world").hexdigest()


def test_google_sheet_link_parsing():
    sid = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    assert extract_sheet_id(f"https://docs.google.com/spreadsheets/d/{sid}/edit#gid=0") == sid
    assert extract_sheet_id("https://example.com/spreadsheets/d/" + sid) is None
    assert extract_sheet_id("hello") is None
