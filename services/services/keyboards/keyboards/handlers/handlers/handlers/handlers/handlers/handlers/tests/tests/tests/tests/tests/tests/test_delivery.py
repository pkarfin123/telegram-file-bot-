"""Delivery: success, duplicate prevention, errors. Telegram is faked."""
from types import SimpleNamespace

import pytest
from telegram.error import BadRequest, Forbidden, NetworkError

from handlers.delivery import perform_delivery


class FakeBot:
    def __init__(self, exc=None):
        self.exc = exc
        self.sent = []

    async def send_document(self, chat_id, document, filename=None, caption=None):
        if self.exc:
            raise self.exc
        self.sent.append({"chat_id": chat_id, "filename": filename, "caption": caption})
        return SimpleNamespace(message_id=42)


@pytest.fixture
def setup(db, tmp_path):
    f = tmp_path / "stored.xlsx"
    f.write_bytes(b"data")
    sid = db.create_submission(
        submitter_id=222, username="sub", full_name="Sub", source_type="telegram_file",
        original_name="inventory.xlsx", stored_path=str(f), telegram_file_id=None,
        size_bytes=4, sha256="h1",
    )
    code = db.create_buyer_invite("Karim")
    buyer = db.consume_invite(code, 5551, "karim")
    return SimpleNamespace(sid=sid, bid=buyer["id"], file=f)


async def test_successful_delivery_is_recorded(db, setup):
    bot = FakeBot()
    out = await perform_delivery(bot, db, setup.sid, setup.bid)
    assert out.status == "success"
    assert bot.sent[0]["chat_id"] == 5551
    assert bot.sent[0]["filename"] == "inventory.xlsx"

    row = db.get_submission(setup.sid)
    assert row["status"] == "delivered"
    assert row["delivered_buyer_id"] == setup.bid
    assert row["delivered_at"]
    assert db.has_successful_delivery(row["file_id"], setup.bid)

    deliveries = db.deliveries_for_submission(setup.sid)
    assert len(deliveries) == 1
    assert deliveries[0]["submitter_id"] == 222
    assert deliveries[0]["telegram_message_id"] == 42


async def test_caption_contains_reference_id(db, setup):
    bot = FakeBot()
    await perform_delivery(bot, db, setup.sid, setup.bid)
    assert f"#{1000 + setup.sid}" in bot.sent[0]["caption"]


async def test_duplicate_delivery_is_blocked_unless_forced(db, setup):
    bot = FakeBot()
    first = await perform_delivery(bot, db, setup.sid, setup.bid)
    second = await perform_delivery(bot, db, setup.sid, setup.bid)
    assert first.status == "success"
    assert second.status == "duplicate"
    assert len(bot.sent) == 1

    forced = await perform_delivery(bot, db, setup.sid, setup.bid, force=True)
    assert forced.status == "success"
    assert len(bot.sent) == 2


async def test_blocked_buyer_is_failed_not_delivered(db, setup):
    bot = FakeBot(exc=Forbidden("bot was blocked by the user"))
    out = await perform_delivery(bot, db, setup.sid, setup.bid)
    assert out.status == "failed"
    assert "blocked" in out.message.lower()

    row = db.get_submission(setup.sid)
    assert row["status"] == "pending"
    assert not db.has_successful_delivery(row["file_id"], setup.bid)
    assert db.stats()["deliveries_failed"] == 1


async def test_network_error_is_never_marked_successful(db, setup):
    bot = FakeBot(exc=NetworkError("connection reset"))
    out = await perform_delivery(bot, db, setup.sid, setup.bid)
    assert out.status == "failed"
    assert "not confirmed" in out.message.lower()
    assert db.get_submission(setup.sid)["status"] == "pending"


async def test_bad_request_is_failed(db, setup):
    bot = FakeBot(exc=BadRequest("chat not found"))
    out = await perform_delivery(bot, db, setup.sid, setup.bid)
    assert out.status == "failed"
    assert db.get_submission(setup.sid)["status"] == "pending"


async def test_retry_after_failure_can_succeed(db, setup):
    bad = FakeBot(exc=Forbidden("blocked"))
    assert (await perform_delivery(bad, db, setup.sid, setup.bid)).status == "failed"
    good = FakeBot()
    assert (await perform_delivery(good, db, setup.sid, setup.bid)).status == "success"
    assert db.get_submission(setup.sid)["status"] == "delivered"


async def test_missing_stored_file_fails(db, setup):
    setup.file.unlink()
    bot = FakeBot()
    out = await perform_delivery(bot, db, setup.sid, setup.bid)
    assert out.status == "failed"
    assert bot.sent == []


async def test_rejected_submission_cannot_be_delivered(db, setup):
    db.reject_submission(setup.sid)
    bot = FakeBot()
    out = await perform_delivery(bot, db, setup.sid, setup.bid)
    assert out.status == "invalid"
    assert bot.sent == []


async def test_removed_buyer_cannot_receive(db, setup):
    db.remove_buyer(setup.bid)
    bot = FakeBot()
    out = await perform_delivery(bot, db, setup.sid, setup.bid)
    assert out.status == "invalid"
    assert bot.sent == []


async def test_unknown_submission(db, setup):
    out = await perform_delivery(FakeBot(), db, 9999, setup.bid)
    assert out.status == "invalid"
