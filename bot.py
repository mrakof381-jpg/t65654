import json
import logging
import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError, Forbidden, BadRequest

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8893617089:AAGRBy6etZYSliRhX8Z9sQSyueKLT7j_UXM"
ADMIN_ID = 8546607388  # <-- сюда свой Telegram ID

USERS_FILE = Path("users.json")
# ===================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def load_users() -> set[int]:
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data)
        except Exception:
            return set()
    return set()


def save_users(users: set[int]):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(users), f, ensure_ascii=False, indent=2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users = load_users()
    
    if user.id not in users:
        users.add(user.id)
        save_users(users)
        logger.info(f"Новый пользователь: {user.id} ({user.full_name})")
    
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n\n"
        "Ты подписался на рассылку.\n"
        "Когда появится новая информация — я пришлю сообщение."
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Только для админа: сколько пользователей"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    users = load_users()
    await update.message.reply_text(f"Всего подписчиков: {len(users)}")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Рассылка.
    Использование:
    1. Напиши /broadcast
    2. Следующим сообщением отправь текст (или фото с подписью)
    """
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У тебя нет прав для рассылки.")
        return

    # Если команда написана с текстом сразу: /broadcast Привет всем!
    if context.args:
        text = " ".join(context.args)
        await do_broadcast(context, text=text, photo=None)
        return

    await update.message.reply_text(
        "Отправь сейчас сообщение, которое нужно разослать всем.\n"
        "(можно просто текст или фото с подписью)\n\n"
        "Чтобы отменить — напиши /cancel"
    )
    context.user_data["waiting_broadcast"] = True


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data.pop("waiting_broadcast", None)
    await update.message.reply_text("Рассылка отменена.")


async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ловит следующее сообщение после /broadcast"""
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.user_data.get("waiting_broadcast"):
        return

    context.user_data["waiting_broadcast"] = False

    text = update.message.caption or update.message.text
    photo = None

    if update.message.photo:
        # Берём фото наилучшего качества
        photo = update.message.photo[-1].file_id

    await do_broadcast(context, text=text, photo=photo)


async def do_broadcast(context: ContextTypes.DEFAULT_TYPE, text: str | None, photo: str | None):
    users = load_users()
    if not users:
        await context.bot.send_message(ADMIN_ID, "Нет подписчиков для рассылки.")
        return

    await context.bot.send_message(
        ADMIN_ID,
        f"Начинаю рассылку для {len(users)} пользователей..."
    )

    success = 0
    failed = 0
    blocked = []

    for user_id in users:
        try:
            if photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=text
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text
                )
            success += 1
        except Forbidden:
            # Пользователь заблокировал бота
            blocked.append(user_id)
            failed += 1
        except (BadRequest, TelegramError) as e:
            logger.warning(f"Ошибка отправки {user_id}: {e}")
            failed += 1
        
        # Небольшая пауза, чтобы не словить лимиты Telegram
        await asyncio.sleep(0.05)

    # Удаляем тех, кто заблокировал бота
    if blocked:
        users = load_users()
        users -= set(blocked)
        save_users(users)

    await context.bot.send_message(
        ADMIN_ID,
        f"Рассылка завершена!\n\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибок: {failed}\n"
        f"🚫 Заблокировали бота: {len(blocked)}"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Ловим любое сообщение от админа после команды /broadcast
    app.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO,
        handle_broadcast_message
    ))

    print("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
