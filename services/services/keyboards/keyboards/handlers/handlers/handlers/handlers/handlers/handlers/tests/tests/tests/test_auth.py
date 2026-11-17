"""Admin and submitter authorization."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from handlers.common import admin_only, is_admin_user
from handlers.submitter import _authorized


def _update(user_id):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, username="u", full_name="U"),
        callback_query=None,
        effective_message=SimpleNamespace(reply_text=AsyncMock(), reply_html=AsyncMock()),
    )


def test_only_configured_admin_is_admin(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    assert is_admin_user(ctx, admin_id) is True
    assert is_admin_user(ctx, 999) is False


def test_admin_id_must_also_exist_in_admins_table(db, make_context):
    # cfg says 999 is admin, but the database only knows admin 111
    ctx = make_context(db, 999)
    assert is_admin_user(ctx, 999) is False


async def test_admin_only_blocks_strangers(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    called = []

    @admin_only
    async def protected(update, context):
        called.append(1)

    stranger = _update(555)
    await protected(stranger, ctx)
    assert called == []
    stranger.effective_message.reply_text.assert_awaited_once()


async def test_admin_only_blocks_missing_user(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    called = []

    @admin_only
    async def protected(update, context):
        called.append(1)

    upd = SimpleNamespace(effective_user=None, callback_query=None,
                          effective_message=SimpleNamespace(reply_text=AsyncMock()))
    await protected(upd, ctx)
    assert called == []


async def test_admin_only_allows_admin(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    called = []

    @admin_only
    async def protected(update, context):
        called.append(1)

    await protected(_update(admin_id), ctx)
    assert called == [1]


async def test_unapproved_submitter_is_rejected(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    upd = _update(222)
    assert await _authorized(upd, ctx) is False
    upd.effective_message.reply_html.assert_awaited_once()


async def test_approved_submitter_is_allowed_and_removal_revokes(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    db.approve_user(222, "sub", "Sub", admin_id)
    assert await _authorized(_update(222), ctx) is True
    db.remove_user(222)
    assert await _authorized(_update(222), ctx) is False


async def test_admin_can_always_submit(db, admin_id, make_context):
    ctx = make_context(db, admin_id)
    assert await _authorized(_update(admin_id), ctx) is True
