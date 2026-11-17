"""Configuration loaded from environment variables. No secrets in code."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Telegram Bot API lets bots download files up to 20 MB.
TELEGRAM_DOWNLOAD_LIMIT_MB = 20


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int
    data_dir: Path
    db_path: Path
    upload_dir: Path
    backup_dir: Path
    log_dir: Path
    max_file_bytes: int
    backup_keep: int
    google_sa_file: str
    log_level: str


def load_config(env_file: str | None = None) -> Config:
    load_dotenv(env_file)  # silently does nothing if no .env file exists

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "put_your_bot_token_here":
        raise ConfigError("BOT_TOKEN সেট করা নেই (.env ফাইল দেখুন)।")

    admin_raw = os.getenv("ADMIN_ID", "").strip()
    try:
        admin_id = int(admin_raw)
    except ValueError:
        raise ConfigError("ADMIN_ID অবশ্যই একটি সংখ্যা হতে হবে।") from None
    if admin_id <= 0:
        raise ConfigError("ADMIN_ID সঠিক নয়।")

    try:
        max_mb = int(os.getenv("MAX_FILE_MB", "20"))
    except ValueError:
        raise ConfigError("MAX_FILE_MB সংখ্যা হতে হবে।") from None
    max_mb = max(1, min(max_mb, TELEGRAM_DOWNLOAD_LIMIT_MB))

    try:
        backup_keep = max(1, int(os.getenv("BACKUP_KEEP", "14")))
    except ValueError:
        raise ConfigError("BACKUP_KEEP সংখ্যা হতে হবে।") from None

    data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve()
    upload_dir = data_dir / "uploads"
    backup_dir = data_dir / "backups"
    log_dir = data_dir / "logs"
    for d in (data_dir, upload_dir, backup_dir, log_dir):
        d.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=token,
        admin_id=admin_id,
        data_dir=data_dir,
        db_path=data_dir / "bot.db",
        upload_dir=upload_dir,
        backup_dir=backup_dir,
        log_dir=log_dir,
        max_file_bytes=max_mb * 1024 * 1024,
        backup_keep=backup_keep,
        google_sa_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
