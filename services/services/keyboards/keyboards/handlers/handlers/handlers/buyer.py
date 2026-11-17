"""Buyer registration via one-time invite link (verified Chat ID)."""
from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from database import arun
from handlers.common import get_cfg, get_db
from services.notification import esc, notify_admin, user_label

log = logging.getLogger(__name__)
CODE_RE = re.compile(r"[A-Za-z0-9_-]{6,40}")


async def register_from_start(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str) -> None:
    chat, user, msg = update.effective_chat, update.effective_user, update.effective_message
    if chat is None or user is None or msg is None or chat.type != "private":
        return
    if not CODE_RE.fullmatch(code):
        await msg.reply_text("❌ This registration link is invalid.")
        return
    db, cfg = get_db(context), get_cfg(context)
    buyer = await arun(db.consume_invite, code, chat.id, user.username)
    if buyer is None:
        await msg.reply_text(
            "❌ This registration link is invalid or was already used.\n"
            "Please ask the admin for a new link."
        )
        return
    await msg.reply_html(
        f"✅ <b>Registration complete!</b>\n\nWelcome, {esc(buyer['name'])}.\n"
        "Files sent by the admin will arrive in this chat. Please do not block the bot."
    )
    await notify_admin(
        context.bot, cfg.admin_id,
        "🛒 <b>BUYER REGISTERED</b>\n\n"
        f"Name: {esc(buyer['name'])}\n"
        f"Telegram: {esc(user_label(user.username, user.id))}\n"
        f"Chat ID: <code>{buyer['chat_id']}</code>",
    )


async def show_buyer_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE, buyer) -> None:
    await update.effective_message.reply_html(
        f"🛒 Hello {esc(buyer['name'])}! You are registered as a buyer.\n"
        "Files from the admin will arrive here automatically."
    )
