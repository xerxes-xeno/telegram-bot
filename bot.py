import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "𝐓𝐡𝐞 𝐨𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐗𝐄𝐑𝐗𝐄𝐒 𝐛𝐨𝐭 — 𝐛𝐫𝐢𝐧𝐠𝐢𝐧𝐠 𝐆𝐚𝐦𝐢𝐧𝐠, 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭 & 𝐌𝐮𝐬𝐢𝐜 𝐭𝐨𝐠𝐞𝐭𝐡𝐞𝐫 𝐰𝐢𝐭𝐡 𝐩𝐨𝐰𝐞𝐫𝐟𝐮𝐥 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬, 𝐬𝐦𝐨𝐨𝐭𝐡 𝐭𝐨𝐨𝐥𝐬, 𝐚𝐧𝐝 𝐚 𝐛𝐞𝐭𝐭𝐞𝐫 𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐞𝐱𝐩𝐞𝐫𝐢𝐞𝐧𝐜𝐞.\n\n"
        "𝐌𝐨𝐫𝐞 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐜𝐨𝐦𝐢𝐧𝐠 𝐬𝐨𝐨𝐧. . .\n"
        "✆ 𝐀𝐮𝐭𝐡𝐨𝐫𝐢𝐭𝐲 𝐬𝐮𝐩𝐩𝐨𝐫𝐭: @XERXES_XENO 🜲"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ 𝐗𝐄𝐑𝐗𝐄𝐒 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓\n\n"
        "𝐌𝐨𝐝𝐞𝐫𝐚𝐭𝐢𝐨𝐧\n"
        "• /ban — Ban a member\n"
        "• /unban — Unban a member\n"
        "• /kick — Remove a member\n"
        "• /mute — Mute a member\n"
        "• /unmute — Unmute a member\n\n"
        "𝐒𝐚𝐟𝐞𝐭𝐲\n"
        "• /warn — Warn a member\n"
        "• /warnings — Check warnings\n"
        "• /resetwarns — Reset warnings\n\n"
        "𝐔𝐭𝐢𝐥𝐢𝐭𝐢𝐞𝐬\n"
        "• /id — Get ID\n"
        "• /info — User information\n"
        "• /purge — Delete messages\n\n"
        "⚙️ 𝐌𝐨𝐫𝐞 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐜𝐨𝐦𝐢𝐧𝐠 𝐬𝐨𝐨𝐧..."
    )


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /ban."
        )
        return

    member = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.ban_member(member.id)

        await update.message.reply_text(
            f"🔨 𝐔𝐬𝐞𝐫 {member.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐛𝐚𝐧𝐧𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception:
        await update.message.reply_text(
            "❌ I couldn't ban this user.\n"
            "Make sure I have admin permission."
        )


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /unban."
        )
        return

    member = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.unban_member(
            member.id,
            only_if_banned=True
        )

        await update.message.reply_text(
            f"✅ 𝐔𝐬𝐞𝐫 {member.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐮𝐧𝐛𝐚𝐧𝐧𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception:
        await update.message.reply_text(
            "❌ I couldn't unban this user."
        )


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /kick."
        )
        return

    member = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.ban_member(member.id)
        await update.effective_chat.unban_member(member.id)

        await update.message.reply_text(
            f"👢 𝐔𝐬𝐞𝐫 {member.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐤𝐢𝐜𝐤𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception:
        await update.message.reply_text(
            "❌ I couldn't kick this user.\n"
            "Make sure I have admin permission."
        )


app = Application.builder().token(
    os.environ["TELEGRAM_BOT_TOKEN"]
).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CommandHandler("kick", kick))

print("XERXES BOT started...")
app.run_polling()
