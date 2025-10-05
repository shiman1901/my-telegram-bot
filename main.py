import logging
import asyncio
import time
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = "7723918807:AAFPfwLnRFi1-4jGfeNk4j6AVaKZ9mauw6I"
CHANNEL_ID = -1003154844765
YOUR_ADMIN_ID = 5610556402  # Твой Telegram ID

POST_COOLDOWN = 30 * 60  # 30 минут в секундах

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ХРАНИЛИЩА ===
album_buffer = {}
last_post_time = {}
active_album_tasks = set()

# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! 👋\n\n"
        "Отправляй фото, видео, текст или альбомы — всё попадёт в канал.\n"
        "⚠️ Лимит для пользователей: 1 пост в 30 минут.\n\n"
        "💡 Совет: используй символы (█, ▓, │, ─) вместо эмодзи для цветных баров — так они не превратятся в реакции."
    )
    await update.message.reply_text(text)


async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_ADMIN_ID:
        await update.message.reply_text("❌ Только админ может использовать эту команду.")
        return

    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [[InlineKeyboardButton("ПОСТ", url="https://t.me/CHA2M_bot")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        sent = await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text="📩 Хочешь отправить пост в канал? Жми кнопку ниже!",
            reply_markup=reply_markup
        )
        await update.message.reply_text(
            f"✅ Сообщение с кнопкой отправлено в канал!\n"
            f"Закрепи его в канале (ID: {sent.message_id})."
        )
    except Exception as e:
        logger.error(f"Ошибка /pin: {e}")
        await update.message.reply_text("❌ Не удалось отправить пост в канал.")


# === ОСНОВНОЙ ОБРАБОТЧИК ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.effective_message:
        return

    user_id = user.id
    message = update.effective_message
    current_time = time.time()
    is_admin = (user_id == YOUR_ADMIN_ID)

    try:
        # === АЛЬБОМ ===
        if message.media_group_id:
            group_id = message.media_group_id

            if not is_admin and group_id not in album_buffer:
                if user_id in last_post_time:
                    elapsed = current_time - last_post_time[user_id]
                    if elapsed < POST_COOLDOWN:
                        remaining = max(1, int((POST_COOLDOWN - elapsed) // 60))
                        await update.message.reply_text(
                            f"⏳ Подожди ещё {remaining} мин. Лимит: 1 пост в 30 минут."
                        )
                        return
                last_post_time[user_id] = current_time

            if group_id not in album_buffer:
                album_buffer[group_id] = []
            album_buffer[group_id].append(message)

            if group_id not in active_album_tasks:
                active_album_tasks.add(group_id)
                asyncio.create_task(
                    send_album_later_with_notification(group_id, context, message)
                )

        # === ОДИНОЧНОЕ СООБЩЕНИЕ ===
        else:
            if not is_admin:
                if user_id in last_post_time:
                    elapsed = current_time - last_post_time[user_id]
                    if elapsed < POST_COOLDOWN:
                        remaining = max(1, int((POST_COOLDOWN - elapsed) // 60))
                        await update.message.reply_text(
                            f"⏳ Подожди ещё {remaining} мин. Лимит: 1 пост в 30 минут."
                        )
                        return
                last_post_time[user_id] = current_time

            # Отправляем как НОВОЕ сообщение, а не forward — чтобы не было "от кого"
            try:
                if message.text is not None:
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=message.text,
                        parse_mode=None  # Сохраняет всё как есть: эмодзи, символы, пробелы
                    )
                elif message.photo:
                    await context.bot.send_photo(
                        chat_id=CHANNEL_ID,
                        photo=message.photo[-1].file_id,
                        caption=message.caption
                    )
                elif message.video:
                    await context.bot.send_video(
                        chat_id=CHANNEL_ID,
                        video=message.video.file_id,
                        caption=message.caption
                    )
                elif message.document:
                    await context.bot.send_document(
                        chat_id=CHANNEL_ID,
                        document=message.document.file_id,
                        caption=message.caption
                    )
                elif message.sticker:
                    await context.bot.send_sticker(
                        chat_id=CHANNEL_ID,
                        sticker=message.sticker.file_id
                    )
                else:
                    # fallback: если тип не поддерживается
                    await context.bot.forward_message(
                        chat_id=CHANNEL_ID,
                        from_chat_id=update.effective_chat.id,
                        message_id=message.message_id
                    )

                await update.message.reply_text("✅ Пост отправлен в канал!")

            except Exception as e:
                logger.error(f"Ошибка отправки одиночного сообщения: {e}")
                await update.message.reply_text("❌ Не удалось отправить пост.")

    except Exception as e:
        logger.error(f"Ошибка handle_message от user={user_id}: {e}")
        try:
            await update.message.reply_text("❌ Не удалось обработать пост.")
        except:
            pass


# === ОТПРАВКА АЛЬБОМА ===
async def send_album_later_with_notification(group_id: str, context: ContextTypes.DEFAULT_TYPE, first_msg):
    await asyncio.sleep(1.3)

    if group_id not in album_buffer:
        active_album_tasks.discard(group_id)
        return

    messages = album_buffer.pop(group_id)
    active_album_tasks.discard(group_id)

    if not messages:
        return

    media = []
    for msg in messages:
        if msg.photo:
            file_id = msg.photo[-1].file_id
            media.append(InputMediaPhoto(media=file_id, caption=msg.caption))
        elif msg.video:
            media.append(InputMediaVideo(media=msg.video.file_id, caption=msg.caption))

    if not media:
        try:
            await messages[-1].reply_text("❌ Альбом не содержит поддерживаемых медиафайлов.")
        except:
            pass
        return

    try:
        await context.bot.send_media_group(chat_id=CHANNEL_ID, media=media)
        await messages[-1].reply_text("✅ Альбом отправлен в канал!")
    except Exception as e:
        logger.error(f"Ошибка отправки альбома {group_id}: {e}")
        try:
            await messages[-1].reply_text("❌ Не удалось отправить альбом. Файлы могут быть слишком большими.")
        except:
            pass


# === ЗАПУСК ===
def main():
    logger.info("🚀 Запуск бота...")
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pin", pin))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    logger.info("✅ Бот запущен: админ без лимита, пользователи — 1 пост/30 мин, альбомы, /pin")
    application.run_polling()


if __name__ == '__main__':
    main()
