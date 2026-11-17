"""Keyboards for submitters and unauthorised users."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _b(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_b("📤 Submit Excel File", "me:submit")],
        [_b("🔗 Submit Google Sheet", "me:sheet")],
        [_b("📂 My Submissions", "me:mine"), _b("❓ Help", "me:help")],
    ])


def request_access_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_b("🔑 Request Access", "reqask")]])
