"""Excel validation, safe file handling and login-secret detection."""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".xlsx"}
MAX_UNZIPPED_BYTES = 200 * 1024 * 1024
MAX_SCAN_ROWS = 2000
HEADER_ROWS = 5

# Column names that clearly indicate login secrets (compared after
# lower-casing and removing every non letter/digit character).
SECRET_HEADERS_EXACT = {
    "password", "pass", "passwd", "pwd", "otp", "2fa", "cookie", "cookies",
    "token", "accesstoken", "sessionid", "secret", "cuser", "xs", "datr",
    "fbdtsg", "recoverycode", "backupcode", "authcode", "twofactorcode",
}
SECRET_HEADER_PARTS = (
    "password", "passwd", "cookie", "accesstoken", "recoverycode", "backupcode",
    "twofactor", "2fa", "authenticator", "sessiontoken", "sessioncookie",
    "secretkey", "authcode", "fbdtsg", "verificationcode",
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"c_user\s*=\s*\d+", re.I),
    re.compile(r"\bxs\s*=\s*[\w%:\-]{10,}", re.I),
    re.compile(r"\bdatr\s*=\s*[\w\-]{10,}", re.I),
    re.compile(r"\bfb_dtsg\b", re.I),
    re.compile(r"\bEAA[A-Za-z0-9]{40,}"),
)

SECRET_MESSAGE = (
    "Sheet '{sheet}' contains a login-secret field (such as password, cookie, "
    "token, OTP or 2FA/recovery code). This bot does not accept such data."
)


@dataclass
class ValidationResult:
    ok: bool
    error: str = ""
    sheets: int = 0
    rows: int = 0


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def is_secret_header(value: object) -> bool:
    n = _norm(value)
    if not n or len(n) > 40:
        return False
    return n in SECRET_HEADERS_EXACT or any(p in n for p in SECRET_HEADER_PARTS)


def has_secret_value(value: str) -> bool:
    return any(p.search(value) for p in SECRET_VALUE_PATTERNS)


def has_allowed_extension(name: str) -> bool:
    return Path(str(name)).suffix.lower() in ALLOWED_EXTENSIONS


def clean_display_name(name: str | None) -> str:
    name = re.sub(r"[\x00-\x1f]", "", str(name or "file.xlsx")).strip()
    return (name or "file.xlsx")[:120]


def sanitize_filename(name: str) -> str:
    base = Path(str(name)).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(base).stem).strip("._") or "file"
    ext = Path(base).suffix.lower()
    return f"{stem[:80]}{ext}"


def build_store_path(upload_dir: Path, submitter_id: int, original_name: str) -> Path:
    folder = Path(upload_dir) / str(int(submitter_id))
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{uuid.uuid4().hex[:12]}_{sanitize_filename(original_name)}"
    if folder.resolve() not in dest.resolve().parents:
        raise ValueError("Unsafe file path")
    return dest


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_remove(path: Path | None) -> None:
    if path is None:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        log.warning("Could not delete %s", path)


def validate_xlsx(path: Path, max_bytes: int) -> ValidationResult:
    """Blocking; call with asyncio.to_thread()."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        return ValidationResult(False, "The file could not be read.")
    if size == 0:
        return ValidationResult(False, "The file is empty.")
    if size > max_bytes:
        return ValidationResult(False, f"File is too large (max {max_bytes // (1024 * 1024)} MB).")
    if not zipfile.is_zipfile(path):
        return ValidationResult(False, "This is not a valid .xlsx file (it may be renamed or corrupted).")
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "[Content_Types].xml" not in names or not any(n.startswith("xl/") for n in names):
                return ValidationResult(False, "This is not a valid Excel (.xlsx) workbook.")
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                return ValidationResult(False, "Workbooks containing macros are not accepted.")
            if sum(i.file_size for i in zf.infolist()) > MAX_UNZIPPED_BYTES:
                return ValidationResult(False, "The file expands to an unsafe size and was rejected.")
    except zipfile.BadZipFile:
        return ValidationResult(False, "The file is corrupted.")

    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception:  # openpyxl raises many different exception types
        log.info("openpyxl could not open %s", path.name, exc_info=True)
        return ValidationResult(False, "The workbook could not be opened. Please re-save it in Excel and try again.")

    try:
        sheets = 0
        rows_total = 0
        non_empty = 0
        for ws in wb.worksheets:
            sheets += 1
            counted = 0
            for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                if r_idx > MAX_SCAN_ROWS:
                    break
                counted = r_idx
                for cell in row:
                    if cell is None:
                        continue
                    non_empty += 1
                    if isinstance(cell, str):
                        if r_idx <= HEADER_ROWS and is_secret_header(cell):
                            return ValidationResult(False, SECRET_MESSAGE.format(sheet=ws.title))
                        if len(cell) >= 10 and has_secret_value(cell):
                            return ValidationResult(False, SECRET_MESSAGE.format(sheet=ws.title))
            declared = getattr(ws, "max_row", None) or 0
            rows_total += max(counted, declared)
        if sheets == 0:
            return ValidationResult(False, "The workbook has no sheets.")
        if non_empty == 0:
            return ValidationResult(False, "The workbook contains no data.")
        return ValidationResult(True, "", sheets, rows_total)
    except Exception:
        log.info("Error while scanning %s", path.name, exc_info=True)
        return ValidationResult(False, "The workbook could not be read. Please re-save it and try again.")
    finally:
        try:
            wb.close()
        except Exception:
            pass
