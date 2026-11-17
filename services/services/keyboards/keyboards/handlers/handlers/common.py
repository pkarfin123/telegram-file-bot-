"""Shared helpers: dependency access, admin guard, send-or-edit, dashboard."""
from __future__ import annotations

import logging
from functools import wraps

from telegram import InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import Config
from database import Database, arun
from keyboards.admin_keyboard import dashboard_kb

log = logging.getLogger(__name__)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def get_cfg(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.application.bot_data["cfg"]


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


def is_admin_user(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Strict check: must match the ADMIN_ID from .env AND exist in admins table."""
    return user_id == get_cfg(context).admin_id and get_db(context).is_admin(user_id)


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user is None or not is_admin_user(context, user.id):
            log.warning("Blocked admin action from %s", user.id if user else "unknown")
            if update.callback_query:
                await update.callback_query.answer("⛔ Not authorized", show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text("⛔ This command is for the admin only.")
            return None
        return await func(update, context, *args, **kwargs)
    return wrapper


async def send(update: Update, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit the current message for button taps; reply for commands."""
    q = update.callback_query
    if q:
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup,
                                      link_preview_options=NO_PREVIEW)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
    elif update.effective_message:
        await update.effective_message.reply_html(text, reply_markup=markup,
                                                  link_preview_options=NO_PREVIEW)


async def render_dashboard(db: Database) -> tuple[str, InlineKeyboardMarkup]:
    s = await arun(db.stats)
    text = (
        "🛠 <b>Admin Dashboard</b>\n\n"
        f"⏳ Pending files: <b>{s['pending']}</b>\n"
        f"📁 Total files: <b>{s['submissions']}</b>\n"
        f"👥 Approved users: <b>{s['approved_users']}</b>\n"
        f"🛒 Buyers: <b>{s['buyers']}</b>\n"
        f"🚀 Successful deliveries: <b>{s['deliveries_ok']}</b>"
    )
    return text, dashboard_kb()
