import os
import re
import sqlite3
import asyncio
import time

from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# =========================================================
# CONFIG
# =========================================================

DB_FILE = "warnings.db"

# Your Telegram User ID
ADMIN_ID = 8504230656

# Anti-spam settings
SPAM_LIMIT = 5
SPAM_WINDOW = 8
MUTE_TIME = 60

user_messages = {}


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_db()
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            antilink INTEGER NOT NULL DEFAULT 0,
            antispam INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def save_user(user_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,)
    )

    conn.commit()
    conn.close()


def get_all_users():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]

    conn.close()
    return users


# =========================================================
# WARNING SYSTEM
# =========================================================

def get_warnings(chat_id, user_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT count
        FROM warnings
        WHERE chat_id = ? AND user_id = ?
        """,
        (chat_id, user_id)
    )

    result = cursor.fetchone()

    conn.close()

    return result[0] if result else 0


def add_warning(chat_id, user_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO warnings (chat_id, user_id, count)
        VALUES (?, ?, 1)

        ON CONFLICT(chat_id, user_id)
        DO UPDATE SET count = count + 1
        """,
        (chat_id, user_id)
    )

    conn.commit()

    cursor.execute(
        """
        SELECT count
        FROM warnings
        WHERE chat_id = ? AND user_id = ?
        """,
        (chat_id, user_id)
    )

    count = cursor.fetchone()[0]

    conn.close()

    return count


def reset_warnings(chat_id, user_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM warnings
        WHERE chat_id = ? AND user_id = ?
        """,
        (chat_id, user_id)
    )

    conn.commit()
    conn.close()


# =========================================================
# SETTINGS
# =========================================================

def set_antilink(chat_id, status):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO settings (chat_id, antilink, antispam)
        VALUES (?, ?, 0)

        ON CONFLICT(chat_id)
        DO UPDATE SET antilink = excluded.antilink
        """,
        (chat_id, status)
    )

    conn.commit()
    conn.close()


def get_antilink(chat_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT antilink
        FROM settings
        WHERE chat_id = ?
        """,
        (chat_id,)
    )

    result = cursor.fetchone()

    conn.close()

    return result[0] if result else 0


def set_antispam(chat_id, status):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO settings (chat_id, antilink, antispam)
        VALUES (?, 0, ?)

        ON CONFLICT(chat_id)
        DO UPDATE SET antispam = excluded.antispam
        """,
        (chat_id, status)
    )

    conn.commit()
    conn.close()


def get_antispam(chat_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT antispam
        FROM settings
        WHERE chat_id = ?
        """,
        (chat_id,)
    )

    result = cursor.fetchone()

    conn.close()

    return result[0] if result else 0


# =========================================================
# ADMIN CHECK
# =========================================================

async def is_admin(update: Update):
    if not update.effective_chat:
        return False

    if update.effective_chat.type == "private":
        return False

    if not update.effective_user:
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


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user.id)

    await update.message.reply_text(
        "𝐓𝐡𝐞 𝐨𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐗𝐄𝐑𝐗𝐄𝐒 𝐛𝐨𝐭 — 𝐛𝐫𝐢𝐧𝐠𝐢𝐧𝐠 "
        "𝐆𝐚𝐦𝐢𝐧𝐠, 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭 & 𝐌𝐮𝐬𝐢𝐜 𝐭𝐨𝐠𝐞𝐭𝐡𝐞𝐫 𝐰𝐢𝐭𝐡 "
        "𝐩𝐨𝐰𝐞𝐫𝐟𝐮𝐥 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬, 𝐬𝐦𝐨𝐨𝐭𝐡 𝐭𝐨𝐨𝐥𝐬, 𝐚𝐧𝐝 𝐚 "
        "𝐛𝐞𝐭𝐭𝐞𝐫 𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐞𝐱𝐩𝐞𝐫𝐢𝐞𝐧𝐜𝐞.\n\n"
        "𝐌𝐨𝐫𝐞 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐜𝐨𝐦𝐢𝐧𝐠 𝐬𝐨𝐨𝐧. . .\n"
        "✆ 𝐀𝐮𝐭𝐡𝐨𝐫𝐢𝐭𝐲 𝐬𝐮𝐩𝐩𝐨𝐫𝐭: @XERXES_XENO 🜲"
    )


# =========================================================
# ID
# =========================================================

async def user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user.id)

    await update.message.reply_text(
        "🆔 𝐘𝐨𝐮𝐫 𝐔𝐬𝐞𝐫 𝐈𝐃:\n\n"
        f"`{update.effective_user.id}`",
        parse_mode="Markdown"
    )


# =========================================================
# HELP
# =========================================================

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
        "• /resetwarns — Reset warnings\n"
        "• /antilink on — Enable Anti-Link\n"
        "• /antilink off — Disable Anti-Link\n"
        "• /antispam on — Enable Anti-Spam\n"
        "• /antispam off — Disable Anti-Spam\n\n"

        "𝐔𝐭𝐢𝐥𝐢𝐭𝐢𝐞𝐬\n"
        "• /id — Get ID\n"
        "• /broadcast — Admin broadcast\n\n"

        "⚙️ 𝐌𝐨𝐫𝐞 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐜𝐨𝐦𝐢𝐧𝐠 𝐬𝐨𝐨𝐧..."
    )


# =========================================================
# BAN
# =========================================================

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

    except Exception as error:
        print("Ban error:", error)

        await update.message.reply_text(
            "❌ I couldn't ban this user."
        )


# =========================================================
# UNBAN
# =========================================================

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

    except Exception as error:
        print("Unban error:", error)

        await update.message.reply_text(
            "❌ I couldn't unban this user."
        )


# =========================================================
# KICK
# =========================================================

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

    except Exception as error:
        print("Kick error:", error)

        await update.message.reply_text(
            "❌ I couldn't kick this user."
        )


# =========================================================
# MUTE
# =========================================================

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
            permissions=ChatPermissions(
                can_send_messages=False
            )
        )

        await update.message.reply_text(
            f"🔇 𝐔𝐬𝐞𝐫 {member.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐦𝐮𝐭𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception as error:
        print("Mute error:", error)

        await update.message.reply_text(
            "❌ I couldn't mute this user."
        )


# =========================================================
# UNMUTE
# =========================================================

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
            permissions=ChatPermissions(
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

    except Exception as error:
        print("Unmute error:", error)

        await update.message.reply_text(
            "❌ I couldn't unmute this user."
        )


# =========================================================
# WARN
# =========================================================

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /warn."
        )
        return

    member = update.message.reply_to_message.from_user

    count = add_warning(
        update.effective_chat.id,
        member.id
    )

    await update.message.reply_text(
        f"⚠️ 𝐖𝐚𝐫𝐧𝐢𝐧𝐠 𝐢𝐬𝐬𝐮𝐞𝐝 𝐭𝐨 {member.mention_html()}.\n\n"
        f"𝐖𝐚𝐫𝐧𝐢𝐧𝐠𝐬: {count}",
        parse_mode="HTML"
    )


# =========================================================
# WARNINGS
# =========================================================

async def warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /warnings."
        )
        return

    member = update.message.reply_to_message.from_user

    count = get_warnings(
        update.effective_chat.id,
        member.id
    )

    await update.message.reply_text(
        f"⚠️ {member.mention_html()} has {count} warning(s).",
        parse_mode="HTML"
    )


# =========================================================
# RESET WARNINGS
# =========================================================

async def resetwarns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to the member's message and use /resetwarns."
        )
        return

    member = update.message.reply_to_message.from_user

    reset_warnings(
        update.effective_chat.id,
        member.id
    )

    await update.message.reply_text(
        f"✅ 𝐖𝐚𝐫𝐧𝐢𝐧𝐠𝐬 𝐫𝐞𝐬𝐞𝐭 𝐟𝐨𝐫 {member.mention_html()}.",
        parse_mode="HTML"
    )


# =========================================================
# ANTI-LINK
# =========================================================

async def antilink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    chat_id = update.effective_chat.id

    if not context.args:
        status = get_antilink(chat_id)

        await update.message.reply_text(
            "🔗 𝐀𝐧𝐭𝐢-𝐋𝐢𝐧𝐤: "
            + ("𝐎𝐍" if status else "𝐎𝐅𝐅")
        )
        return

    option = context.args[0].lower()

    if option == "on":
        set_antilink(chat_id, 1)

        await update.message.reply_text(
            "🛡️ 𝐀𝐧𝐭𝐢-𝐋𝐢𝐧𝐤 𝐞𝐧𝐚𝐛𝐥𝐞𝐝."
        )

    elif option == "off":
        set_antilink(chat_id, 0)

        await update.message.reply_text(
            "🔓 𝐀𝐧𝐭𝐢-𝐋𝐢𝐧𝐤 𝐝𝐢𝐬𝐚𝐛𝐥𝐞𝐝."
        )

    else:
        await update.message.reply_text(
            "⚠️ 𝐔𝐬𝐚𝐠𝐞:\n"
            "/antilink on\n"
            "/antilink off"
        )


# =========================================================
# ANTI-SPAM
# =========================================================

async def antispam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    chat_id = update.effective_chat.id

    if not context.args:
        status = get_antispam(chat_id)

        await update.message.reply_text(
            "🛡️ 𝐀𝐧𝐭𝐢-𝐒𝐩𝐚𝐦: "
            + ("𝐎𝐍" if status else "𝐎𝐅𝐅")
        )
        return

    option = context.args[0].lower()

    if option == "on":
        set_antispam(chat_id, 1)

        await update.message.reply_text(
            "🛡️ 𝐀𝐧𝐭𝐢-𝐒𝐩𝐚𝐦 𝐞𝐧𝐚𝐛𝐥𝐞𝐝."
        )

    elif option == "off":
        set_antispam(chat_id, 0)

        await update.message.reply_text(
            "🔓 𝐀𝐧𝐭𝐢-𝐒𝐩𝐚𝐦 𝐝𝐢𝐬𝐚𝐛𝐥𝐞𝐝."
        )

    else:
        await update.message.reply_text(
            "⚠️ 𝐔𝐬𝐚𝐠𝐞:\n"
            "/antispam on\n"
            "/antispam off"
        )


# =========================================================
# MODERATION HANDLER
# =========================================================

async def moderation_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    if not update.effective_chat:
        return

    if update.effective_chat.type == "private":
        return

    user = update.effective_user

    if not user:
        return

    save_user(user.id)

    # Admins are exempt
    try:
        member = await update.effective_chat.get_member(user.id)

        if member.status in ("administrator", "creator"):
            return

    except Exception:
        return

    text = update.message.text or update.message.caption or ""

    # -----------------------------------------------------
    # ANTI-LINK
    # -----------------------------------------------------

    if get_antilink(update.effective_chat.id):

        link_pattern = r"(https?://|www\.|t\.me/|telegram\.me/)"

        if re.search(link_pattern, text, re.IGNORECASE):

            try:
                await update.message.delete()

                count = add_warning(
                    update.effective_chat.id,
                    user.id
                )

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        "🔗 𝐋𝐢𝐧𝐤 𝐫𝐞𝐦𝐨𝐯𝐞𝐝.\n"
                        f"⚠️ {user.mention_html()} — "
                        f"𝐖𝐚𝐫𝐧𝐢𝐧𝐠: {count}"
                    ),
                    parse_mode="HTML"
                )

            except Exception as error:
                print("Anti-link error:", error)

            return

    # -----------------------------------------------------
    # ANTI-SPAM
    # -----------------------------------------------------

    if get_antispam(update.effective_chat.id):

        now = time.time()

        key = (
            update.effective_chat.id,
            user.id
        )

        if key not in user_messages:
            user_messages[key] = []

        user_messages[key].append(now)

        user_messages[key] = [
            timestamp
            for timestamp in user_messages[key]
            if now - timestamp <= SPAM_WINDOW
        ]

        if len(user_messages[key]) >= SPAM_LIMIT:

            user_messages[key] = []

            try:
                await update.message.delete()

                count = add_warning(
                    update.effective_chat.id,
                    user.id
                )

                await context.bot.restrict_chat_member(
                    chat_id=update.effective_chat.id,
                    user_id=user.id,
                    permissions=ChatPermissions(
                        can_send_messages=False
                    ),
                    until_date=int(now + MUTE_TIME)
                )

                await 
