"""Google Sheets download: public export, or private via Service Account."""
from __future__ import annotations

import io
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

SHEET_URL_RE = re.compile(r"https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class SheetError(Exception):
    """Message is safe to show to the user."""


class SheetAccessError(SheetError):
    """Sheet is private / missing permission."""


def extract_sheet_id(text: str) -> str | None:
    m = SHEET_URL_RE.search(text or "")
    return m.group(1) if m else None


def service_account_email(sa_file: str) -> str | None:
    try:
        return json.loads(Path(sa_file).read_text(encoding="utf-8")).get("client_email")
    except Exception:
        return None


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Only follow redirects that stay on Google domains."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = (urllib.parse.urlparse(newurl).hostname or "").lower()
        if not (host == "google.com" or host.endswith(".google.com")
                or host.endswith(".googleusercontent.com")):
            raise SheetError("Google redirected to an unexpected address.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_public(sheet_id: str, dest: Path, max_bytes: int) -> None:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    opener = urllib.request.build_opener(_SafeRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (FileCollectorBot)"})
    try:
        with opener.open(req, timeout=40) as resp, open(dest, "wb") as out:
            written = 0
            first = True
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                if first:
                    if not chunk.startswith(b"PK"):  # HTML login page, not an xlsx
                        raise SheetAccessError("not public")
                    first = False
                written += len(chunk)
                if written > max_bytes:
                    raise SheetError(f"The sheet is too large (max {max_bytes // (1024 * 1024)} MB).")
                out.write(chunk)
            if written == 0:
                raise SheetAccessError("empty response")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise SheetAccessError(f"http {e.code}") from None
        raise SheetError(f"Google returned an error (HTTP {e.code}). Try again later.") from None
    except urllib.error.URLError:
        raise SheetError("Could not reach Google. Check the network and try again.") from None
    except TimeoutError:
        raise SheetError("Google took too long to respond. Try again.") from None


def _download_private(sheet_id: str, dest: Path, sa_file: str, max_bytes: int) -> None:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload

    email = service_account_email(sa_file) or "the service account"
    try:
        creds = service_account.Credentials.from_service_account_file(
            sa_file, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        request = service.files().export_media(fileId=sheet_id, mimeType=XLSX_MIME)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request, chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            if buf.tell() > max_bytes:
                raise SheetError(f"The sheet is too large (max {max_bytes // (1024 * 1024)} MB).")
        dest.write_bytes(buf.getvalue())
    except HttpError as e:
        if b"exportSizeLimitExceeded" in (e.content or b""):
            raise SheetError("The sheet is too large for Google to export.") from None
        if e.resp.status in (403, 404):
            raise SheetAccessError(
                f"No permission. Share the sheet (Viewer) with: {email}"
            ) from None
        raise SheetError(f"Google API error (HTTP {e.resp.status}).") from None
    except (OSError, ValueError):
        raise SheetError("The Google API credentials file is missing or invalid (ask the admin).") from None


def fetch_sheet(sheet_id: str, dest: Path, sa_file: str, max_bytes: int) -> str:
    """Blocking. Returns 'public' or 'private'. Raises SheetError."""
    dest = Path(dest)
    try:
        _download_public(sheet_id, dest, max_bytes)
        return "public"
    except SheetAccessError:
        dest.unlink(missing_ok=True)
        if not sa_file or not Path(sa_file).is_file():
            raise SheetAccessError(
                "This Google Sheet is private. Set its sharing to "
                "'Anyone with the link → Viewer' and send the link again."
            ) from None
    _download_private(sheet_id, dest, sa_file, max_bytes)
    return "private"
