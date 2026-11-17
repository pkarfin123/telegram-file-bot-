"""Admin commands, dashboard views and the callback router."""
from __future__ import annotations

import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from database import arun, display_id
from handlers.common import admin_only, get_cfg, get_db, render_dashboard, send
from keyboards import admin_keyboard as akb
from keyboards.user_keyboard import main_menu_kb
from services.file_service import safe_remove
from services.notification import (STATUS_LABEL, broadcast, esc, fmt_dt,
                                   submission_detail_text, user_label)

log = logging.getLogger(__name__)
PER_PAGE = 6

FILE_TITLES = {
    "pending": "⏳ Pending Files",
    "all": "📁 All Files",
    "deliver": "🚀 Deliver Files — pick a pending file",
}


def _parse_id(args: list[str]) -> int | None:
    if not args:
        return None
    s = args[0].strip()
    if s.isdigit() and 0 < int(s) < 10 ** 13:
        return int(s)
    return None


# ------------------------------------------------------------------ views
async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, kb = await render_dashboard(get_db(context))
    await send(update, text, kb)


async def show_files(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str, page: int = 0) -> None:
    db = get_db(context)
    status = "pending" if mode in ("pending", "deliver") else None
    total = await arun(db.count_submissions, status)
    page = min(max(page, 0), max(0, (total - 1) // PER_PAGE))
    rows = await arun(db.list_submissions, status, PER_PAGE, page * PER_PAGE)
    if total == 0:
        text = f"<b>{FILE_TITLES[mode]}</b>\n\nNothing here yet."
    else:
        text = f"<b>{FILE_TITLES[mode]}</b> ({total})\n\nTap a file:"
    await send(update, text, akb.file_list_kb(rows, mode, page, total, PER_PAGE))


async def show_file_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, sid: int) -> None:
    db = get_db(context)
    row = await arun(db.get_submission, sid)
    if row is None:
        await send(update, "File not found.", akb.home_kb())
        return
    dels = await arun(db.deliveries_for_submission, sid)
    await send(update, submission_detail_text(row, dels), akb.file_detail_kb(sid, row["status"]))


async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    users = await arun(db.list_approved)
    reqs = await arun(db.list_access_requests)
    lines = [f"👥 <b>Approved Users</b> ({len(users)})", ""]
    if not users:
        lines.append("No approved users yet. Use <code>/approve USER_ID</code>")
    for u in users[:30]:
        lines.append(f"• {esc(user_label(u['username'], u['telegram_id']))} — <code>{u['telegram_id']}</code>")
    if reqs:
        lines += ["", f"🔔 <b>Access requests</b> ({len(reqs)})"]
        for r in reqs[:10]:
            lines.append(f"• {esc(user_label(r['username'], r['telegram_id']))} — <code>{r['telegram_id']}</code>")
    await send(update, "\n".join(lines), akb.users_kb(users[:10], reqs[:10]))


async def show_buyers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    buyers = await arun(get_db(context).list_buyers)
    lines = [f"🛒 <b>Registered Buyers</b> ({len(buyers)})", ""]
    if not buyers:
        lines.append("No buyers yet. Use <code>/addbuyer Name</code> to create an invite link.")
    for b in buyers[:30]:
        lines.append(f"• ID {b['id']} — {esc(b['name'])} ({esc(user_label(b['username'], b['chat_id']))})")
    await send(update, "\n".join(lines), akb.buyers_kb(buyers))


async def show_buyer_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, bid: int) -> None:
    db = get_db(context)
    b = await arun(db.get_buyer, bid)
    if b is None:
        await send(update, "Buyer not found.", akb.home_kb())
        return
    hist = await arun(db.buyer_delivery_history, bid, 10)
    lines = [
        f"🛒 <b>{esc(b['name'])}</b>", "",
        f"Telegram: {esc(user_label(b['username'], b['chat_id']))}",
        f"Chat ID: <code>{b['chat_id']}</code>",
        f"Registered: {fmt_dt(b['registered_at'])}",
        f"Active: {'yes' if b['is_active'] else 'no'}", "",
        "<b>Delivery history</b>",
    ]
    if not hist:
        lines.append("No deliveries yet.")
    for d in hist:
        icon = "✅" if d["status"] == "success" else "❌"
        lines.append(f"{icon} #{display_id(d['submission_id'])} · {esc(d['original_name'])} · {fmt_dt(d['created_at'])}")
    await send(update, "\n".join(lines), akb.buyer_detail_kb(bid))


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    db = get_db(context)
    total = await arun(db.count_deliveries)
    page = min(max(page, 0), max(0, (total - 1) // PER_PAGE))
    rows = await arun(db.list_deliveries, PER_PAGE, page * PER_PAGE)
    lines = [f"📜 <b>Delivery History</b> ({total})", ""]
    if not rows:
        lines.append("No deliveries yet.")
    for d in rows:
        icon = "✅" if d["status"] == "success" else "❌"
        lines.append(f"{icon} #{display_id(d['submission_id'])} · {esc(d['original_name'])}\n"
                     f"    → {esc(d['buyer_name'])} · {fmt_dt(d['created_at'])}")
        if d["status"] == "failed" and d["error"]:
            lines.append(f"    ⚠️ {esc(d['error'][:100])}")
    await send(update, "\n".join(lines), akb.history_kb(page, total, PER_PAGE))


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = await arun(get_db(context).stats)
    text = (
        "📊 <b>Statistics</b>\n\n"
        f"👥 Approved users: {s['approved_users']}\n"
        f"🛒 Buyers: {s['buyers']}\n"
        f"📁 Total submissions: {s['submissions']}\n"
        f"⏳ Pending: {s['pending']}\n"
        f"✅ Delivered: {s['delivered']}\n"
        f"🚫 Rejected: {s['rejected']}\n"
        f"🚀 Successful deliveries: {s['deliveries_ok']}\n"
        f"❌ Failed deliveries: {s['deliveries_failed']}"
    )
    await send(update, text, akb.home_kb())


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    values = {k: await arun(db.get_setting, k) for k in akb.SETTING_LABELS}
    await send(update, "⚙️ <b>Bot Settings</b>\n\nTap to switch ON/OFF:", akb.settings_kb(values))


# ------------------------------------------------------------------ approve / remove helpers
async def _approve(context: ContextTypes.DEFAULT_TYPE, uid: int) -> str:
    cfg, db = get_cfg(context), get_db(context)
    req = await arun(db.get_access_request, uid)
    await arun(db.approve_user, uid, req["username"] if req else None,
               req["full_name"] if req else None, cfg.admin_id)
    try:
        await context.bot.send_message(
            uid, "✅ <b>You have been approved!</b>\n\nYou can now send .xlsx files or Google Sheets links.",
            parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())
        return "The user was notified."
    except TelegramError:
        return "Could not message the user (they must open the bot and press Start first)."


# ------------------------------------------------------------------ commands
@admin_only
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_dashboard(update, context)


@admin_only
async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = _parse_id(context.args)
    if uid is None:
        await update.effective_message.reply_html("Usage: <code>/approve 123456789</code>")
        return
    if uid == get_cfg(context).admin_id:
        await update.effective_message.reply_text("You are the admin already.")
        return
    note = await _approve(context, uid)
    await update.effective_message.reply_html(f"✅ User <code>{uid}</code> approved.\n{esc(note)}")


@admin_only
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = _parse_id(context.args)
    if uid is None:
        await update.effective_message.reply_html("Usage: <code>/remove 123456789</code>")
        return
    ok = await arun(get_db(context).remove_user, uid)
    await update.effective_message.reply_html(
        f"🗑 User <code>{uid}</code> removed." if ok else "That user is not in the approved list.")


@admin_only
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_users(update, context)


@admin_only
async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_files(update, context, "pending", 0)


@admin_only
async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_files(update, context, "all", 0)


@admin_only
async def buyers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_buyers(update, context)


@admin_only
async def addbuyer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = " ".join(context.args).strip()
    if not name or len(name) > 60:
        await update.effective_message.reply_html("Usage: <code>/addbuyer Buyer Name</code> (max 60 characters)")
        return
    code = await arun(get_db(context).create_buyer_invite, name)
    link = f"https://t.me/{context.bot.username}?start=buy_{code}"
    await update.effective_message.reply_html(
        f"🛒 <b>Invite created for {esc(name)}</b>\n\n"
        "Send this one-time link to the buyer. When they open it and press <b>Start</b>, "
        "they are registered with their verified Chat ID:\n\n"
        f"<code>{esc(link)}</code>")


@admin_only
async def removebuyer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await show_buyers(update, context)
        return
    db = get_db(context)
    buyer = await arun(db.find_buyer, context.args[0])
    if buyer is None:
        await update.effective_message.reply_text("Buyer not found. Use /buyers to see IDs.")
        return
    await arun(db.remove_buyer, buyer["id"])
    await update.effective_message.reply_html(f"🗑 Buyer <b>{esc(buyer['name'])}</b> removed. History is kept.")


@admin_only
async def deliver_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_files(update, context, "deliver", 0)


@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_stats(update, context)


@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args).strip()
    if not text:
        await update.effective_message.reply_html("Usage: <code>/broadcast Your announcement</code>")
        return
    if len(text) > 3500:
        await update.effective_message.reply_text("Message is too long (max 3500 characters).")
        return
    context.user_data["broadcast"] = text
    n = len(await arun(get_db(context).list_approved))
    await update.effective_message.reply_html(
        f"📢 <b>Preview</b> (will be sent to {n} approved users):\n\n{esc(text)}",
        reply_markup=akb.broadcast_confirm_kb())


# ------------------------------------------------------------------ callbacks
@admin_only
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    db, cfg = get_db(context), get_cfg(context)
    parts = q.data.split(":")
    kind = parts[0]
    try:
        if kind == "adm":
            action = parts[1]
            page = int(parts[2]) if len(parts) > 2 else 0
            if action in FILE_TITLES:
                await show_files(update, context, action, page)
            elif action == "home":
                await show_dashboard(update, context)
            elif action == "users":
                await show_users(update, context)
            elif action == "buyers":
                await show_buyers(update, context)
            elif action == "history":
                await show_history(update, context, page)
            elif action == "stats":
                await show_stats(update, context)
            elif action == "settings":
                await show_settings(update, context)
            elif action == "backup":
                path = await arun(db.backup, cfg.backup_dir, cfg.backup_keep)
                with open(path, "rb") as fh:
                    await context.bot.send_document(q.message.chat_id, fh, filename=Path(path).name,
                                                    caption="💾 Database backup (keep it private!)")
                await show_settings(update, context)
        elif kind == "file":
            await show_file_detail(update, context, int(parts[1]))
        elif kind == "fget":
            row = await arun(db.get_submission, int(parts[1]))
            if row is None or not Path(row["stored_path"]).is_file():
                await q.answer("File is missing on the server.", show_alert=True)
                return
            with open(row["stored_path"], "rb") as fh:
                await context.bot.send_document(q.message.chat_id, fh, filename=row["original_name"])
        elif kind == "rej":
            sid = int(parts[1])
            await send(update, f"Reject submission <b>#{display_id(sid)}</b>? It can no longer be delivered.",
                       akb.reject_confirm_kb(sid))
        elif kind == "rejy":
            sid = int(parts[1])
            await arun(db.reject_submission, sid)
            await show_file_detail(update, context, sid)
        elif kind == "usr":
            uid = int(parts[2])
            if parts[1] == "rm":
                await send(update, f"Remove user <code>{uid}</code> from approved submitters?",
                           akb.user_remove_confirm_kb(uid))
            elif parts[1] == "rmy":
                await arun(db.remove_user, uid)
                await show_users(update, context)
        elif kind == "buy":
            action = parts[1]
            if action == "add":
                await send(update, "To add a buyer send:\n<code>/addbuyer Buyer Name</code>\n"
                                   "You will get a one-time link for the buyer.", akb.home_kb())
            else:
                bid = int(parts[2])
                if action == "view":
                    await show_buyer_detail(update, context, bid)
                elif action == "rm":
                    await send(update, "Remove this buyer? Delivery history is kept.",
                               akb.buyer_remove_confirm_kb(bid))
                elif action == "rmy":
                    await arun(db.remove_buyer, bid)
                    await show_buyers(update, context)
        elif kind == "req":
            uid = int(parts[2])
            if parts[1] == "ok":
                note = await _approve(context, uid)
                await send(update, f"✅ User <code>{uid}</code> approved.\n{esc(note)}", akb.home_kb())
            elif parts[1] == "no":
                await arun(db.delete_access_request, uid)
                try:
                    await context.bot.send_message(uid, "Your access request was not approved.")
                except TelegramError:
                    pass
                await send(update, f"🚫 Request from <code>{uid}</code> declined.", akb.home_kb())
        elif kind == "set":
            if parts[1] in akb.SETTING_LABELS:
                await arun(db.toggle_setting, parts[1])
            await show_settings(update, context)
        elif kind == "bc":
            if parts[1] == "yes":
                text = context.user_data.pop("broadcast", None)
                if not text:
                    await send(update, "Nothing to send.", akb.home_kb())
                    return
                ids = [u["telegram_id"] for u in await arun(db.list_approved)]
                await send(update, f"📢 Sending to {len(ids)} users…")
                ok, failed = await broadcast(context.bot, ids, "📢 Announcement\n\n" + text)
                await send(update, f"📢 Done. Sent: {ok} · Failed: {failed}", akb.home_kb())
            else:
                context.user_data.pop("broadcast", None)
                await send(update, "❎ Broadcast cancelled.", akb.home_kb())
    except (IndexError, ValueError):
        log.warning("Bad admin callback data: %r", q.data)
    except TelegramError:
        log.exception("Telegram error in admin callback %r", q.data)
