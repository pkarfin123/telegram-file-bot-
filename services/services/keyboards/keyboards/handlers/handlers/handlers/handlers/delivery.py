"""File delivery: confirmation flow and the core perform_delivery()."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import ContextTypes

from database import Database, arun, display_id
from handlers.common import admin_only, get_cfg, get_db, render_dashboard, send
from keyboards import admin_keyboard as akb
from services.notification import (delivery_success_text, esc, fmt_dt, notify_admin,
                                   retry_seconds, user_label)

log = logging.getLogger(__name__)


@dataclass
class DeliveryOutcome:
    status: str  # success | failed | duplicate | invalid
    message: str = ""
    delivery_id: Optional[int] = None
    submission: object = None
    buyer: object = None


async def perform_delivery(bot, db: Database, submission_id: int, buyer_id: int,
                           *, force: bool = False) -> DeliveryOutcome:
    """Send the file. A delivery is recorded as successful ONLY after Telegram
    returned the sent message (i.e. confirmed it)."""
    sub = await arun(db.get_submission, submission_id)
    buyer = await arun(db.get_buyer, buyer_id)
    if sub is None:
        return DeliveryOutcome("invalid", "Submission not found.")
    if buyer is None or not buyer["is_active"]:
        return DeliveryOutcome("invalid", "Buyer not found or no longer active.", submission=sub)
    if sub["status"] == "rejected":
        return DeliveryOutcome("invalid", "This file was rejected and cannot be delivered.",
                               submission=sub, buyer=buyer)
    if not force and await arun(db.has_successful_delivery, sub["file_id"], buyer_id):
        return DeliveryOutcome("duplicate", "This file was already delivered to this buyer.",
                               submission=sub, buyer=buyer)

    path = Path(sub["stored_path"])
    error: Optional[str] = None
    message_id: Optional[int] = None

    if not path.is_file():
        error = "The stored file is missing on the server."
    else:
        caption = (f"📦 New file for you\nFile: {sub['original_name']}\n"
                   f"Reference: #{display_id(sub['id'])}")
        try:
            with path.open("rb") as fh:
                sent = await bot.send_document(
                    chat_id=buyer["chat_id"], document=fh,
                    filename=sub["original_name"], caption=caption,
                )
            message_id = sent.message_id
        except Forbidden:
            error = "The buyer blocked the bot or has not started it."
        except BadRequest as e:
            error = f"Telegram rejected the request: {e.message}"
        except (TimedOut, NetworkError) as e:
            error = (f"Network problem ({e}). Delivery is NOT confirmed — it may or may not have "
                     "arrived. Ask the buyer before retrying.")
        except RetryAfter as e:
            error = f"Telegram rate limit. Try again in {int(retry_seconds(e)) + 1} seconds."
        except TelegramError as e:
            error = f"Telegram error: {e}"

    if error is None:
        try:
            did = await arun(
                db.record_delivery, submission_id=sub["id"], file_id=sub["file_id"],
                buyer_id=buyer["id"], submitter_id=sub["submitter_id"], success=True,
                telegram_message_id=message_id,
            )
        except Exception:
            log.exception("Delivered but could not record delivery for submission %s", sub["id"])
            return DeliveryOutcome("success", "Delivered, but saving the record failed (see logs).",
                                   None, sub, buyer)
        return DeliveryOutcome("success", "Delivered.", did, sub, buyer)

    try:
        did = await arun(
            db.record_delivery, submission_id=sub["id"], file_id=sub["file_id"],
            buyer_id=buyer["id"], submitter_id=sub["submitter_id"], success=False, error=error,
        )
    except Exception:
        log.exception("Could not record failed delivery")
        did = None
    return DeliveryOutcome("failed", error, did, sub, buyer)


async def _confirm_text(db: Database, sub, buyer) -> tuple[str, bool]:
    dels = await arun(db.deliveries_for_submission, sub["id"])
    same = [d for d in dels if d["buyer_id"] == buyer["id"]]
    lines = [
        "🚀 <b>Confirm Delivery</b>", "",
        f"File: <b>{esc(sub['original_name'])}</b>",
        f"Submission ID: #{display_id(sub['id'])}",
        f"Submitter: {esc(user_label(sub['submitter_username'], sub['submitter_id']))}",
        f"Buyer: <b>{esc(buyer['name'])}</b> ({esc(user_label(buyer['username'], buyer['chat_id']))})",
    ]
    if same:
        lines += ["", f"⚠️ <b>Duplicate warning:</b> already delivered to this buyer on {fmt_dt(same[-1]['created_at'])}."]
    elif dels:
        names = ", ".join(esc(d["buyer_name"]) for d in dels)
        lines += ["", f"⚠️ This file was already delivered to: {names}."]
    return "\n".join(lines), bool(same)


async def _run_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        sid: int, bid: int, force: bool) -> None:
    db, cfg = get_db(context), get_cfg(context)
    inflight: set = context.application.bot_data.setdefault("inflight", set())
    key = (sid, bid)
    if key in inflight:
        return  # double tap protection
    inflight.add(key)
    try:
        await send(update, "⏳ Sending file… please wait.")
        out = await perform_delivery(context.bot, db, sid, bid, force=force)
    finally:
        inflight.discard(key)

    if out.status == "success":
        await send(update, "✅ Delivery completed.", akb.home_kb())
        await notify_admin(context.bot, cfg.admin_id, delivery_success_text(out.buyer, out.submission))
    elif out.status == "duplicate":
        text, _ = await _confirm_text(db, out.submission, out.buyer)
        await send(update, text, akb.confirm_kb(sid, bid, True))
    elif out.status == "failed":
        await send(update, f"❌ <b>Delivery failed</b>\n\n{esc(out.message)}", akb.retry_kb(sid, bid))
    else:
        await send(update, f"❌ {esc(out.message)}", akb.home_kb())


@admin_only
async def delivery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    db = get_db(context)
    parts = q.data.split(":")
    try:
        action = parts[1]
        if action == "cancel":
            text, kb = await render_dashboard(db)
            await send(update, "❎ Cancelled.\n\n" + text, kb)
        elif action == "pick":
            sid = int(parts[2])
            sub = await arun(db.get_submission, sid)
            if sub is None or sub["status"] == "rejected":
                await send(update, "This file is not available for delivery.", akb.home_kb())
                return
            buyers = await arun(db.list_buyers)
            if not buyers:
                await send(update, "No buyers registered yet.\nUse <code>/addbuyer Name</code> first.",
                           akb.home_kb())
                return
            await send(update, f"🛒 Choose a buyer for <b>{esc(sub['original_name'])}</b> "
                               f"(#{display_id(sid)}):", akb.buyer_pick_kb(sid, buyers))
        elif action == "buyer":
            sid, bid = int(parts[2]), int(parts[3])
            sub = await arun(db.get_submission, sid)
            buyer = await arun(db.get_buyer, bid)
            if sub is None or buyer is None:
                await send(update, "Not found.", akb.home_kb())
                return
            text, dup = await _confirm_text(db, sub, buyer)
            await send(update, text, akb.confirm_kb(sid, bid, dup))
        elif action in ("go", "force"):
            await _run_delivery(update, context, int(parts[2]), int(parts[3]), force=(action == "force"))
    except (IndexError, ValueError):
        log.warning("Bad delivery callback data: %r", q.data)
