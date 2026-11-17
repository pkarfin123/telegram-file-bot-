"""Submitter flow: /start, /help, .xlsx uploads, Google Sheets links, access requests."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from database import arun, display_id
from handlers import buyer as buyer_handlers
from handlers.common import get_cfg, get_db, is_admin_user, render_dashboard, send
from keyboards import admin_keyboard as akb
from keyboards.user_keyboard import main_menu_kb, request_access_kb
from services import file_service as fs
from services.google_sheets import SheetError, extract_sheet_id, fetch_sheet
from services.notification import (STATUS_LABEL, admin_new_file_text, esc,
                                   notify_admin, submission_confirmation_text, user_label)

log = logging.getLogger(__name__)

HELP_USER = (
    "❓ <b>Help</b>\n\n"
    "• Send an <b>.xlsx</b> file here, or\n"
    "• Send a <b>Google Sheets link</b>.\n\n"
    "Your file goes to the Admin for review.\n"
    "Please never include passwords, cookies, tokens or OTP/2FA codes — such files are rejected."
)
HELP_ADMIN = (
    "🛠 <b>Admin commands</b>\n\n"
    "/admin – dashboard\n"
    "/approve &lt;user_id&gt; – approve a submitter\n"
    "/remove &lt;user_id&gt; – remove a submitter\n"
    "/users – approved users &amp; requests\n"
    "/pending – pending files\n"
    "/files – all files\n"
    "/buyers – registered buyers\n"
    "/addbuyer &lt;name&gt; – create buyer invite link\n"
    "/removebuyer &lt;id|@username&gt; – remove a buyer\n"
    "/deliver – deliver a pending file\n"
    "/stats – statistics\n"
    "/broadcast &lt;text&gt; – message all approved users\n"
    "/help – this message"
)


async def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if user is None:
        return False
    if is_admin_user(context, user.id) or await arun(get_db(context).is_approved, user.id):
        return True
    await update.effective_message.reply_html(
        "⛔ <b>Not authorized.</b>\n\nOnly approved users can submit files. "
        "You can ask the admin for access:",
        reply_markup=request_access_kb(),
    )
    return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat, user, msg = update.effective_chat, update.effective_user, update.effective_message
    if chat is None or user is None or msg is None or chat.type != "private":
        return
    db = get_db(context)
    if context.args and context.args[0].startswith("buy_"):
        await buyer_handlers.register_from_start(update, context, context.args[0][4:])
        return
    if is_admin_user(context, user.id):
        text, kb = await render_dashboard(db)
        await msg.reply_html(text, reply_markup=kb)
        return
    buyer = await arun(db.get_buyer_by_chat, chat.id)
    if buyer is not None:
        await buyer_handlers.show_buyer_welcome(update, context, buyer)
        return
    if await arun(db.is_approved, user.id):
        await arun(db.touch_user_profile, user.id, user.username, user.full_name)
        await msg.reply_html(
            f"👋 Welcome, {esc(user.first_name)}!\n\nSend me an <b>.xlsx</b> file or a "
            "<b>Google Sheets link</b> and I will pass it to the Admin.",
            reply_markup=main_menu_kb(),
        )
        return
    await msg.reply_html(
        "👋 Welcome!\n\nThis is a private file-collection bot. "
        "You need approval from the Admin before you can submit files.",
        reply_markup=request_access_kb(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if user is None or msg is None:
        return
    await msg.reply_html(HELP_ADMIN if is_admin_user(context, user.id) else HELP_USER)


async def request_access_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    user = q.from_user
    db, cfg = get_db(context), get_cfg(context)
    if is_admin_user(context, user.id) or await arun(db.is_approved, user.id):
        await q.edit_message_text("✅ You already have access.")
        return
    is_new = await arun(db.add_access_request, user.id, user.username, user.full_name)
    if is_new:
        await notify_admin(
            context.bot, cfg.admin_id,
            "🔔 <b>ACCESS REQUEST</b>\n\n"
            f"User: {esc(user_label(user.username, user.id))}\n"
            f"Name: {esc(user.full_name)}\nID: <code>{user.id}</code>",
            akb.access_request_kb(user.id),
        )
    await q.edit_message_text("✅ Your request was sent to the Admin. You will get a message when approved.")


async def submitter_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not await _authorized(update, context):
        return
    action = q.data.split(":")[1] if ":" in q.data else ""
    msg = q.message
    if action == "submit":
        await msg.reply_text("📤 Send your .xlsx file now (as a document, max "
                             f"{get_cfg(context).max_file_bytes // (1024 * 1024)} MB).")
    elif action == "sheet":
        await msg.reply_text("🔗 Paste your Google Sheets link now.")
    elif action == "help":
        await msg.reply_html(HELP_USER)
    elif action == "mine":
        rows = await arun(get_db(context).list_user_submissions, q.from_user.id, 10)
        if not rows:
            await msg.reply_text("You have not submitted anything yet.")
            return
        lines = ["📂 <b>Your latest submissions</b>", ""]
        for r in rows:
            lines.append(f"#{display_id(r['id'])} · {esc(r['original_name'])} · {STATUS_LABEL[r['status']]}")
        await msg.reply_html("\n".join(lines))


def _setting_blocks(db, kind: str) -> str | None:
    if db.get_setting("submissions_open") != "1":
        return "⏸ Submissions are temporarily closed. Please try again later."
    if kind == "xlsx" and db.get_setting("accept_xlsx") != "1":
        return "⏸ Excel uploads are currently turned off."
    if kind == "sheet" and db.get_setting("accept_sheets") != "1":
        return "⏸ Google Sheets links are currently turned off."
    return None


async def _finalize(update: Update, context: ContextTypes.DEFAULT_TYPE, status_msg, dest: Path,
                    original_name: str, source_type: str, tg_file_id: str | None,
                    sheet_url: str | None) -> None:
    cfg, db, user = get_cfg(context), get_db(context), update.effective_user
    result = await asyncio.to_thread(fs.validate_xlsx, dest, cfg.max_file_bytes)
    if not result.ok:
        fs.safe_remove(dest)
        await status_msg.edit_text(f"❌ File rejected.\n\n{result.error}")
        return
    sha = await asyncio.to_thread(fs.sha256_file, dest)
    dup = await arun(db.find_duplicate_by_hash, sha)
    if dup is not None:
        fs.safe_remove(dest)
        await status_msg.edit_text(
            f"⚠️ This exact file was already submitted (Submission #{display_id(dup['id'])}). "
            "Duplicate submissions are not accepted.")
        return
    try:
        sid = await arun(
            db.create_submission, submitter_id=user.id, username=user.username,
            full_name=user.full_name, source_type=source_type, original_name=original_name,
            stored_path=str(dest), telegram_file_id=tg_file_id, size_bytes=dest.stat().st_size,
            sha256=sha, sheet_url=sheet_url, sheets_count=result.sheets, rows_count=result.rows,
        )
    except sqlite3.Error:
        log.exception("Database error while saving submission")
        fs.safe_remove(dest)
        await status_msg.edit_text("❌ Could not save your submission (database error). Please try again.")
        return
    await status_msg.edit_text(submission_confirmation_text(sid, original_name),
                               parse_mode=ParseMode.HTML)
    if db.get_setting("notify_on_submit") == "1":
        row = await arun(db.get_submission, sid)
        await notify_admin(context.bot, cfg.admin_id, admin_new_file_text(row),
                           akb.InlineKeyboardMarkup([[akb._b("👁 View", f"file:{sid}")]]))


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, user = update.effective_message, update.effective_user
    if msg is None or user is None or msg.document is None or msg.chat.type != "private":
        return
    if not await _authorized(update, context):
        return
    cfg, db = get_cfg(context), get_db(context)
    blocked = _setting_blocks(db, "xlsx")
    if blocked:
        await msg.reply_text(blocked)
        return
    doc = msg.document
    name = fs.clean_display_name(doc.file_name)
    if not fs.has_allowed_extension(name):
        await msg.reply_text("❌ Unsupported format. Only .xlsx files or Google Sheets links are accepted.")
        return
    if doc.file_size and doc.file_size > cfg.max_file_bytes:
        await msg.reply_text(f"❌ File is too large (max {cfg.max_file_bytes // (1024 * 1024)} MB).")
        return
    status_msg = await msg.reply_text("⏳ Receiving and checking your file…")
    dest = fs.build_store_path(cfg.upload_dir, user.id, name)
    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(custom_path=dest)
    except TelegramError as e:
        fs.safe_remove(dest)
        log.warning("Download failed: %s", e)
        await status_msg.edit_text("❌ Could not download the file from Telegram. Please try again.")
        return
    await _finalize(update, context, status_msg, dest, name, "telegram_file", doc.file_id, None)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, user = update.effective_message, update.effective_user
    if msg is None or user is None or not msg.text or msg.chat.type != "private":
        return
    if not await _authorized(update, context):
        return
    sheet_id = extract_sheet_id(msg.text)
    if sheet_id is None:
        await msg.reply_text("Please send an .xlsx file or a Google Sheets link.",
                             reply_markup=main_menu_kb())
        return
    cfg, db = get_cfg(context), get_db(context)
    blocked = _setting_blocks(db, "sheet")
    if blocked:
        await msg.reply_text(blocked)
        return
    status_msg = await msg.reply_text("⏳ Downloading your Google Sheet…")
    name = f"sheet_{sheet_id[:10]}.xlsx"
    dest = fs.build_store_path(cfg.upload_dir, user.id, name)
    try:
        await asyncio.to_thread(fetch_sheet, sheet_id, dest, cfg.google_sa_file, cfg.max_file_bytes)
    except SheetError as e:
        fs.safe_remove(dest)
        await status_msg.edit_text(f"❌ {e}")
        return
    except Exception:
        log.exception("Unexpected Google Sheets error")
        fs.safe_remove(dest)
        await status_msg.edit_text("❌ Could not fetch the sheet. Please try again later.")
        return
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    await _finalize(update, context, status_msg, dest, name, "google_sheet", None, url)


async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None or msg.chat.type != "private":
        return
    if await _authorized(update, context):
        await msg.reply_text("Please send an .xlsx file (as a document) or a Google Sheets link.")
