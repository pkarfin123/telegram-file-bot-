"""Entry point: python bot.py"""
from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler

from telegram import BotCommand, BotCommandScopeChat, Update
from telegram.error import TelegramError
from telegram.ext import (Application, ApplicationBuilder, CallbackQueryHandler,
                          CommandHandler, ContextTypes, MessageHandler, filters)

from config import Config, ConfigError, load_config
from database import Database, arun
from handlers import admin, delivery, submitter

log = logging.getLogger("bot")
PRIVATE = filters.ChatType.PRIVATE

ADMIN_COMMANDS = [
    ("start", "Start the bot"), ("admin", "Open admin dashboard"),
    ("approve", "Approve a submitter"), ("remove", "Remove an approved submitter"),
    ("users", "View approved users"), ("pending", "View pending submissions"),
    ("files", "View all submitted files"), ("buyers", "View registered buyers"),
    ("addbuyer", "Register a buyer"), ("removebuyer", "Remove a buyer"),
    ("deliver", "Deliver a selected file"), ("stats", "View bot statistics"),
    ("broadcast", "Announce to approved users"), ("help", "Show commands"),
]


def setup_logging(cfg: Config) -> None:
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(cfg.log_dir / "bot.log", maxBytes=1_000_000,
                                backupCount=5, encoding="utf-8"),
        ],
    )
    # httpx logs full request URLs, which contain the bot token. Keep them quiet.
    for noisy in ("httpx", "httpcore", "telegram.ext.ExtBot"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def _backup_loop(app: Application) -> None:
    cfg, db = app.bot_data["cfg"], app.bot_data["db"]
    while True:
        try:
            path = await arun(db.backup, cfg.backup_dir, cfg.backup_keep)
            log.info("Database backup saved: %s", path.name)
        except Exception:
            log.exception("Database backup failed")
        await asyncio.sleep(24 * 3600)


async def post_init(app: Application) -> None:
    cfg: Config = app.bot_data["cfg"]
    await app.bot.set_my_commands([BotCommand("start", "Start the bot"), BotCommand("help", "Show help")])
    try:
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in ADMIN_COMMANDS],
                                      scope=BotCommandScopeChat(cfg.admin_id))
    except TelegramError:
        log.warning("Could not set the admin command menu (open the bot and press /start once).")
    app.bot_data["backup_task"] = asyncio.create_task(_backup_loop(app))
    log.info("Bot started as @%s", app.bot.username)


async def post_shutdown(app: Application) -> None:
    task = app.bot_data.get("backup_task")
    if task:
        task.cancel()
    app.bot_data["db"].close()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Something went wrong. Please try again.")
        except TelegramError:
            pass


def register_handlers(app: Application) -> None:
    commands = {
        "start": submitter.start_command, "help": submitter.help_command,
        "admin": admin.admin_command, "approve": admin.approve_command,
        "remove": admin.remove_command, "users": admin.users_command,
        "pending": admin.pending_command, "files": admin.files_command,
        "buyers": admin.buyers_command, "addbuyer": admin.addbuyer_command,
        "removebuyer": admin.removebuyer_command, "deliver": admin.deliver_command,
        "stats": admin.stats_command, "broadcast": admin.broadcast_command,
    }
    for name, fn in commands.items():
        app.add_handler(CommandHandler(name, fn, filters=PRIVATE))

    app.add_handler(CallbackQueryHandler(delivery.delivery_callback, pattern=r"^dl:"))
    app.add_handler(CallbackQueryHandler(
        admin.admin_callback, pattern=r"^(adm|file|fget|rej|rejy|usr|buy|req|set|bc):"))
    app.add_handler(CallbackQueryHandler(submitter.submitter_menu_callback, pattern=r"^me:"))
    app.add_handler(CallbackQueryHandler(submitter.request_access_callback, pattern=r"^reqask$"))

    app.add_handler(MessageHandler(filters.Document.ALL & PRIVATE, submitter.handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & PRIVATE, submitter.handle_text))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & PRIVATE, submitter.handle_other))
    app.add_error_handler(on_error)


def main() -> None:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"❌ Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
    setup_logging(cfg)

    db = Database(cfg.db_path)
    db.init(cfg.admin_id)

    app = (
        ApplicationBuilder()
        .token(cfg.bot_token)
        .concurrent_updates(8)
        .connect_timeout(15).read_timeout(30).write_timeout(120).pool_timeout(15)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["cfg"] = cfg
    app.bot_data["db"] = db
    register_handlers(app)
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
