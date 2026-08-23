import os
import sqlite3
import asyncio

from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, ContextTypes


DB_FILE = "warnings.db"
ADMIN_ID = 8504230656


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)

    conn.commit()
    conn.close()


def save_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,)
    )

    conn.commit()
    conn.close()


def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]

    conn.close()

    return users


def get_warnings(chat_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT count FROM warnings WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    )

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else 0


def add_warning(chat_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO warnings (chat_id, user_id, count)
        VALUES (?, ?, 1)
        ON CONFLICT(chat_id, user_id)
        DO UPDATE SET count = count + 1
    """, (chat_id, user_id))

    conn.commit()

    cursor.execute(
        "SELECT count FROM warnings WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    )

    count = cursor.fetchone()[0]

    conn.close()

    return count


def reset_warnings(chat_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    )

    conn.commit()
    conn.close()


async def is_admin(update: Update):
    if not update.effective_chat or update.effective_chat.type == "private":
        return False

    try:
        member = await update.effective_chat.get_member(
            update.effective_user.id
        )

        return member.status in ("administrator", "creator")

    except Exception:
        return False


async def admin_only(update: Update):
    if not await is_admin(update):
        await update.message.reply_text(
            "❌ 𝐀𝐝𝐦𝐢𝐧𝐬 𝐨𝐧𝐥𝐲.\n"
            "𝐘𝐨𝐮 𝐝𝐨 𝐧𝐨𝐭 𝐡𝐚𝐯𝐞 𝐩𝐞𝐫𝐦𝐢𝐬𝐬𝐢𝐨𝐧 𝐭𝐨 𝐮𝐬𝐞 𝐭𝐡𝐢𝐬 𝐜𝐨𝐦𝐦𝐚𝐧𝐝."
        )
        return False

    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user.id)

    await update.message.reply_text(
        "𝐓𝐡𝐞 𝐨𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐗𝐄𝐑𝐗𝐄𝐒 𝐛𝐨𝐭 — 𝐛𝐫𝐢𝐧𝐠𝐢𝐧𝐠 𝐆𝐚𝐦𝐢𝐧𝐠, 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭 & 𝐌𝐮𝐬𝐢𝐜 𝐭𝐨𝐠𝐞𝐭𝐡𝐞𝐫 𝐰𝐢𝐭𝐡 𝐩𝐨𝐰𝐞𝐫𝐟𝐮𝐥 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬, 𝐬𝐦𝐨𝐨𝐭𝐡 𝐭𝐨𝐨𝐥𝐬, 𝐚𝐧𝐝 𝐚 𝐛𝐞𝐭𝐭𝐞𝐫 𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐞𝐱𝐩𝐞𝐫𝐢𝐞𝐧𝐜𝐞.\n\n"
        "𝐌𝐨𝐫𝐞 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐜𝐨𝐦𝐢𝐧𝐠 𝐬𝐨𝐨𝐧. . .\n"
        "✆ 𝐀𝐮𝐭𝐡𝐨𝐫𝐢𝐭𝐲 𝐬𝐮𝐩𝐩𝐨𝐫𝐭: @XERXES_XENO 🜲"
    )


async def user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user.id)

    await update.message.reply_text(
        f"🆔 𝐘𝐨𝐮𝐫 𝐔𝐬𝐞𝐫 𝐈𝐃:\n\n"
        f"`{update.effective_user.id}`",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user.id)

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
        "• /broadcast — Admin broadcast\n\n"
        "⚙️ 𝐌𝐨𝐫𝐞 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐜𝐨𝐦𝐢𝐧𝐠 𝐬𝐨𝐨𝐧..."
    )


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

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
            "❌ I couldn't ban this user."
        )


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

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
    if not await admin_only(update):
        return

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
            "❌ I couldn't kick this user."
        )


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /mute."
        )
        return

    member = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.restrict_member(
            member.id,
            ChatPermissions(can_send_messages=False)
        )

        await update.message.reply_text(
            f"🔇 𝐔𝐬𝐞𝐫 {member.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐦𝐮𝐭𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception:
        await update.message.reply_text(
            "❌ I couldn't mute this user."
        )


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /unmute."
        )
        return

    member = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.restrict_member(
            member.id,
            ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )

        await update.message.reply_text(
            f"🔊 𝐔𝐬𝐞𝐫 {member.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐮𝐧𝐦𝐮𝐭𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception:
        await update.message.reply_text(
            "❌ I couldn't unmute this user."
        )


async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /warn."
        )
        return

    member = update.message.reply_to_message.from_user
    count = add_warning(update.effective_chat.id, member.id)

    await update.message.reply_text(
        f"⚠️ 𝐖𝐚𝐫𝐧𝐢𝐧𝐠 𝐢𝐬𝐬𝐮𝐞𝐝 𝐭𝐨 {member.mention_html()}.\n\n"
        f"𝐖𝐚𝐫𝐧𝐢𝐧𝐠𝐬: {count}",
        parse_mode="HTML"
    )


async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /warnings."
        )
        return

    member = update.message.reply_to_message.from_user
    count = get_warnings(update.effective_chat.id, member.id)

    await update.message.reply_text(
        f"⚠️ {member.mention_html()} has {count} warning(s).",
        parse_mode="HTML"
    )


async def resetwarns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /resetwarns."
        )
        return

    member = update.message.reply_to_message.from_user

    reset_warnings(update.effective_chat.id, member.id)

    await update.message.reply_text(
        f"✅ 𝐖𝐚𝐫𝐧𝐢𝐧𝐠𝐬 𝐫𝐞𝐬𝐞𝐭 𝐟𝐨𝐫 {member.mention_html()}.",
        parse_mode="HTML"
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐭 𝐚𝐮𝐭𝐡𝐨𝐫𝐢𝐳𝐞𝐝 𝐭𝐨 𝐮𝐬𝐞 𝐭𝐡𝐢𝐬 𝐜𝐨𝐦𝐦𝐚𝐧𝐝."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ 𝐔𝐬𝐚𝐠𝐞:\n/broadcast Your message here"
        )
        return

    message = " ".join(context.args)
    users = get_all_users()

    sent = 0
    failed = 0

    await update.message.reply_text(
        f"📢 𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭 𝐬𝐭𝐚𝐫𝐭𝐞𝐝...\n"
        f"👥 𝐑𝐞𝐠𝐢𝐬𝐭𝐞𝐫𝐞𝐝 𝐮𝐬𝐞𝐫𝐬: {len(users)}"
    )

    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message
            )

            sent += 1
            await asyncio.sleep(0.05)

        except Exception:
            failed += 1

    await update.message.reply_text(
        f"📊 𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭 𝐜𝐨𝐦𝐩𝐥𝐞𝐭𝐞𝐝.\n\n"
        f"✅ 𝐒𝐞𝐧𝐭: {sent}\n"
        f"❌ 𝐅𝐚𝐢𝐥𝐞𝐝: {failed}"
    )


init_db()

app = Application.builder().token(
    os.environ["TELEGRAM_BOT_TOKEN"]
).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("id", user_id))
app.add_handler(CommandHandler("help", help_command))

app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CommandHandler("kick", kick))
app.add_handler(CommandHandler("mute", mute))
app.add_handler(CommandHandler("unmute", unmute))

app.add_handler(CommandHandler("warn", warn))
app.add_handler(CommandHandler("warnings", warnings))
app.add_handler(CommandHandler("resetwarns", resetwarns))

app.add_handler(CommandHandler("broadcast", broadcast))

print("XERXES BOT started...")
app.run_polling()
