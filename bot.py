import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 XERXES BOT is online!\n\n"
        "🛡️ Management • 🎵 Music • 🎮 Gaming\n"
        "More features coming soon..."
    )


app = Application.builder().token(
    os.environ["TELEGRAM_BOT_TOKEN"]
).build()

app.add_handler(CommandHandler("start", start))

print("XERXES BOT started...")
app.run_polling()
