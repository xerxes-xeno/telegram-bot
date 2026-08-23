import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "𝐓𝐡𝐞 𝐨𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐗𝐄𝐑𝐗𝐄𝐒 𝐛𝐨𝐭 — 𝐛𝐫𝐢𝐧𝐠𝐢𝐧𝐠 𝐆𝐚𝐦𝐢𝐧𝐠, 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭 & 𝐌𝐮𝐬𝐢𝐜 𝐭𝐨𝐠𝐞𝐭𝐡𝐞𝐫 𝐰𝐢𝐭𝐡 𝐩𝐨𝐰𝐞𝐫𝐟𝐮𝐥 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬, 𝐬𝐦𝐨𝐨𝐭𝐡 𝐭𝐨𝐨𝐥𝐬, 𝐚𝐧𝐝 𝐚 𝐛𝐞𝐭𝐭𝐞𝐫 𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐞𝐱𝐩𝐞𝐫𝐢𝐞𝐧𝐜𝐞.\n\n"
        "𝐌𝐨𝐫𝐞 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐜𝐨𝐦𝐢𝐧𝐠 𝐬𝐨𝐨𝐧. . .\n"
        "✆ 𝐀𝐮𝐭𝐡𝐨𝐫𝐢𝐭𝐲 𝐬𝐮𝐩𝐩𝐨𝐫𝐭: @XERXES_XENO 🜲"
    )

app = Application.builder().token(
    os.environ["TELEGRAM_BOT_TOKEN"]
).build()

app.add_handler(CommandHandler("start", start))

print("XERXES BOT started...")
app.run_polling()
