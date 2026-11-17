"""Shared fixtures."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from database import Database


@pytest.fixture
def admin_id() -> int:
    return 111


@pytest.fixture
def db(tmp_path, admin_id):
    d = Database(tmp_path / "test.db")
    d.init(admin_id)
    yield d
    d.close()


@pytest.fixture
def xlsx_factory(tmp_path):
    def make(name, rows, title="Sheet1"):
        path = tmp_path / name
        wb = Workbook()
        ws = wb.active
        ws.title = title
        for r in rows:
            ws.append(r)
        wb.save(path)
        return path
    return make


@pytest.fixture
def make_context(tmp_path):
    def build(db, admin_id, bot=None):
        cfg = SimpleNamespace(
            admin_id=admin_id,
            max_file_bytes=5 * 1024 * 1024,
            upload_dir=tmp_path / "uploads",
            google_sa_file="",
        )
        return SimpleNamespace(
            application=SimpleNamespace(bot_data={"cfg": cfg, "db": db}),
            bot=bot or SimpleNamespace(send_message=AsyncMock()),
            args=[],
            user_data={},
        )
    return build
