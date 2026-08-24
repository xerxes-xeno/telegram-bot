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

DB_FILE = "warnings.db"
ADMIN_ID = 8504230656

SPAM_LIMIT = 5
SPAM_WINDOW = 8
MUTE_TIME = 60

user_messages = {}


# =========================================================
# DATABASE
# =========================================================

def db():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            antilink INTEGER NOT NULL DEFAULT 0,
            antispam INTEGER NOT NULL DEFAULT 0
        )
    """)

    try:
        cur.execute("ALTER TABLE settings ADD COLUMN welcome TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def save_user(user_id):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,)
    )
    conn.commit()
    conn.close()


def get_all_users():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = [row[0] for row in cur.fetchall()]
    conn.close()
    return users


# =========================================================
# WARNINGS
# =========================================================

def get_warnings(chat_id, user_id):
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT count FROM warnings WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )

    result = cur.fetchone()
    conn.close()

    return result[0] if result else 0


def add_warning(chat_id, user_id):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO warnings (chat_id, user_id, count)
        VALUES (?, ?, 1)
        ON CONFLICT(chat_id, user_id)
        DO UPDATE SET count = count + 1
    """, (chat_id, user_id))

    conn.commit()

    cur.execute(
        "SELECT count FROM warnings WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )

    count = cur.fetchone()[0]
    conn.close()

    return count


def reset_warnings(chat_id, user_id):
    conn = db()
    conn.execute(
        "DELETE FROM warnings WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()


# =========================================================
# SETTINGS
# =========================================================

def set_antilink(chat_id, status):
    conn = db()

    conn.execute("""
        INSERT INTO settings (chat_id, antilink, antispam)
        VALUES (?, ?, 0)
        ON CONFLICT(chat_id)
        DO UPDATE SET antilink=excluded.antilink
    """, (chat_id, status))

    conn.commit()
    conn.close()


def get_antilink(chat_id):
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT antilink FROM settings WHERE chat_id=?",
        (chat_id,)
    )

    result = cur.fetchone()
    conn.close()

    return result[0] if result else 0


def set_antispam(chat_id, status):
    conn = db()

    conn.execute("""
        INSERT INTO settings (chat_id, antilink, antispam)
        VALUES (?, 0, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET antispam=excluded.antispam
    """, (chat_id, status))

    conn.commit()
    conn.close()


def get_antispam(chat_id):
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT antispam FROM settings WHERE chat_id=?",
        (chat_id,)
    )

    result = cur.fetchone()
    conn.close()

    return result[0] if result else 0


# =========================================================
# ADMIN CHECK
# =========================================================

async def is_admin(update):
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

    except Exception as e:
        print("Admin check error:", e)
        return False


async def admin_only(update):
    if not await is_admin(update):
        await update.message.reply_text(
            "❌ 𝐀𝐝𝐦𝐢𝐧𝐬 𝐨𝐧𝐥𝐲."
        )
        return False

    return True


# =========================================================
# START
# =========================================================

async def start(update, context):
    save_user(update.effective_user.id)

    await update.message.reply_text(
        "𝐓𝐡𝐞 𝐨𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐗𝐄𝐑𝐗𝐄𝐒 𝐛𝐨𝐭 🜲\n\n"
        "𝐆𝐚𝐦𝐢𝐧𝐠 • 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭 • 𝐌𝐮𝐬𝐢𝐜\n\n"
        "𝐏𝐨𝐰𝐞𝐫𝐟𝐮𝐥 𝐟𝐞𝐚𝐭𝐮𝐫𝐞𝐬, 𝐬𝐦𝐨𝐨𝐭𝐡 𝐭𝐨𝐨𝐥𝐬 "
        "𝐚𝐧𝐝 𝐚 𝐛𝐞𝐭𝐭𝐞𝐫 𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐞𝐱𝐩𝐞𝐫𝐢𝐞𝐧𝐜𝐞.\n\n"
        "✆ 𝐀𝐮𝐭𝐡𝐨𝐫𝐢𝐭𝐲 𝐬𝐮𝐩𝐩𝐨𝐫𝐭: @XERXES_XENO"
    )


# =========================================================
# ID
# =========================================================

async def user_id(update, context):
    save_user(update.effective_user.id)

    await update.message.reply_text(
        f"🆔 𝐘𝐨𝐮𝐫 𝐔𝐬𝐞𝐫 𝐈𝐃:\n\n"
        f"`{update.effective_user.id}`",
        parse_mode="Markdown"
    )


# =========================================================
# HELP
# =========================================================

async def help_command(update, context):
    save_user(update.effective_user.id)

    await update.message.reply_text(
        "🛡️ 𝐗𝐄𝐑𝐗𝐄𝐒 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓\n\n"
        "𝐌𝐨𝐝𝐞𝐫𝐚𝐭𝐢𝐨𝐧\n"
        "• /ban\n"
        "• /unban\n"
        "• /kick\n"
        "• /mute\n"
        "• /unmute\n\n"
        "𝐒𝐚𝐟𝐞𝐭𝐲\n"
        "• /warn\n"
        "• /warnings\n"
        "• /resetwarns\n"
        "• /antilink on/off\n"
        "• /antispam on/off\n\n"
        "𝐔𝐭𝐢𝐥𝐢𝐭𝐢𝐞𝐬\n"
        "• /id\n"
        "• /broadcast"
    )


# =========================================================
# MODERATION COMMANDS
# =========================================================

async def ban(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a member's message and use /ban."
        )
        return

    user = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.ban_member(user.id)

        await update.message.reply_text(
            f"🔨 {user.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐛𝐚𝐧𝐧𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception as e:
        print("Ban error:", e)
        await update.message.reply_text("❌ I couldn't ban this user.")


async def unban(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a member's message and use /unban."
        )
        return

    user = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.unban_member(
            user.id,
            only_if_banned=True
        )

        await update.message.reply_text(
            f"✅ {user.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐮𝐧𝐛𝐚𝐧𝐧𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception as e:
        print("Unban error:", e)
        await update.message.reply_text("❌ I couldn't unban this user.")


async def kick(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a member's message and use /kick."
        )
        return

    user = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.ban_member(user.id)
        await update.effective_chat.unban_member(user.id)

        await update.message.reply_text(
            f"👢 {user.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐤𝐢𝐜𝐤𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception as e:
        print("Kick error:", e)
        await update.message.reply_text("❌ I couldn't kick this user.")


async def mute(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a member's message and use /mute."
        )
        return

    user = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.restrict_member(
            user.id,
            permissions=ChatPermissions(
                can_send_messages=False
            )
        )

        await update.message.reply_text(
            f"🔇 {user.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐦𝐮𝐭𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception as e:
        print("Mute error:", e)
        await update.message.reply_text("❌ I couldn't mute this user.")


async def unmute(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a member's message and use /unmute."
        )
        return

    user = update.message.reply_to_message.from_user

    try:
        await update.effective_chat.restrict_member(
            user.id,
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
            f"🔊 {user.mention_html()} 𝐡𝐚𝐬 𝐛𝐞𝐞𝐧 𝐮𝐧𝐦𝐮𝐭𝐞𝐝.",
            parse_mode="HTML"
        )

    except Exception as e:
        print("Unmute error:", e)
        await update.message.reply_text("❌ I couldn't unmute this user.")


# =========================================================
# WARNING COMMANDS
# =========================================================

async def warn(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a member's message and use /warn."
        )
        return

    user = update.message.reply_to_message.from_user

    count = add_warning(
        update.effective_chat.id,
        user.id
    )

    await update.message.reply_text(
        f"⚠️ 𝐖𝐚𝐫𝐧𝐢𝐧𝐠 𝐢𝐬𝐬𝐮𝐞𝐝 𝐭𝐨 {user.mention_html()}.\n\n"
        f"𝐖𝐚𝐫𝐧𝐢𝐧𝐠𝐬: {count}",
        parse_mode="HTML"
    )


async def warnings(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a member's message and use /warnings."
        )
        return

    user = update.message.reply_to_message.from_user

    count = get_warnings(
        update.effective_chat.id,
        user.id
    )

    await update.message.reply_text(
        f"⚠️ {user.mention_html()} has {count} warning(s).",
        parse_mode="HTML"
    )


async def resetwarns(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a member's message and use /resetwarns."
        )
        return

    user = update.message.reply_to_message.from_user

    reset_warnings(
        update.effective_chat.id,
        user.id
    )

    await update.message.reply_text(
        f"✅ 𝐖𝐚𝐫𝐧𝐢𝐧𝐠𝐬 𝐫𝐞𝐬𝐞𝐭 𝐟𝐨𝐫 {user.mention_html()}.",
        parse_mode="HTML"
    )


# =========================================================
# ANTI-LINK
# =========================================================

async def antilink(update, context):
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
            "⚠️ Use:\n/antilink on\n/antilink off"
        )


# =========================================================
# ANTI-SPAM
# =========================================================

async def antispam(update, context):
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
            "⚠️ Use:\n/antispam on\n/antispam off"
        )


# ========================================================= 
# WELCOME SYSTEM 
# =========================================================

async def setwelcome(update, context):
    if not await admin_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Use:\n/setwelcome Your welcome message"
        )
        return

    welcome_text = " ".join(context.args)

    conn = db()

    conn.execute("""
        INSERT INTO settings (chat_id, antilink, antispam, welcome)
        VALUES (?, 0, 0, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET welcome=excluded.welcome
    """, (
        update.effective_chat.id,
        welcome_text
    ))

    conn.commit()
    conn.close()

    await update.message.reply_text(
        "🎉🛠️ 𝐍𝐞𝐰 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐢𝐬 𝐬𝐞𝐭 𝐍𝐨𝐰🍥!"
    )

async def getwelcome(update, context):
    if not await admin_only(update):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT welcome FROM settings WHERE chat_id=?",
        (update.effective_chat.id,)
    )

    result = cur.fetchone()
    conn.close()

    if result and result[0]:
        await update.message.reply_text(
            "📌 𝐂𝐮𝐫𝐫𝐞𝐧𝐭 𝐖𝐞𝐥𝐜𝐨𝐦𝐞:\n\n" + result[0]
        )
    else:
        await update.message.reply_text(
            "⚠️ 𝐍𝐨 𝐜𝐮𝐬𝐭𝐨𝐦 𝐰𝐞𝐥𝐜𝐨𝐦𝐞 𝐢𝐬 𝐬𝐞𝐭."
        )


async def resetwelcome(update, context):
    if not await admin_only(update):
        return

    conn = db()

    conn.execute(
        "UPDATE settings SET welcome=NULL WHERE chat_id=?",
        (update.effective_chat.id,)
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        "🎉🛠️ 𝐍𝐞𝐰 𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐢𝐬 𝐬𝐞𝐭 𝐍𝐨𝐰🍥!"
    )
    
 async def welcome(update, context):
    if not update.message or not update.message.new_chat_members:
        return

    chat_id = update.effective_chat.id

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT welcome FROM settings WHERE chat_id=?",
        (chat_id,)
    )

    result = cur.fetchone()
    conn.close()

    welcome_text = (
        result[0]
        if result and result[0]
        else "🪬 Welcome {user} to the group! 🥳\n\n✨ Have a great time here!"
    )

    for user in update.message.new_chat_members:
        save_user(user.id)

        message = welcome_text.replace(
            "{user}",
            user.mention_html()
        )

        await update.message.reply_text(
            message,
            parse_mode="HTML"
        )
        

# =========================================================
# MESSAGE MODERATION
# =========================================================

async def moderation_handler(update, context):
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

    try:
        member = await update.effective_chat.get_member(user.id)

        if member.status in ("administrator", "creator"):
            return

    except Exception:
        return

    text = update.message.text or update.message.caption or ""

    # ANTI-LINK

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

            except Exception as e:
                print("Anti-link error:", e)

            return

    # ANTI-SPAM

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

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        "🚨 𝐒𝐩𝐚𝐦 𝐝𝐞𝐭𝐞𝐜𝐭𝐞𝐝!\n\n"
                        f"👤 {user.mention_html()}\n"
                        f"⚠️ 𝐖𝐚𝐫𝐧𝐢𝐧𝐠𝐬: {count}\n"
                        f"🔇 𝐌𝐮𝐭𝐞𝐝 𝐟𝐨𝐫 {MUTE_TIME} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬."
                    ),
                    parse_mode="HTML"
                )

            except Exception as e:
                print("Anti-spam error:", e)


# =========================================================
# BROADCAST
# =========================================================

async def broadcast(update, context):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐭 𝐚𝐮𝐭𝐡𝐨𝐫𝐢𝐳𝐞𝐝."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Usage:\n/broadcast Your message here"
        )
        return

    message = " ".join(context.args)
    users = get_all_users()

    await update.message.reply_text(
        f"📢 𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭 𝐬𝐭𝐚𝐫𝐭𝐞𝐝...\n"
        f"👥 𝐔𝐬𝐞𝐫𝐬: {len(users)}"
    )

    sent = 0
    failed = 0

    for user_id in users:

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message
            )

            sent += 1
            await asyncio.sleep(0.1)

        except Exception as e:
            print("Broadcast error:", user_id, e)
            failed += 1

    await update.message.reply_text(
        "📊 𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭 𝐜𝐨𝐦𝐩𝐥𝐞𝐭𝐞𝐝.\n\n"
        f"✅ 𝐒𝐞𝐧𝐭: {sent}\n"
        f"❌ 𝐅𝐚𝐢𝐥𝐞𝐝: {failed}"
    )


# =========================================================
# START BOT
# =========================================================

def main():

    init_db()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN environment variable is missing."
        )

    app = Application.builder().token(token).build()

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

    app.add_handler(CommandHandler("antilink", antilink))
    app.add_handler(CommandHandler("antispam", antispam))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_handler(CommandHandler("setwelcome", setwelcome))
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome
        )
    )
    
    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.CAPTION,
            moderation_handler
        )
    )

    print("XERXES Bot is starting...")

    app.run_polling()


if __name__ == "__main__":
    main()
