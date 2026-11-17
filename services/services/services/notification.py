"""Message formatting helpers, admin notification and broadcast."""
from __future__ import annotations

import asyncio
import html
import logging
from typing import Iterable, Optional

from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError

from database import display_id

log = logging.getLogger(__name__)

STATUS_LABEL = {
    "pending": "⏳ Pending Review",
    "delivered": "✅ Delivered",
    "rejected": "🚫 Rejected",
}


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def user_label(username: Optional[str], user_id: int) -> str:
    return f"@{username}" if username else f"ID {user_id}"


def fmt_dt(value: Optional[str]) -> str:
    return f"{value[:16]} UTC" if value else "-"


def human_size(n: int) -> str:
    size = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def retry_seconds(exc: RetryAfter) -> float:
    delay = exc.retry_after
    return delay.total_seconds() if hasattr(delay, "total_seconds") else float(delay)


def submission_confirmation_text(sub_id: int, name: str) -> str:
    return (
        "✅ <b>File Submitted Successfully!</b>\n\n"
        f"Submission ID: <b>#{display_id(sub_id)}</b>\n"
        f"File: {esc(name)}\n"
        f"Status: {STATUS_LABEL['pending']}\n\n"
        "Your file has been sent to the Admin."
    )


def admin_new_file_text(row) -> str:
    return (
        "📥 <b>NEW FILE RECEIVED</b>\n\n"
        f"Submission ID: <b>#{display_id(row['id'])}</b>\n"
        f"Submitter: {esc(user_label(row['submitter_username'], row['submitter_id']))}\n"
        f"File: {esc(row['original_name'])}\n"
        f"Status: {STATUS_LABEL[row['status']]}"
    )


def delivery_success_text(buyer, sub) -> str:
    return (
        "🚀 <b>FILE DELIVERED SUCCESSFULLY</b>\n\n"
        f"Buyer: {esc(user_label(buyer['username'], buyer['chat_id']))} ({esc(buyer['name'])})\n"
        f"File: {esc(sub['original_name'])}\n"
        f"Submission ID: #{display_id(sub['id'])}\n"
        "Delivery Status: Successful"
    )


def submission_detail_text(row, deliveries) -> str:
    kind = "Google Sheet" if row["source_type"] == "google_sheet" else "Excel upload"
    lines = [
        f"📄 <b>Submission #{display_id(row['id'])}</b>",
        "",
        f"File: <b>{esc(row['original_name'])}</b>",
        f"Type: {kind}",
        f"Size: {human_size(row['size_bytes'])}",
        f"Sheets: {row['sheets_count'] or '-'} · Rows: {row['rows_count'] or '-'}",
        f"Submitter: {esc(user_label(row['submitter_username'], row['submitter_id']))} "
        f"(<code>{row['submitter_id']}</code>)",
        f"Submitted: {fmt_dt(row['created_at'])}",
        f"Status: {STATUS_LABEL[row['status']]}",
    ]
    if row["sheet_url"]:
        lines.append(f"Link: {esc(row['sheet_url'])}")
    if deliveries:
        lines += ["", "<b>Delivered to:</b>"]
        for d in deliveries:
            lines.append(f"• {esc(d['buyer_name'])} — {fmt_dt(d['created_at'])}")
    return "\n".join(lines)


async def notify_admin(bot, admin_id: int, text: str, reply_markup=None) -> bool:
    try:
        await bot.send_message(admin_id, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return True
    except TelegramError:
        log.warning("Could not notify admin", exc_info=True)
        return False


async def broadcast(bot, user_ids: Iterable[int], text: str) -> tuple[int, int]:
    """Plain-text broadcast. Returns (sent, failed)."""
    ok = failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=text)
            ok += 1
        except RetryAfter as e:
            await asyncio.sleep(retry_seconds(e) + 1)
            try:
                await bot.send_message(chat_id=uid, text=text)
                ok += 1
            except TelegramError:
                failed += 1
        except TelegramError:
            failed += 1
        await asyncio.sleep(0.05)
    return ok, failed
