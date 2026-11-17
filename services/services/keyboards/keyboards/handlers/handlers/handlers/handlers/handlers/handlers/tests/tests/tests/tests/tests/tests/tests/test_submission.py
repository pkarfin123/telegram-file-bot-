"""Submitter flow: file submission, duplicates, unsupported formats."""
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock

from handlers.submitter import _finalize, handle_document


def _user(uid=222):
    return SimpleNamespace(id=uid, username="sub", full_name="Sub User", first_name="Sub")


async def test_valid_file_is_saved_and_admin_notified(db, admin_id, make_context, xlsx_factory, tmp_path):
    ctx = make_context(db, admin_id)
    dest = xlsx_factory("a.xlsx", [["Name", "Qty"], ["x", 1]])
    status_msg = SimpleNamespace(edit_text=AsyncMock())
    update = SimpleNamespace(effective_user=_user())

    await _finalize(update, ctx, status_msg, dest, "a.xlsx", "telegram_file", "fid", None)

    assert db.count_submissions() == 1
    row = db.get_submission(1)
    assert row["submitter_id"] == 222
    assert row["status"] == "pending"
    assert row["size_bytes"] > 0 and row["sha256"]
    assert "Submitted Successfully" in status_msg.edit_text.call_args.args[0]
    assert "#1001" in status_msg.edit_text.call_args.args[0]
    ctx.bot.send_message.assert_awaited_once()
    assert ctx.bot.send_message.call_args.args[0] == admin_id


async def test_admin_notification_can_be_turned_off(db, admin_id, make_context, xlsx_factory):
    ctx = make_context(db, admin_id)
    db.set_setting("notify_on_submit", "0")
    dest = xlsx_factory("a.xlsx", [["Name", "Qty"], ["x", 1]])
    await _finalize(SimpleNamespace(effective_user=_user()), ctx,
                    SimpleNamespace(edit_text=AsyncMock()), dest, "a.xlsx", "telegram_file", "f", None)
    assert db.count_submissions() == 1
    ctx.bot.send_message.assert_not_awaited()


async def test_duplicate_file_is_rejected(db, admin_id, make_context, xlsx_factory, tmp_path):
    ctx = make_context(db, admin_id)
    first = xlsx_factory("a.xlsx", [["Name", "Qty"], ["x", 1]])
    second = tmp_path / "copy.xlsx"
    shutil.copy(first, second)

    await _finalize(SimpleNamespace(effective_user=_user()), ctx,
                    SimpleNamespace(edit_text=AsyncMock()), first, "a.xlsx", "telegram_file", "f", None)
    msg2 = SimpleNamespace(edit_text=AsyncMock())
    await _finalize(SimpleNamespace(effective_user=_user()), ctx,
                    msg2, second, "copy.xlsx", "telegram_file", "f2", None)

    assert db.count_submissions() == 1
    assert "already submitted" in msg2.edit_text.call_args.args[0]
    assert not second.exists()


async def test_file_with_login_secrets_is_rejected(db, admin_id, make_context, xlsx_factory):
    ctx = make_context(db, admin_id)
    dest = xlsx_factory("bad.xlsx", [["Email", "Password"], ["a@b.com", "x"]])
    msg = SimpleNamespace(edit_text=AsyncMock())
    await _finalize(SimpleNamespace(effective_user=_user()), ctx, msg, dest,
                    "bad.xlsx", "telegram_file", "f", None)
    assert db.count_submissions() == 0
    assert "rejected" in msg.edit_text.call_args.args[0].lower()
    assert not dest.exists()


async def test_invalid_excel_is_rejected_and_removed(db, admin_id, make_context, tmp_path):
    ctx = make_context(db, admin_id)
    dest = tmp_path / "broken.xlsx"
    dest.write_text("not a real workbook")
    msg = SimpleNamespace(edit_text=AsyncMock())
    await _finalize(SimpleNamespace(effective_user=_user()), ctx, msg, dest,
                    "broken.xlsx", "telegram_file", "f", None)
    assert db.count_submissions() == 0
    assert not dest.exists()


def _doc_update(file_name, file_size, user):
    msg = SimpleNamespace(
        document=SimpleNamespace(file_name=file_name, file_size=file_size, file_id="x"),
        chat=SimpleNamespace(type="private"),
        reply_text=AsyncMock(),
        reply_html=AsyncMock(),
    )
    return SimpleNamespace(effective_message=msg, effective_user=user)


async def test_unapproved_user_cannot_submit(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    upd = _doc_update("a.xlsx", 100, _user(555))
    await handle_document(upd, ctx)
    upd.effective_message.reply_html.assert_awaited_once()
    assert db.count_submissions() == 0


async def test_unsupported_format_is_rejected(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    db.approve_user(222, "sub", "Sub", admin_id)
    upd = _doc_update("a.xls", 100, _user())
    await handle_document(upd, ctx)
    assert "Unsupported" in upd.effective_message.reply_text.call_args.args[0]
    assert db.count_submissions() == 0


async def test_oversized_file_is_rejected(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    db.approve_user(222, "sub", "Sub", admin_id)
    upd = _doc_update("a.xlsx", 500 * 1024 * 1024, _user())
    await handle_document(upd, ctx)
    assert "too large" in upd.effective_message.reply_text.call_args.args[0].lower()
    assert db.count_submissions() == 0


async def test_closed_submissions_block_uploads(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    db.approve_user(222, "sub", "Sub", admin_id)
    db.set_setting("submissions_open", "0")
    upd = _doc_update("a.xlsx", 100, _user())
    await handle_document(upd, ctx)
    assert "closed" in upd.effective_message.reply_text.call_args.args[0].lower()
    assert db.count_submissions() == 0
