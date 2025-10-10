import logging
import asyncio
import time
import pytz
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.triggers.cron import CronTrigger

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = "7723918807:AAFPfwLnRFi1-4jGfeNk4j6AVaKZ9mauw6I"
CHANNEL_ID = -1003154844765
YOUR_ADMIN_ID = 5610556402
POST_COOLDOWN = 10 * 60  # 10 минут

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

# === ИМПОРТ ГЕНЕРАТОРА ТЕМ ===
from theme_generator import generate_weekly_theme, get_current_theme


# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! 👋\n\n"
        "Отправляй фото, видео, текст или альбомы — всё попадёт в канал.\n"
        f"⚠️ Лимит для пользователей: 1 пост в {POST_COOLDOWN // 60} минут."
    )
    await update.message.reply_text(text)


async def theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theme_word = get_current_theme()
    if theme_word:
        await update.message.reply_text(f"📌 Текущая тема: «{theme_word}»")
    else:
        await update.message.reply_text("❌ Тема ещё не установлена. Следующая — в воскресенье!")


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


# === ФОН: публикация темы каждое воскресенье в 00:00 МСК ===
async def weekly_theme_job(context: ContextTypes.DEFAULT_TYPE):
    new_theme = await generate_weekly_theme()
    if new_theme:
        try:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"🗓 **Тема недели: «{new_theme}»**\n\n"
                     f"Присылайте посты, вдохновлённые этим словом.\n"
                     f"Лучшие — закрепим!",
                parse_mode="Markdown"
            )
            logger.info(f"Опубликована новая тема: {new_theme}")
        except Exception as e:
            logger.error(f"Не удалось опубликовать тему: {e}")


# === ОСНОВНОЙ ОБРАБОТЧИК ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.effective_message:
        logger.warning("Пропущено сообщение: отсутствует пользователь или сообщение")
        return

    user_id = user.id
    message = update.effective_message
    current_time = time.time()
    is_admin = (user_id == YOUR_ADMIN_ID)

    logger.info(
        f"📨 Получено сообщение от user={user_id} (admin={is_admin}), "
        f"media_group_id={message.media_group_id}, "
        f"has_photo={bool(message.photo)}, "
        f"has_video={bool(message.video)}, "
        f"has_document={bool(message.document)}"
    )

    # Проверка кулдауна
    if not is_admin:
        if user_id in last_post_time:
            elapsed = current_time - last_post_time[user_id]
            if elapsed < POST_COOLDOWN:
                remaining = max(1, int((POST_COOLDOWN - elapsed) // 60))
                logger.info(f"🕒 Пользователь {user_id} превысил лимит. Осталось ждать: {remaining} мин.")
                await update.message.reply_text(
                    f"⏳ Подожди ещё {remaining} мин. Лимит: 1 пост в {POST_COOLDOWN // 60} минут."
                )
                return
        last_post_time[user_id] = current_time

    try:
        # === АЛЬБОМ ===
        if message.media_group_id:
            group_id = message.media_group_id
            logger.info(f"🖼️ Обнаружен альбом: media_group_id={group_id}")
            if group_id not in album_buffer:
                album_buffer[group_id] = []
            album_buffer[group_id].append(message)

            if group_id not in active_album_tasks:
                active_album_tasks.add(group_id)
                logger.info(f"⏱️ Запланирована отложенная отправка альбома {group_id}")
                asyncio.create_task(
                    send_album_later_with_notification(group_id, context, message)
                )
            return

        # === ОДИНОЧНОЕ СООБЩЕНИЕ ===
        else:
            logger.info(f"📤 Обработка одиночного сообщения от user={user_id}")
            sent = False
            try:
                if message.text is not None:
                    await context.bot.send_message(chat_id=CHANNEL_ID, text=message.text)
                    sent = True
                elif message.photo:
                    await context.bot.send_photo(
                        chat_id=CHANNEL_ID,
                        photo=message.photo[-1].file_id,
                        caption=message.caption
                    )
                    sent = True
                elif message.video:
                    await context.bot.send_video(
                        chat_id=CHANNEL_ID,
                        video=message.video.file_id,
                        caption=message.caption
                    )
                    sent = True
                elif message.document:
                    await context.bot.send_document(
                        chat_id=CHANNEL_ID,
                        document=message.document.file_id,
                        caption=message.caption
                    )
                    sent = True
                elif message.sticker:
                    await context.bot.send_sticker(
                        chat_id=CHANNEL_ID,
                        sticker=message.sticker.file_id
                    )
                    sent = True
                else:
                    await context.bot.forward_message(
                        chat_id=CHANNEL_ID,
                        from_chat_id=update.effective_chat.id,
                        message_id=message.message_id
                    )
                    sent = True

                if sent:
                    theme_word = get_current_theme()
                    reply_text = f"✅ Пост отправлен!\nТекущая тема: «{theme_word}» — как ты его понял?" if theme_word else "✅ Пост отправлен в канал!"
                    await update.message.reply_text(reply_text)
                    logger.info(f"✅ Успешно отправлено в канал: user={user_id}")

            except Exception as e:
                logger.error(f"❌ Ошибка при отправке одиночного сообщения от user={user_id}: {e}", exc_info=True)
                try:
                    await update.message.reply_text("❌ Не удалось отправить пост. Возможно, файл слишком большой.")
                except:
                    pass

    except Exception as e:
        logger.critical(f"💥 Критическая ошибка в handle_message от user={user_id}: {e}", exc_info=True)
        try:
            await update.message.reply_text("❌ Произошла внутренняя ошибка. Админ уже чинит!")
        except:
            pass


# === ОТПРАВКА АЛЬБОМА ===
async def send_album_later_with_notification(group_id: str, context: ContextTypes.DEFAULT_TYPE, first_msg):
    await asyncio.sleep(2.5)

    if group_id not in album_buffer:
        active_album_tasks.discard(group_id)
        return

    messages = album_buffer.pop(group_id)
    active_album_tasks.discard(group_id)

    if not messages:
        return

    # === ВАЖНО: подпись (caption) только у ПЕРВОГО элемента! ===
    media = []
    for i, msg in enumerate(messages):
        caption = msg.caption if i == 0 else None
        if msg.photo:
            media.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=caption))
        elif msg.video:
            media.append(InputMediaVideo(media=msg.video.file_id, caption=caption))
        else:
            logger.warning(f"Пропущен неподдерживаемый тип медиа в альбоме: {msg}")

    logger.info(f"Собран альбом: {len(media)} медиа, из них с caption: {sum(1 for m in media if m.caption)}")

    if not media:
        try:
            await messages[-1].reply_text("❌ Альбом не содержит поддерживаемых медиафайлов (только фото/видео).")
        except:
            pass
        return

    try:
        logger.info(f"📤 Отправка альбома из {len(media)} элементов в канал")
        await context.bot.send_media_group(chat_id=CHANNEL_ID, media=media)
        theme_word = get_current_theme()
        reply_text = f"✅ Альбом отправлен в канал!\nТекущая тема: «{theme_word}»" if theme_word else "✅ Альбом отправлен в канал!"
        await messages[-1].reply_text(reply_text)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки альбома {group_id}: {e}", exc_info=True)
        try:
            await messages[-1].reply_text("❌ Не удалось отправить альбом. Возможно, файлы слишком большие или недопустимый формат.")
        except:
            pass


# === ЗАПУСК ===
def main():
    logger.info("🚀 Запуск бота...")
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("theme", theme))
    application.add_handler(CommandHandler("pin", pin))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    # Еженедельная тема: воскресенье 00:00 МСК = суббота 21:00 UTC
    trigger = CronTrigger(
        day_of_week=5,   # суббота в UTC
        hour=21,
        minute=0,
        timezone=pytz.utc
    )
    application.job_queue.run_custom(weekly_theme_job, job_kwargs={"trigger": trigger})

    logger.info("✅ Бот запущен. Ожидание сообщений...")
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
