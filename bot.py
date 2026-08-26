import os
import re
import sqlite3
import asyncio
import time
import random

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

DB_FILE = "/data/warnings.db"
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
    

# =========================================================
# TRAINER PROFILE
# =========================================================

    for column, definition in [
        ("trainer_id", "TEXT"),
        ("trainer_name", "TEXT"),
        ("hometown", "TEXT DEFAULT 'Unknown'"),
        ("region", "TEXT DEFAULT 'Unknown'"),
        ("wins", "INTEGER DEFAULT 0"),
        ("losses", "INTEGER DEFAULT 0"),
        ("avatar", "TEXT"),
        ("banner", "TEXT"),
        ("batches", "INTEGER DEFAULT 0")
    ]:
        try:
            cur.execute(
                f"ALTER TABLE users ADD COLUMN {column} {definition}"
        )
        except sqlite3.OperationalError:
            pass

    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            antilink INTEGER NOT NULL DEFAULT 0,
            antispam INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pokedex_control (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 1
        )
    """)

    cur.execute("""
        INSERT OR IGNORE INTO pokedex_control (id, enabled)
        VALUES (1, 1)
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pokedex (
            user_id INTEGER PRIMARY KEY,
            pokemon TEXT NOT NULL,
            nature TEXT NOT NULL,
            hp INTEGER NOT NULL,
            attack INTEGER NOT NULL,
            defense INTEGER NOT NULL,
            sp_attack INTEGER NOT NULL,
            sp_defense INTEGER NOT NULL,
            speed INTEGER NOT NULL
        )
    """)
   
    cur.execute("""
        CREATE TABLE IF NOT EXISTS filters (
            chat_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            response TEXT NOT NULL,
            PRIMARY KEY (chat_id, keyword)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sticker_filters (
            chat_id INTEGER NOT NULL,
            sticker_id TEXT NOT NULL,
            response TEXT NOT NULL,
            PRIMARY KEY (chat_id, sticker_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS text_sticker_filters (
            chat_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            sticker_id TEXT NOT NULL,
            PRIMARY KEY (chat_id, keyword)
        )
    """)
  
    try:
        cur.execute("ALTER TABLE settings ADD COLUMN welcome TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# =========================================================
# TRAINER ID
# =========================================================

def generate_trainer_id(user_id):
    return f"XRX-{user_id}"


# =========================================================
# TRAINER SAVE
# =========================================================

def save_trainer(user_id, trainer_name, hometown, region):

    trainer_id = generate_trainer_id(user_id)

    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE users
        SET trainer_id=?,
            trainer_name=?,
            hometown=?,
            region=?
        WHERE user_id=?
        """,
        (
            trainer_id,
            trainer_name,
            hometown,
            region,
            user_id
        )
    )

    conn.commit()
    conn.close()

    return trainer_id


# =========================================================
# SAVE USER
# =========================================================

def save_user(user_id):
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT trainer_id FROM users WHERE user_id=?",
        (user_id,)
    )

    result = cur.fetchone()

    if not result:
        trainer_id = f"XRX-{user_id}"

        cur.execute(
            """
            INSERT INTO users (user_id, trainer_id)
            VALUES (?, ?)
            """,
            (user_id, trainer_id)
        )

    elif not result[0]:
        trainer_id = f"XRX-{user_id}"

        cur.execute(
            """
            UPDATE users
            SET trainer_id=?
            WHERE user_id=?
            """,
            (trainer_id, user_id)
        )

    conn.commit()
    conn.close()
    

# =========================================================
# TRAINER COMMAND
# =========================================================

async def trainer(update, context):

    user_id = update.effective_user.id

    # Make sure user exists and Trainer ID is created
    save_user(user_id)

    conn = db()
    cur = conn.cursor()

    # Get Trainer Profile
    cur.execute(
        """
        SELECT trainer_id, trainer_name, hometown, region,
               wins, losses, batches
        FROM users
        WHERE user_id=?
        """,
        (user_id,)
    )

    user = cur.fetchone()

    # Get permanent starter
    cur.execute(
        """
        SELECT pokemon
        FROM pokedex
        WHERE user_id=?
        """,
        (user_id,)
    )

    pokemon = cur.fetchone()

    conn.close()

    # Not registered yet
    if not user or not user[1]:
        await update.message.reply_text(
            "❌ 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐭 𝐫𝐞𝐠𝐢𝐬𝐭𝐞𝐫𝐞𝐝 𝐚𝐬 𝐚 𝐏𝐨𝐤é𝐦𝐨𝐧 𝐓𝐫𝐚𝐢𝐧𝐞𝐫 𝐲𝐞𝐭.\n\n"
            "𝐔𝐬𝐞 /startpokedex 𝐭𝐨 𝐛𝐞𝐠𝐢𝐧 𝐲𝐨𝐮𝐫 𝐣𝐨𝐮𝐫𝐧𝐞𝐲."
        )
        return

    trainer_id, name, hometown, region, wins, losses, batches = user

    starter = pokemon[0] if pokemon else "Not selected"

    # Trainer Profile
    await update.message.reply_photo(
        photo="https://i.ibb.co/MT7GVfB/IMG-20260826-101702-983.webp",
        caption=(
            "🎓 𝐓𝐑𝐀𝐈𝐍𝐄𝐑 𝐏𝐑𝐎𝐅𝐈𝐋𝐄\n\n"
            f"👤 𝐍𝐚𝐦𝐞: {name}\n"
            f"🆔 𝐓𝐫𝐚𝐢𝐧𝐞𝐫 𝐈𝐃: {trainer_id}\n"
            f"🏠 𝐇𝐨𝐦𝐞𝐭𝐨𝐰𝐧: {hometown}\n"
            f"🌍 𝐑𝐞𝐠𝐢𝐨𝐧: {region}\n\n"
            f"🐾 𝐒𝐭𝐚𝐫𝐭𝐞𝐫: {starter}\n\n"
            f"🏆 𝐖𝐢𝐧𝐬: {wins}\n"
            f"💀 𝐋𝐨𝐬𝐬𝐞𝐬: {losses}\n"
            f"🎖️ 𝐁𝐚𝐝𝐠𝐞𝐬: {batches}"
        )
    )


# =========================================================
# POKEDEX GLOBAL CONTROL
# =========================================================

def is_pokedex_enabled():
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT enabled FROM pokedex_control WHERE id=1"
    )

    result = cur.fetchone()
    conn.close()

    return bool(result[0]) if result else True


def set_pokedex_enabled(status):
    conn = db()

    conn.execute(
        "UPDATE pokedex_control SET enabled=? WHERE id=1",
        (1 if status else 0,)
    )

    conn.commit()
    conn.close()


# =========================================================
# POKEDEX DATABASE
# =========================================================

def starter_exists(user_id):
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT pokemon FROM pokedex WHERE user_id=?",
        (user_id,)
    )

    result = cur.fetchone()
    conn.close()

    return result is not None


def save_starter(user_id, pokemon, nature, ivs):
    conn = db()

    conn.execute("""
        INSERT OR REPLACE INTO pokedex
        (
            user_id,
            pokemon,
            nature,
            hp,
            attack,
            defense,
            sp_attack,
            sp_defense,
            speed
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        pokemon,
        nature,
        ivs[0],
        ivs[1],
        ivs[2],
        ivs[3],
        ivs[4],
        ivs[5]
    ))

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
# POKEMON STARTER SETTINGS
# =========================================================

STARTER_POKEMON = [
    "Bulbasaur",
    "Charmander",
    "Squirtle",
    "Pikachu",
    "Eevee",
    "Riolu",
    "Ralts",
    "Axew"
]

NATURES = [
    "Adamant",
    "Bashful",
    "Brave",
    "Calm",
    "Careful",
    "Docile",
    "Gentle",
    "Hardy",
    "Hasty",
    "Impish",
    "Jolly",
    "Lax",
    "Lonely",
    "Mild",
    "Modest",
    "Naive",
    "Naughty",
    "Quiet",
    "Quirky",
    "Rash",
    "Relaxed",
    "Sassy",
    "Serious",
    "Timid"
]


def generate_ivs():
    while True:
        ivs = [
            random.randint(0, 31),
            random.randint(0, 31),
            random.randint(0, 31),
            random.randint(0, 31),
            random.randint(0, 31),
            random.randint(0, 31)
        ]

        total = sum(ivs)

        if 141 <= total <= 186:
            return ivs


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


def set_filter(chat_id, keyword, response):
    conn = db()
    conn.execute("""
        INSERT INTO filters (chat_id, keyword, response)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id, keyword)
        DO UPDATE SET response=excluded.response
    """, (chat_id, keyword.lower(), response))
    conn.commit()
    conn.close()


def get_filter(chat_id, keyword):
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT response FROM filters WHERE chat_id=? AND keyword=?",
        (chat_id, keyword.lower())
    )

    result = cur.fetchone()
    conn.close()

    return result[0] if result else None


def delete_filter(chat_id, keyword):
    conn = db()
    conn.execute(
        "DELETE FROM filters WHERE chat_id=? AND keyword=?",
        (chat_id, keyword.lower())
    )
    conn.commit()
    conn.close()


# =========================================================
# ADMIN CHECK
# =========================================================

async def is_admin(update):
    if not update.effective_chat or not update.effective_user:
        return False

    if update.effective_chat.type == "private":
        return False

    try:
        member = await update.effective_chat.get_member(
            update.effective_user.id
        )

        print(
            "ADMIN DEBUG:",
            "user_id =", update.effective_user.id,
            "status =", member.status,
            "chat_id =", update.effective_chat.id
        )

        return member.status in ("administrator", "creator")

    except Exception as e:
        print("Admin check error:", repr(e))
        return False


async def admin_only(update):
    if not await is_admin(update):
        await update.message.reply_text(
            "❌ 𝐀𝐝𝐦𝐢𝐧𝐬 𝐨𝐧𝐥𝐲."
        )
        return False

    return True


# =========================================================
# POKEDEX MASTER CONTROL
# =========================================================

async def stopdex(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Only the XERXES Boss can control the Pokémon system."
        )
        return

    set_pokedex_enabled(False)

    await update.message.reply_text(
        "🔴 𝐗𝐄𝐑𝐗𝐄𝐒 𝐏𝐨𝐤é𝐃𝐞𝐱 𝐒𝐲𝐬𝐭𝐞𝐦 𝐎𝐅𝐅.\n\n"
        "💾 All Pokémon data remains safe.\n"
        "🛡️ Nothing has been deleted."
    )


async def ondex(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Only the XERXES Boss can control the Pokémon system."
        )
        return

    set_pokedex_enabled(True)

    await update.message.reply_text(
        "🟢 𝐗𝐄𝐑𝐗𝐄𝐒 𝐏𝐨𝐤é𝐃𝐞𝐱 𝐒𝐲𝐬𝐭𝐞𝐦 𝐎𝐍.\n\n"
        "⚡ The Pokémon system is active again."
        )


# =========================================================
# START
# =========================================================

async def start(update, context):
    save_user(update.effective_user.id)

    await update.message.reply_text(
        "╭━━━━━━━━━━━━━━━━━╮\n"
        "         𝛸𝛴𝛤𝛸𝛴𝑆\n"
        "╰━━━━━━━━━━━━━━━━━╯\n"
        "𝐀𝐧 𝐨𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐛𝐨𝐭 𝐛𝐮𝐢𝐥𝐭 𝐭𝐨 𝐛𝐫𝐢𝐧𝐠\n"
        "𝐆𝐚𝐦𝐢𝐧𝐠, 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭 & 𝐌𝐮𝐬𝐢𝐜\n"
        "𝐭𝐨𝐠𝐞𝐭𝐡𝐞𝐫 𝐢𝐧 𝐨𝐧𝐞 𝐩𝐥𝐚𝐜𝐞 — 𝐦𝐚𝐤𝐢𝐧𝐠 𝐲𝐨𝐮𝐫\n"
        "𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐞𝐱𝐩𝐞𝐫𝐢𝐞𝐧𝐜𝐞 𝐬𝐦𝐚𝐫𝐭𝐞𝐫, 𝐬𝐦𝐨𝐨𝐭𝐡𝐞𝐫,\n"
        "𝐚𝐧𝐝 𝐦𝐨𝐫𝐞 𝐞𝐧𝐠𝐚𝐠𝐢𝐧𝐠.\n\n"
        "𝐇𝐞𝐫𝐞 𝐮 𝐠𝐞𝐭 𝐚𝐥𝐥 𝐭𝐡𝐞 𝐥𝐢𝐧𝐤𝐬 𝐚𝐧𝐝 𝐚𝐜𝐜𝐞𝐬𝐬 𝐭𝐨\n"
        "𝐚𝐥𝐥 𝐭𝐡𝐞 𝐠𝐫𝐨𝐮𝐩𝐬 𝐚𝐧𝐝 𝐜𝐡𝐚𝐧𝐧𝐞𝐥𝐬 𝐨𝐟 𝐭𝐡𝐞 𝐗𝐞𝐫𝐱𝐞𝐬 𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲.\n\n"
        "https://t.me/XERXES_COMMUNITY\n\n"
        "                ── ⋆⋅𖤓⋅⋆ ──"
)


# =========================================================
# ID
# =========================================================

async def user_id(update, context):
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    else:
        target_user = update.effective_user

    await update.message.reply_text(
        f"🆔 𝐔𝐬𝐞𝐫 𝐈𝐃:\n\n"
        f"`{target_user.id}`",
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
# PIN / UNPIN
# =========================================================

async def pin(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a message and use /pin."
        )
        return

    try:
        await update.message.reply_to_message.pin(
            disable_notification=True
        )

        await update.message.reply_text(
            "📌 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐩𝐢𝐧𝐧𝐞𝐝 𝐬𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥𝐥𝐲."
        )

    except Exception as e:
        print("Pin error:", e)
        await update.message.reply_text(
            "❌ I couldn't pin this message."
        )


async def unpin(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Reply to a message and use /unpin."
        )
        return

    try:
        await update.message.reply_to_message.unpin()

        await update.message.reply_text(
            "📌 𝐌𝐞𝐬𝐬𝐚𝐠𝐞 𝐮𝐧𝐩𝐢𝐧𝐧𝐞𝐝 𝐬𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥𝐥𝐲."
        )

    except Exception as e:
        print("Unpin error:", e)
        await update.message.reply_text(
            "❌ I couldn't unpin this message."
        )


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
# TEXT → STICKER FILTER HANDLER
# =========================================================

async def text_sticker_filter_handler(update, context):
    if not update.message:
        return

    if not update.effective_chat:
        return

    text = update.message.text or ""

    if not text:
        return

    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT keyword, sticker_id
        FROM text_sticker_filters
        WHERE chat_id=?
        """,
        (update.effective_chat.id,)
    )

    rows = cur.fetchall()
    conn.close()

    text_lower = text.lower()

    for keyword, sticker_id in rows:
        if keyword.lower() in text_lower:
            await update.message.reply_sticker(sticker_id)


# =========================================================
# FILTER COMMANDS
# =========================================================

async def filter_command(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Jis message ko filter banana hai, "
            "usse reply karke use:\n"
            "/filter keyword"
        )
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Use:\n/filter xeno"
        )
        return

    replied = update.message.reply_to_message

    if not replied.text:
        await update.message.reply_text(
            "⚠️ Sirf text message ko reply karke filter set karo."
        )
        return

    keyword = context.args[0].lower()
    response = replied.text

    set_filter(
        update.effective_chat.id,
        keyword,
        response
    )

    await update.message.reply_text(
        f"✅ Filter set for: {keyword}"
    )

async def filters_command(update, context):
    if not await admin_only(update):
        return

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT keyword FROM filters WHERE chat_id=?",
        (update.effective_chat.id,)
    )

    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(
            "📭 No filters set."
        )
        return

    text = "📋 𝐀𝐜𝐭𝐢𝐯𝐞 𝐅𝐢𝐥𝐭𝐞𝐫𝐬:\n\n"

    for row in rows:
        text += f"• {row[0]}\n"

    await update.message.reply_text(text)


async def stop_filter(update, context):
    if not await admin_only(update):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Use:\n/stop keyword"
        )
        return

    keyword = context.args[0]

    delete_filter(
        update.effective_chat.id,
        keyword
    )

    await update.message.reply_text(
        f"🗑️ Filter removed: {keyword}"
    )


# =========================================================
# STICKER FILTER
# =========================================================

async def sticker_filter(update, context):
    if not await admin_only(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Sticker ko reply karke use:\n"
            "/stickerfilter keyword"
        )
        return

    replied = update.message.reply_to_message

    if not replied.sticker:
        await update.message.reply_text(
            "⚠️ Sticker wale message ko reply karo."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Use:\n/stickerfilter xeno"
        )
        return

    keyword = context.args[0].lower()
    sticker_id = replied.sticker.file_id

    conn = db()

    conn.execute("""
        INSERT INTO text_sticker_filters
        (chat_id, keyword, sticker_id)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id, keyword)
        DO UPDATE SET sticker_id=excluded.sticker_id
    """, (
        update.effective_chat.id,
        keyword,
        sticker_id
    ))

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Sticker filter set for: {keyword}"
    )


# =========================================================
# TEXT FILTER + STICKER FILTER HANDLER
# =========================================================

async def text_sticker_filter_handler(update, context):
    if not update.message:
        return

    if not update.effective_chat:
        return

    if update.effective_chat.type == "private":
        return

    text = update.message.text or ""

    if not text:
        return

    chat_id = update.effective_chat.id
    text_lower = text.lower()

    conn = db()
    cur = conn.cursor()

    # -------------------------
    # TEXT FILTER
    # -------------------------

    cur.execute(
        "SELECT keyword, response FROM filters WHERE chat_id=?",
        (chat_id,)
    )

    text_filters = cur.fetchall()

    for keyword, response in text_filters:
        if keyword.lower() in text_lower:
            await update.message.reply_text(response)

    # -------------------------
    # STICKER FILTER
    # -------------------------

    cur.execute(
        "SELECT keyword, sticker_id FROM text_sticker_filters WHERE chat_id=?",
        (chat_id,)
    )

    sticker_filters = cur.fetchall()

    conn.close()

    for keyword, sticker_id in sticker_filters:
        if keyword.lower() in text_lower:
            await update.message.reply_sticker(sticker_id)


# =========================================================
# STICKER FILTER HANDLER
# =========================================================

async def sticker_filter_handler(update, context):
    if not update.message:
        return

    if not update.effective_chat:
        return

    if not update.message.sticker:
        return

    sticker_id = update.message.sticker.file_id

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT response FROM sticker_filters WHERE chat_id=? AND sticker_id=?",
        (update.effective_chat.id, sticker_id)
    )

    result = cur.fetchone()
    conn.close()

    if result:
        await update.message.reply_text(result[0])


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
# FILTER HANDLER
# =========================================================


async def filter_handler(update, context):
    if not update.message:
        return

    if not update.effective_chat:
        return

    if update.effective_chat.type == "private":
        return

    text = update.message.text or ""

    if not text:
        return

    response = get_filter(
        update.effective_chat.id,
        text
    )

    if response:
        await update.message.reply_text(response)


# =========================================================
# POKEDEX REGISTRATION
# =========================================================

TRAINER_NAME, TRAINER_HOMETOWN, TRAINER_REGION = range(3)


async def start_pokedex(update, context):

    user_id = update.effective_user.id

    # POKEDEX OFF CHECK
    if not is_pokedex_enabled():
        await update.message.reply_text(
            "🔴 𝐗𝐄𝐑𝐗𝐄𝐒 𝐏𝐨𝐤é𝐃𝐞𝐱 𝐢𝐬 𝐜𝐮𝐫𝐫𝐞𝐧𝐭𝐥𝐲 𝐎𝐅𝐅."
        )
        return ConversationHandler.END

    save_user(user_id)

    # ALREADY REGISTERED
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT trainer_name FROM users WHERE user_id=?",
        (user_id,)
    )

    result = cur.fetchone()
    conn.close()

    if result and result[0]:
        await update.message.reply_text(
            "𝐘𝐨𝐮 𝐚𝐫𝐞 𝐚𝐥𝐫𝐞𝐚𝐝𝐲 𝐫𝐞𝐠𝐢𝐬𝐭𝐞𝐫𝐞𝐝 𝐚𝐬 𝐚 𝐭𝐫𝐚𝐢𝐧𝐞𝐫 𝐢𝐧 "
            "𝐏𝐨𝐤𝐞𝐰𝐨𝐫𝐥𝐝 𝐨𝐟 𝛸𝛴𝛤𝛸𝛴𝑆 ❗"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🎓 𝐖𝐞𝐥𝐜𝐨𝐦𝐞, 𝐟𝐮𝐭𝐮𝐫𝐞 𝐓𝐫𝐚𝐢𝐧𝐞𝐫!\n\n"
        "𝐖𝐡𝐚𝐭 𝐧𝐚𝐦𝐞 𝐰𝐨𝐮𝐥𝐝 𝐲𝐨𝐮 𝐥𝐢𝐤𝐞 𝐭𝐨 𝐮𝐬𝐞 𝐚𝐬 𝐲𝐨𝐮𝐫 "
        "𝐓𝐫𝐚𝐢𝐧𝐞𝐫 𝐧𝐚𝐦𝐞?"
    )

    return TRAINER_NAME


async def trainer_name(update, context):

    name = update.message.text.strip()

    if not name:
        await update.message.reply_text(
            "⚠️ Please enter a valid Trainer name."
        )
        return TRAINER_NAME

    if len(name) > 30:
        await update.message.reply_text(
            "⚠️ Trainer name must be 30 characters or less."
        )
        return TRAINER_NAME

    context.user_data["trainer_name"] = name

    await update.message.reply_text(
        "🏠 𝐖𝐡𝐚𝐭 𝐢𝐬 𝐲𝐨𝐮𝐫 𝐡𝐨𝐦𝐞𝐭𝐨𝐰𝐧?"
    )

    return TRAINER_HOMETOWN


async def trainer_hometown(update, context):

    hometown = update.message.text.strip()

    if not hometown:
        await update.message.reply_text(
            "⚠️ Please enter a valid hometown."
        )
        return TRAINER_HOMETOWN

    if len(hometown) > 30:
        await update.message.reply_text(
            "⚠️ Hometown must be 30 characters or less."
        )
        return TRAINER_HOMETOWN

    context.user_data["hometown"] = hometown

    keyboard = [
        [
            InlineKeyboardButton("𝐊𝐚𝐧𝐭𝐨", callback_data="region_Kanto"),
            InlineKeyboardButton("𝐉𝐨𝐡𝐭𝐨", callback_data="region_Johto")
        ],
        [
            InlineKeyboardButton("𝐇𝐨𝐞𝐧𝐧", callback_data="region_Hoenn"),
            InlineKeyboardButton("𝐒𝐢𝐧𝐧𝐨𝐡", callback_data="region_Sinnoh")
        ],
        [
            InlineKeyboardButton("𝐔𝐧𝐨𝐯𝐚", callback_data="region_Unova"),
            InlineKeyboardButton("𝐊𝐚𝐥𝐨𝐬", callback_data="region_Kalos")
        ],
        [
            InlineKeyboardButton("𝐀𝐥𝐨𝐥𝐚", callback_data="region_Alola"),
            InlineKeyboardButton("𝐆𝐚𝐥𝐚𝐫", callback_data="region_Galar")
        ],
        [
            InlineKeyboardButton("𝐏𝐚𝐥𝐝𝐞𝐚", callback_data="region_Paldea")
        ]
    ]

    await update.message.reply_text(
        "🌍 𝐂𝐡𝐨𝐨𝐬𝐞 𝐲𝐨𝐮𝐫 𝐏𝐨𝐤é𝐦𝐨𝐧 𝐫𝐞𝐠𝐢𝐨𝐧:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return TRAINER_REGION


async def trainer_region(update, context):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    region = query.data.replace("region_", "")

    trainer_name = context.user_data.get("trainer_name")
    hometown = context.user_data.get("hometown")

    if not trainer_name or not hometown:
        await query.message.reply_text(
            "❌ 𝐓𝐫𝐚𝐢𝐧𝐞𝐫 𝐫𝐞𝐠𝐢𝐬𝐭𝐫𝐚𝐭𝐢𝐨𝐧 𝐞𝐫𝐫𝐨𝐫.\n\n"
            "Please use /startpokedex again."
        )
        return ConversationHandler.END

    # Save Trainer ID + Name + Hometown + Region
    save_trainer(
        user_id,
        trainer_name,
        hometown,
        region
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "𝐁𝐮𝐥𝐛𝐚𝐬𝐚𝐮𝐫 🌱",
                callback_data="starter_bulbasaur"
            ),
            InlineKeyboardButton(
                "𝐂𝐡𝐚𝐫𝐦𝐚𝐧𝐝𝐞𝐫 🔥",
                callback_data="starter_charmander"
            )
        ],
        [
            InlineKeyboardButton(
                "𝐒𝐪𝐮𝐮𝐫𝐭𝐥𝐞 💧",
                callback_data="starter_squirtle"
            ),
            InlineKeyboardButton(
                "𝐏𝐢𝐤𝐚𝐜𝐡𝐮 ⚡",
                callback_data="starter_pikachu"
            )
        ],
        [
            InlineKeyboardButton(
                "𝐄𝐞𝐯𝐞𝐞 ✨",
                callback_data="starter_eevee"
            ),
            InlineKeyboardButton(
                "𝐑𝐢𝐨𝐥𝐮 🥊",
                callback_data="starter_riolu"
            )
        ],
        [
            InlineKeyboardButton(
                "𝐑𝐚𝐥𝐭𝐬 🔮",
                callback_data="starter_ralts"
            ),
            InlineKeyboardButton(
                "𝐀𝐱𝐞𝐰 🐉",
                callback_data="starter_axew"
            )
        ]
    ]

    await query.message.edit_text(
        "🌍 𝐑𝐞𝐠𝐢𝐨𝐧 𝐬𝐞𝐭 𝐭𝐨: "
        f"𝐓𝐡𝐞 𝐫𝐞𝐠𝐢𝐨𝐧 𝐨𝐟 {region}\n\n"
        "🐾 𝐍𝐨𝐰 𝐜𝐡𝐨𝐨𝐬𝐞 𝐲𝐨𝐮𝐫 𝐟𝐢𝐫𝐬𝐭 𝐏𝐨𝐤é𝐦𝐨𝐧!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return ConversationHandler.END


# =========================================================
# STARTER SELECTION
# =========================================================

import random


STARTER_NAMES = {
    "starter_bulbasaur": "𝐁𝐮𝐥𝐛𝐚𝐬𝐚𝐮𝐫 🌱",
    "starter_charmander": "𝐂𝐡𝐚𝐫𝐦𝐚𝐧𝐝𝐞𝐫 🔥",
    "starter_squirtle": "𝐒𝐪𝐮𝐢𝐫𝐭𝐥𝐞 💧",
    "starter_pikachu": "𝐏𝐢𝐤𝐚𝐜𝐡𝐮 ⚡",
    "starter_eevee": "𝐄𝐞𝐯𝐞𝐞 ✨",
    "starter_riolu": "𝐑𝐢𝐨𝐥𝐮 🥊",
    "starter_ralts": "𝐑𝐚𝐥𝐭𝐬 🔮",
    "starter_axew": "𝐀𝐱𝐞𝐰 🐉"
}


NATURES = [
    "Hardy",
    "Lonely",
    "Brave",
    "Adamant",
    "Naughty",
    "Bold",
    "Docile",
    "Relaxed",
    "Impish",
    "Lax",
    "Timid",
    "Hasty",
    "Serious",
    "Jolly",
    "Naive",
    "Modest",
    "Mild",
    "Quiet",
    "Rash",
    "Bashful",
    "Calm",
    "Gentle",
    "Sassy",
    "Careful",
    "Quirky"
]


async def starter_selected(update, context):
    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    # Already has a starter
    if starter_exists(user_id):
        try:
            await query.message.delete()
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚠️ 𝐘𝐨𝐮 𝐚𝐥𝐫𝐞𝐚𝐝𝐲 𝐡𝐚𝐯𝐞 𝐚 𝐏𝐨𝐤é𝐦𝐨𝐧 𝐢𝐧 𝐲𝐨𝐮𝐫 𝐏𝐨𝐤é𝐝𝐞𝐱."
        )
        return

    pokemon = STARTER_NAMES.get(query.data)

    if not pokemon:
        return

    # Random Nature
    nature = random.choice(NATURES)

    # Random IVs — total 141–186
    while True:
        ivs = [random.randint(0, 31) for _ in range(6)]

        if 141 <= sum(ivs) <= 186:
            break

    # Save Pokémon + hidden Nature + IVs
    save_starter(
        user_id,
        pokemon,
        nature,
        ivs
    )

    # Delete starter selection message
    try:
        await query.message.delete()
    except Exception as e:
        print("Starter message delete error:", e)

    # Simple confirmation only
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            f"☻ 𝐏𝐨𝐤é𝐦𝐨𝐧 𝐚𝐝𝐝𝐞𝐝 𝐭𝐨 𝐲𝐨𝐮𝐫 𝐏𝐨𝐤é𝐝𝐞𝐱!\n\n"
            f"🐾 {pokemon}"
        )
    )


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
    app.add_handler(CommandHandler("trainer", trainer))
    app.add_handler(CommandHandler("stopdex", stopdex))
    app.add_handler(CommandHandler("ondex", ondex))
    pokedex_registration = ConversationHandler(
        entry_points=[
            CommandHandler("startpokedex", start_pokedex)
        ],
        states={
            TRAINER_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trainer_name
                )
            ],
            TRAINER_HOMETOWN: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    trainer_hometown
                )
            ],
            TRAINER_REGION: [
                CallbackQueryHandler(
                    trainer_region,
                    pattern="^region_"
                )
            ]
        },
        fallbacks=[]
    )

    app.add_handler(pokedex_registration)

    app.add_handler(CommandHandler("id", user_id))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("pin", pin))
    app.add_handler(CommandHandler("unpin", unpin))

    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warnings", warnings))
    app.add_handler(CommandHandler("resetwarns", resetwarns))

    app.add_handler(CommandHandler("antilink", antilink))
    app.add_handler(CommandHandler("antispam", antispam))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_handler(CommandHandler("filter", filter_command))
    app.add_handler(CommandHandler("filters", filters_command))
    app.add_handler(CommandHandler("stop", stop_filter))
    app.add_handler(CommandHandler("stickerfilter", sticker_filter))
    
    app.add_handler(CommandHandler("setwelcome", setwelcome))
    app.add_handler(CommandHandler("getwelcome", getwelcome))
    app.add_handler(CommandHandler("resetwelcome", resetwelcome))
    
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome
        )
    )
    
    app.add_handler(
        MessageHandler(
            filters.TEXT,
            text_sticker_filter_handler
        )
    )
    
    app.add_handler(
        MessageHandler(
            filters.Sticker.ALL,
            sticker_filter_handler
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
