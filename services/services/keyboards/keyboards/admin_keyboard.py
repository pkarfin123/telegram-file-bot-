"""Inline keyboards for the admin dashboard. Callback data format: prefix:action:args"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database import display_id
from services.notification import user_label

SETTING_LABELS = {
    "notify_on_submit": "Notify me on new files",
    "accept_xlsx": "Accept .xlsx uploads",
    "accept_sheets": "Accept Google Sheets links",
    "submissions_open": "Submissions open",
}


def _b(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _short(text: object, n: int) -> str:
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


def pager(prefix: str, page: int, total: int, per_page: int) -> list[InlineKeyboardButton]:
    pages = max(1, -(-total // per_page))
    if pages <= 1:
        return []
    row = []
    if page > 0:
        row.append(_b("⬅️ Prev", f"{prefix}:{page - 1}"))
    row.append(_b(f"{page + 1}/{pages}", f"{prefix}:{page}"))
    if page < pages - 1:
        row.append(_b("Next ➡️", f"{prefix}:{page + 1}"))
    return row


def home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_b("🏠 Dashboard", "adm:home")]])


def dashboard_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_b("⏳ Pending Files", "adm:pending:0"), _b("📁 All Files", "adm:all:0")],
        [_b("👥 Approved Users", "adm:users"), _b("🛒 Manage Buyers", "adm:buyers")],
        [_b("🚀 Deliver Files", "adm:deliver:0"), _b("📜 Delivery History", "adm:history:0")],
        [_b("📊 Statistics", "adm:stats"), _b("⚙️ Bot Settings", "adm:settings")],
    ])


def file_list_kb(rows, mode: str, page: int, total: int, per_page: int) -> InlineKeyboardMarkup:
    kb = []
    for r in rows:
        label = (f"#{display_id(r['id'])} · {_short(r['original_name'], 20)} · "
                 f"{_short(user_label(r['submitter_username'], r['submitter_id']), 16)}")
        data = f"dl:pick:{r['id']}" if mode == "deliver" else f"file:{r['id']}"
        kb.append([_b(label, data)])
    nav = pager(f"adm:{mode}", page, total, per_page)
    if nav:
        kb.append(nav)
    kb.append([_b("🏠 Dashboard", "adm:home")])
    return InlineKeyboardMarkup(kb)


def file_detail_kb(sid: int, status: str) -> InlineKeyboardMarkup:
    kb = []
    if status != "rejected":
        kb.append([_b("🚀 Deliver to Buyer", f"dl:pick:{sid}")])
    kb.append([_b("📥 Download Copy", f"fget:{sid}")])
    if status == "pending":
        kb.append([_b("🚫 Reject File", f"rej:{sid}")])
    kb.append([_b("⬅️ Pending", "adm:pending:0"), _b("🏠 Dashboard", "adm:home")])
    return InlineKeyboardMarkup(kb)


def reject_confirm_kb(sid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("✅ Yes, reject", f"rejy:{sid}"), _b("↩️ No", f"file:{sid}"),
    ]])


def buyer_pick_kb(sid: int, buyers) -> InlineKeyboardMarkup:
    kb = [[_b(f"🛒 {_short(b['name'], 24)} ({_short(user_label(b['username'], b['chat_id']), 16)})",
              f"dl:buyer:{sid}:{b['id']}")] for b in buyers[:30]]
    kb.append([_b("⬅️ Back", f"file:{sid}"), _b("❎ Cancel", "dl:cancel")])
    return InlineKeyboardMarkup(kb)


def confirm_kb(sid: int, bid: int, duplicate_same_buyer: bool) -> InlineKeyboardMarkup:
    if duplicate_same_buyer:
        first = _b("⚠️ Deliver Again Anyway", f"dl:force:{sid}:{bid}")
    else:
        first = _b("✅ Confirm Delivery", f"dl:go:{sid}:{bid}")
    return InlineKeyboardMarkup([[first], [_b("❎ Cancel", "dl:cancel")]])


def retry_kb(sid: int, bid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_b("🔁 Retry", f"dl:go:{sid}:{bid}")],
        [_b("❎ Cancel", "dl:cancel")],
    ])


def users_kb(users, requests) -> InlineKeyboardMarkup:
    kb = [[_b(f"❌ Remove {_short(user_label(u['username'], u['telegram_id']), 24)}",
              f"usr:rm:{u['telegram_id']}")] for u in users]
    for r in requests:
        who = _short(user_label(r["username"], r["telegram_id"]), 18)
        kb.append([_b(f"✅ Approve {who}", f"req:ok:{r['telegram_id']}"),
                   _b("🚫", f"req:no:{r['telegram_id']}")])
    kb.append([_b("🏠 Dashboard", "adm:home")])
    return InlineKeyboardMarkup(kb)


def user_remove_confirm_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("✅ Yes, remove", f"usr:rmy:{uid}"), _b("↩️ No", "adm:users"),
    ]])


def access_request_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("✅ Approve", f"req:ok:{uid}"), _b("🚫 Decline", f"req:no:{uid}"),
    ]])


def buyers_kb(buyers) -> InlineKeyboardMarkup:
    kb = [[_b(f"🛒 {_short(b['name'], 28)}", f"buy:view:{b['id']}")] for b in buyers[:30]]
    kb.append([_b("➕ Add Buyer", "buy:add")])
    kb.append([_b("🏠 Dashboard", "adm:home")])
    return InlineKeyboardMarkup(kb)


def buyer_detail_kb(bid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_b("🗑 Remove Buyer", f"buy:rm:{bid}")],
        [_b("⬅️ Buyers", "adm:buyers"), _b("🏠 Dashboard", "adm:home")],
    ])


def buyer_remove_confirm_kb(bid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("✅ Yes, remove", f"buy:rmy:{bid}"), _b("↩️ No", f"buy:view:{bid}"),
    ]])


def history_kb(page: int, total: int, per_page: int) -> InlineKeyboardMarkup:
    kb = []
    nav = pager("adm:history", page, total, per_page)
    if nav:
        kb.append(nav)
    kb.append([_b("🏠 Dashboard", "adm:home")])
    return InlineKeyboardMarkup(kb)


def settings_kb(values: dict[str, str]) -> InlineKeyboardMarkup:
    kb = [[_b(f"{'✅' if values.get(k) == '1' else '❌'} {label}", f"set:{k}")]
          for k, label in SETTING_LABELS.items()]
    kb.append([_b("💾 Backup Database Now", "adm:backup")])
    kb.append([_b("🏠 Dashboard", "adm:home")])
    return InlineKeyboardMarkup(kb)


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("📢 Send to all", "bc:yes"), _b("❎ Cancel", "bc:no"),
    ]])
