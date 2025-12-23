import os
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===== ТОКЕН =====
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден в переменных окружения")

# ===== КЛАВИАТУРА =====
keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🏡 О проекте")],
        [KeyboardButton("📜 История деревни Захожье")],

        [KeyboardButton("🗺 Карта 1792 года")],
        [KeyboardButton("🗺 План деревни 1885 г.")],
        [KeyboardButton("🗺 План деревни 1941 г.")],
        [KeyboardButton("🗺 Карта — настоящее время")],
    ],
    resize_keyboard=True
)

# ===== /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здравствуйте! 👋\n\n"
        "Информационный бот инициативы восстановления деревни Захожье.\n\n"
        "Выберите раздел 👇",
        reply_markup=keyboard
    )

# ===== ТЕКСТОВЫЕ КНОПКИ =====
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🏡 О проекте":
        await update.message.reply_text(
            "🏡 **О проекте восстановления деревни Захожье**\n\n"
            "Цель проекта — восстановление официального статуса деревни, "
            "присвоение адресов, развитие инфраструктуры и сохранение "
            "исторического названия.",
            parse_mode="Markdown"
        )

    elif text == "📜 История деревни Захожье":
        await update.message.reply_text(
            "📜 **История деревни Захожье**\n\n"
            "Деревня известна с XVI века, упоминается в переписных книгах "
            "и присутствует на исторических картах Российской империи.",
            parse_mode="Markdown"
        )

    elif text == "🗺 Карта 1792 года":
        await send_map(update, "maps/map_1792.jpg",
                       "🗺 Карта Санкт-Петербургской губернии, 1792 год")

    elif text == "🗺 План деревни 1885 г.":
        await send_map(update, "maps/map_1885.jpg",
                       "🗺 План деревни Захожье, 1885 год")

    elif text == "🗺 План деревни 1941 г.":
        await send_map(update, "maps/map_1941.jpg",
                       "🗺 Карта местности, 1941 год")

    elif text == "🗺 Карта — настоящее время":
        await send_map(update, "maps/map_now.jpg",
                       "🗺 Современное состояние территории Захожья")

    else:
        await update.message.reply_text("Выберите пункт из меню 👇")

# ===== ОТПРАВКА КАРТ =====
async def send_map(update: Update, path: str, caption: str):
    if not os.path.exists(path):
        await update.message.reply_text("❌ Файл карты не найден")
        return

    with open(path, "rb") as f:
        await update.message.reply_photo(
            photo=InputFile(f),
            caption=caption
        )

# ===== ЗАПУСК =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("✅ Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    main()
