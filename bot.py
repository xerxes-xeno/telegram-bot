import os
import re
import sqlite3
import asyncio
import time
import random
import threading
import hashlib
import hmac

from flask import Flask, jsonify, request

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from urllib.request import urlopen

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo
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


# =========================================================
# MINI APP API
# =========================================================

api = Flask(__name__)

from flask_cors import CORS

CORS(api)

# =========================================================
# VERIFY TELEGRAM MINI APP DATA
# =========================================================

def verify_telegram_init_data(init_data):

    if not init_data:
        return None

    try:
        from urllib.parse import parse_qsl

        data = dict(parse_qsl(init_data, keep_blank_values=True))

        received_hash = data.pop("hash", None)

        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={data[key]}"
            for key in sorted(data)
        )

        token = os.environ.get("TELEGRAM_BOT_TOKEN")

        if not token:
            return None

        secret_key = hmac.new(
            b"WebAppData",
            token.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash
        ):
            return None

        return data

    except Exception:
        return None 

@api.route("/api/profile")
def get_profile():

    # Get Telegram Mini App initData
    init_data = request.headers.get("X-Telegram-Init-Data")

    verified_data = verify_telegram_init_data(init_data)

    if not verified_data:
        return jsonify({
            "error": "Invalid Telegram data"
        }), 403

    user_json = verified_data.get("user")

    if not user_json:
        return jsonify({
            "error": "Telegram user not found"
        }), 403

    import json

    telegram_user = json.loads(user_json)

    user_id = telegram_user.get("id")

    if not user_id:
        return jsonify({
            "error": "Telegram user ID not found"
        }), 403
 
    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            trainer_id,
            trainer_name,
            hometown,
            region,
            wins,
            losses,
            batches
        FROM users
        WHERE user_id=?
        """,
        (user_id,)
    )

    user = cur.fetchone()

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

    if not user:
        return jsonify({
            "error": "Trainer not found"
        }), 404

    return jsonify({
        "trainer_id": user[0],
        "name": user[1],
        "hometown": user[2],
        "region": user[3],
        "wins": user[4] or 0,
        "losses": user[5] or 0,
        "badges": user[6] or 0,
        "starter": pokemon[0] if pokemon else "Not selected"
    })


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
# TRAINER PROFILE IMAGE
# =========================================================

TRAINER_PROFILE_IMAGE = (
    "https://i.ibb.co/QjQXF3x9/IMG-20260826-143257.jpg"
)


def get_font(size):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
    ]

    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass

    return ImageFont.load_default()


def create_trainer_profile(
    name,
    trainer_id,
    hometown,
    region,
    starter,
    wins,
    losses
):

    # Download template image
    image_data = urlopen(TRAINER_PROFILE_IMAGE).read()

    image = Image.open(BytesIO(image_data)).convert("RGB")

    draw = ImageDraw.Draw(image)

    # Fonts
    normal_font = get_font(16)
    small_font = get_font(13)
    region_font = get_font(14)

    # =====================================================
    # TEXT POSITIONS
    # =====================================================

    # NAME
    draw.text(
        (145, 146),
        str(name),
        font=normal_font,
        fill="black"
    )

    # HOMETOWN
    draw.text(
        (175, 181),
        str(hometown),
        font=normal_font,
        fill="black"
    )

    # STARTER
    draw.text(
        (145, 215),
        str(starter),
        font=normal_font,
        fill="black"
    )

    # WINS
    draw.text(
        (145, 257),
        str(wins),
        font=normal_font,
        fill="black"
    )

    # LOSSES
    draw.text(
        (155, 288),
        str(losses),
        font=normal_font,
        fill="black"
    )

    # TRAINER ID
    draw.text(
        (105, 322),
        str(trainer_id),
        font=small_font,
        fill="black"
    )

    # Save into memory
    output = BytesIO()
    output.name = "trainer_profile.jpg"

    image.save(
        output,
        format="JPEG",
        quality=95
    )

    output.seek(0)

    return output


# =========================================================
# TRAINER COMMAND
# =========================================================

async def trainer(update, context):

    user_id = update.effective_user.id

    # Make sure user exists
    save_user(user_id)

    conn = db()
    cur = conn.cursor()

    # Trainer information
    cur.execute(
        """
        SELECT
            trainer_id,
            trainer_name,
            hometown,
            region,
            wins,
            losses,
            batches
        FROM users
        WHERE user_id=?
        """,
        (user_id,)
    )

    user = cur.fetchone()

    # Starter information
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

    # =====================================================
    # PROFILE NOT FOUND
    # =====================================================

    if not user or not user[1]:

        await update.message.reply_text(
            "❌ 𝐘𝐨𝐮 𝐚𝐫𝐞 𝐧𝐨𝐭 𝐫𝐞𝐠𝐢𝐬𝐭𝐞𝐫𝐞𝐝 𝐚𝐬 𝐚 "
            "𝐏𝐨𝐤é𝐦𝐨𝐧 𝐓𝐫𝐚𝐢𝐧𝐞𝐫 𝐲𝐞𝐭.\n\n"
            "Use /startpokedex to begin your journey."
        )

        return

    (
        trainer_id,
        name,
        hometown,
        region,
        wins,
        losses,
        batches
    ) = user

    starter = pokemon[0] if pokemon else "Not selected"

    # Safety for old database rows
    wins = wins if wins is not None else 0
    losses = losses if losses is not None else 0

    # =====================================================
    # CREATE PROFILE IMAGE
    # =====================================================

    profile_image = create_trainer_profile(
        name=name,
        trainer_id=trainer_id,
        hometown=hometown,
        region=region,
        starter=starter,
        wins=wins,
        losses=losses
    )

    # =====================================================
    # SEND ONLY IMAGE
    # =====================================================

    keyboard = [
        [
            InlineKeyboardButton(
                text="👤 Profile",
                web_app=WebAppInfo(
                    url="https://xerxes-xeno.github.io/xerxes-miniapp/"
                )
            )
        ],
        [
            InlineKeyboardButton(
                text="🎟️ X Pass Batches",
                callback_data="x_pass_batches"
            )
        ],
        [
            InlineKeyboardButton(
                text="💎 X Prime Pass Batches",
                callback_data="x_prime_batches"
            )
        ]
    ]

    await update.message.reply_photo(
        photo=profile_image,
        reply_markup=InlineKeyboardMarkup(keyboard)
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
# POKEDEX HELP
# =========================================================

async def helpdex(update, context):

    keyboard = [
        [
            InlineKeyboardButton(
                "📖 𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐃𝐚𝐭𝐚",
                callback_data="dex_data"
            ),
            InlineKeyboardButton(
                "⚔️ 𝐃𝐚𝐦𝐚𝐠𝐞 𝐂𝐚𝐥𝐜",
                callback_data="dex_damage"
            )
        ],
        [
            InlineKeyboardButton(
                "📋 𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐁𝐮𝐢𝐥𝐝",
                callback_data="dex_build"
            ),
            InlineKeyboardButton(
                "📊 𝐓𝐲𝐩𝐞",
                callback_data="dex_type"
            )
        ],
        [
            InlineKeyboardButton(
                "🌿 𝐍𝐚𝐭𝐮𝐫𝐞𝐬",
                callback_data="dex_nature"
            ),
            InlineKeyboardButton(
                "⭐ 𝐁𝐞𝐬𝐭 𝐍𝐚𝐭𝐮𝐫𝐞",
                callback_data="dex_bestnature"
            )
        ],
        [
            InlineKeyboardButton(
                "🏋️ 𝐄𝐕 𝐁𝐮𝐢𝐥𝐝",
                callback_data="dex_ev"
            ),
            InlineKeyboardButton(
                "🏆 𝐓𝐌 𝐋𝐢𝐬𝐭",
                callback_data="dex_tm"
            )
        ],
        [
            InlineKeyboardButton(
                "🎯 𝐏𝐨𝐤𝐞́ 𝐁𝐚𝐥𝐥𝐬",
                callback_data="dex_pokeballs"
            ),
            InlineKeyboardButton(
                "⚔️ 𝐌𝐨𝐯𝐞𝐬",
                callback_data="dex_moves"
            )
        ]
    ]

    await update.message.reply_text(
        "📱 𝐗𝐄𝐑𝐗𝐄𝐒 𝐏𝐨𝐤𝐞́𝐃𝐞𝐱\n\n"
        "𝐘𝐨𝐮𝐫 𝐜𝐨𝐦𝐩𝐥𝐞𝐭𝐞 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐝𝐚𝐭𝐚 𝐚𝐧𝐝 "
        "𝐭𝐫𝐚𝐢𝐧𝐢𝐧𝐠 𝐠𝐮𝐢𝐝𝐞.\n\n"
        "𝐒𝐞𝐥𝐞𝐜𝐭 𝐚𝐧 𝐨𝐩𝐭𝐢𝐨𝐧 𝐛𝐞𝐥𝐨𝐰:",
        reply_markup=InlineKeyboardMarkup(keyboard)
            )


# =========================================================
# POKEDEX HELP CALLBACK
# =========================================================

async def helpdex_callback(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "dex_data":

        await query.edit_message_text(
            "📖 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐃𝐚𝐭𝐚\n\n"
            "Use:\n"
            "/data <Pokémon name>\n\n"
            "Example:\n"
            "/data Pikachu",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_damage":

        await query.edit_message_text(
            "⚔️ 𝐃𝐚𝐦𝐚𝐠𝐞 𝐂𝐚𝐥𝐜𝐮𝐥𝐚𝐭𝐨𝐫\n\n"
            "Use /datadamage to get the damage calculator form.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_build":

        await query.edit_message_text(
            "📋 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐁𝐮𝐢𝐥𝐝\n\n"
            "Use /buildpoke to get the Pokémon build form.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_type":

        await query.edit_message_text(
            "📊 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐓𝐲𝐩𝐞\n\n"
            "Type effectiveness chart will be available here.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_nature":

        await query.edit_message_text(
            "🌿 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐍𝐚𝐭𝐮𝐫𝐞𝐬\n\n"
            "Select a nature category to view its natures.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "𝐍𝐞𝐮𝐭𝐫𝐚𝐥",
                        callback_data="nature_neutral"
                    ),
                    InlineKeyboardButton(
                        "𝐀𝐭𝐭𝐚𝐜𝐤",
                        callback_data="nature_attack"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "𝐃𝐞𝐟𝐞𝐧𝐬𝐞",
                        callback_data="nature_defense"
                    ),
                    InlineKeyboardButton(
                        "𝐒𝐩. 𝐀𝐭𝐭𝐚𝐜𝐤",
                        callback_data="nature_spattack"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "𝐒𝐩. 𝐃𝐞𝐟𝐞𝐧𝐬𝐞",
                        callback_data="nature_spdefense"
                    ),
                    InlineKeyboardButton(
                        "𝐒𝐩𝐞𝐞𝐝",
                        callback_data="nature_speed"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "𝐀𝐥𝐥 𝐍𝐚𝐭𝐮𝐫𝐞𝐬",
                        callback_data="nature_all"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_bestnature":

        await query.edit_message_text(
            "⭐ 𝐁𝐞𝐬𝐭 𝐍𝐚𝐭𝐮𝐫𝐞\n\n"
            "Use:\n"
            "/bestnat <Pokémon name>\n\n"
            "Example:\n"
            "/bestnat Pikachu",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_ev":

        await query.edit_message_text(
            "🏋️ 𝐄𝐕 𝐓𝐫𝐚𝐢𝐧𝐢𝐧𝐠 𝐆𝐮𝐢𝐝𝐞\n\n"
            "Select a stat to see Pokémon used for EV training.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("𝐇𝐏", callback_data="ev_hp"),
                    InlineKeyboardButton("𝐀𝐭𝐭𝐚𝐜𝐤", callback_data="ev_attack")
                ],
                [
                    InlineKeyboardButton("𝐃𝐞𝐟𝐞𝐧𝐬𝐞", callback_data="ev_defense"),
                    InlineKeyboardButton("𝐒𝐩. 𝐀𝐭𝐭𝐚𝐜𝐤", callback_data="ev_spattack")
                ],
                [
                    InlineKeyboardButton("𝐒𝐩. 𝐃𝐞𝐟𝐞𝐧𝐬𝐞", callback_data="ev_spdefense"),
                    InlineKeyboardButton("𝐒𝐩𝐞𝐞𝐝", callback_data="ev_speed")
                ],
                [
                    InlineKeyboardButton(
                        "𝐇𝐨𝐰 𝐄𝐕 𝐓𝐫𝐚𝐢𝐧𝐢𝐧𝐠 𝐖𝐨𝐫𝐤𝐬",
                        callback_data="ev_how"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_tm":

        await query.edit_message_text(
            "🏆 𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌 𝐋𝐢𝐬𝐭\n\n"
            "171 official TMs are available across 6 pages.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌𝐬",
                        callback_data="tm_page_1"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_pokeballs":

        await query.edit_message_text(
            "🎯 𝐏𝐨𝐤𝐞́ 𝐁𝐚𝐥𝐥𝐬 𝐆𝐮𝐢𝐝𝐞\n\n"
            "Regular Ball\n"
            "Great Ball\n"
            "Ultra Ball\n"
            "Level Ball\n"
            "Fast Ball\n"
            "Repeat Ball\n"
            "Nest Ball\n"
            "Net Ball\n"
            "Quick Ball\n"
            "Master Ball\n"
            "Safari Ball",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_moves":

        await query.edit_message_text(
            "⚔️ 𝐌𝐨𝐯𝐞 𝐃𝐚𝐭𝐚\n\n"
            "Use:\n"
            "/move <move name>\n\n"
            "Example:\n"
            "/move Crunch",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="dex_help_main"
                    )
                ]
            ])
        )

    elif query.data == "dex_help_main":

        keyboard = [
            [
                InlineKeyboardButton(
                    "📖 𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐃𝐚𝐭𝐚",
                    callback_data="dex_data"
                ),
                InlineKeyboardButton(
                    "⚔️ 𝐃𝐚𝐦𝐚𝐠𝐞 𝐂𝐚𝐥𝐜",
                    callback_data="dex_damage"
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐁𝐮𝐢𝐥𝐝",
                    callback_data="dex_build"
                ),
                InlineKeyboardButton(
                    "📊 𝐓𝐲𝐩𝐞",
                    callback_data="dex_type"
                )
            ],
            [
                InlineKeyboardButton(
                    "🌿 𝐍𝐚𝐭𝐮𝐫𝐞𝐬",
                    callback_data="dex_nature"
                ),
                InlineKeyboardButton(
                    "⭐ 𝐁𝐞𝐬𝐭 𝐍𝐚𝐭𝐮𝐫𝐞",
                    callback_data="dex_bestnature"
                )
            ],
            [
                InlineKeyboardButton(
                    "🏋️ 𝐄𝐕 𝐁𝐮𝐢𝐥𝐝",
                    callback_data="dex_ev"
                ),
                InlineKeyboardButton(
                    "🏆 𝐓𝐌 𝐋𝐢𝐬𝐭",
                    callback_data="dex_tm"
                )
            ],
            [
                InlineKeyboardButton(
                    "🎯 𝐏𝐨𝐤𝐞́ 𝐁𝐚𝐥𝐥𝐬",
                    callback_data="dex_pokeballs"
                ),
                InlineKeyboardButton(
                    "⚔️ 𝐌𝐨𝐯𝐞𝐬",
                    callback_data="dex_moves"
                )
            ]
        ]

        await query.edit_message_text(
            "📱 𝐗𝐄𝐑𝐗𝐄𝐒 𝐏𝐨𝐤𝐞́𝐃𝐞𝐱\n\n"
            "𝐘𝐨𝐮𝐫 𝐜𝐨𝐦𝐩𝐥𝐞𝐭𝐞 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐝𝐚𝐭𝐚 𝐚𝐧𝐝 "
            "𝐭𝐫𝐚𝐢𝐧𝐢𝐧𝐠 𝐠𝐮𝐢𝐝𝐞.\n\n"
            "𝐒𝐞𝐥𝐞𝐜𝐭 𝐚𝐧 𝐨𝐩𝐭𝐢𝐨𝐧 𝐛𝐞𝐥𝐨𝐰:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# =========================================================
# POKEMON DATA
# =========================================================

async def pokemon_data(update, context):

    if not context.args:
        await update.message.reply_text(
            "⚠️ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐞𝐧𝐭𝐞𝐫 𝐚 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐧𝐚𝐦𝐞.\n\n"
            "𝐄𝐱𝐚𝐦𝐩𝐥𝐞:\n"
            "/data Pikachu"
        )
        return

    pokemon_name = " ".join(context.args).strip()

    await update.message.reply_text(
        f"📖 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐃𝐚𝐭𝐚\n\n"
        f"𝐍𝐚𝐦𝐞: {pokemon_name}\n\n"
        "⚠️ 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐝𝐚𝐭𝐚𝐛𝐚𝐬𝐞 𝐢𝐬 𝐛𝐞𝐢𝐧𝐠 𝐩𝐫𝐞𝐩𝐚𝐫𝐞𝐝."
    )


# =========================================================
# DAMAGE CALCULATOR FORM
# =========================================================

async def datadamage(update, context):

    await update.message.reply_text(
        "⚔️ 𝐃𝐀𝐌𝐀𝐆𝐄 𝐂𝐀𝐋𝐂𝐔𝐋𝐀𝐓𝐎𝐑 𝐅𝐎𝐑𝐌\n\n"
        "Copy and paste this template, fill it in, and send it back:\n\n"
        "--- 𝐀𝐓𝐓𝐀𝐂𝐊𝐄𝐑 ---\n"
        "Name : \n"
        "Nature : \n"
        "Move : \n"
        "HP IV/EV : 31 , 0\n"
        "ATK IV/EV : 31 , 0\n"
        "DEF IV/EV : 31 , 0\n"
        "SPA IV/EV : 31 , 0\n"
        "SPD IV/EV : 31 , 0\n"
        "SPE IV/EV : 31 , 0\n\n"
        "--- 𝐃𝐄𝐅𝐄𝐍𝐃𝐄𝐑 ---\n"
        "Name : 0\n"
        "Nature : \n"
        "HP IV/EV : 31 , 0\n"
        "ATK IV/EV : 31 , 0\n"
        "DEF IV/EV : 31 , 0\n"
        "SPA IV/EV : 31 , 0\n"
        "SPD IV/EV : 31 , 0\n"
        "SPE IV/EV : 31 , 0"
    )


# =========================================================
# POKEMON BUILD FORM
# =========================================================

async def buildpoke(update, context):

    await update.message.reply_text(
        "📋 𝐏𝐎𝐊𝐄𝐌𝐎𝐍 𝐁𝐔𝐈𝐋𝐃 𝐅𝐎𝐑𝐌\n\n"
        "Copy and paste this template, EDIT it in, and send it back:\n\n"
        "--- 𝐁𝐔𝐈𝐋𝐃 ---\n"
        "Name : \n"
        "Nature : \n"
        "HP IV/EV : 31 , 0\n"
        "ATK IV/EV : 31 , 0\n"
        "DEF IV/EV : 31 , 0\n"
        "SPA IV/EV : 31 , 0\n"
        "SPD IV/EV : 31 , 0\n"
        "SPE IV/EV : 31 , 0"
    )


# =========================================================
# POKEMON TYPE CHART
# =========================================================

async def pokemon_type(update, context):

    keyboard = [
        [
            InlineKeyboardButton("🔥 Fire", callback_data="type_fire"),
            InlineKeyboardButton("💧 Water", callback_data="type_water")
        ],
        [
            InlineKeyboardButton("🌿 Grass", callback_data="type_grass"),
            InlineKeyboardButton("⚡ Electric", callback_data="type_electric")
        ],
        [
            InlineKeyboardButton("❄️ Ice", callback_data="type_ice"),
            InlineKeyboardButton("🥊 Fighting", callback_data="type_fighting")
        ],
        [
            InlineKeyboardButton("☠️ Poison", callback_data="type_poison"),
            InlineKeyboardButton("⛰️ Ground", callback_data="type_ground")
        ],
        [
            InlineKeyboardButton("🪽 Flying", callback_data="type_flying"),
            InlineKeyboardButton("🔮 Psychic", callback_data="type_psychic")
        ],
        [
            InlineKeyboardButton("🐛 Bug", callback_data="type_bug"),
            InlineKeyboardButton("🪨 Rock", callback_data="type_rock")
        ],
        [
            InlineKeyboardButton("👻 Ghost", callback_data="type_ghost"),
            InlineKeyboardButton("🐉 Dragon", callback_data="type_dragon")
        ],
        [
            InlineKeyboardButton("🌑 Dark", callback_data="type_dark"),
            InlineKeyboardButton("⚙️ Steel", callback_data="type_steel")
        ],
        [
            InlineKeyboardButton("✨ Fairy", callback_data="type_fairy"),
            InlineKeyboardButton("⚪ Normal", callback_data="type_normal")
        ]
    ]

    await update.message.reply_text(
        "📊 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐓𝐲𝐩𝐞 𝐄𝐟𝐟𝐞𝐜𝐭𝐢𝐯𝐞𝐧𝐞𝐬𝐬 𝐂𝐡𝐚𝐫𝐭\n\n"
        "Select a type to see its effectiveness against other types:\n\n"
        "💚 = Super Effective (2x)\n"
        "💛 = Normal (1x)\n"
        "💔 = Not Very Effective (0.5x)\n"
        "🚫 = No Effect (0x)",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# POKEMON NATURES
# =========================================================

async def datanature(update, context):

    keyboard = [
        [
            InlineKeyboardButton(
                "1. 𝐍𝐞𝐮𝐭𝐫𝐚𝐥",
                callback_data="nature_neutral"
            )
        ],
        [
            InlineKeyboardButton(
                "2. 𝐀𝐭𝐭𝐚𝐜𝐤",
                callback_data="nature_attack"
            )
        ],
        [
            InlineKeyboardButton(
                "3. 𝐃𝐞𝐟𝐞𝐧𝐬𝐞",
                callback_data="nature_defense"
            )
        ],
        [
            InlineKeyboardButton(
                "4. 𝐒𝐩𝐞𝐜𝐢𝐚𝐥 𝐀𝐭𝐭𝐚𝐜𝐤",
                callback_data="nature_spattack"
            )
        ],
        [
            InlineKeyboardButton(
                "5. 𝐒𝐩𝐞𝐜𝐢𝐚𝐥 𝐃𝐞𝐟𝐞𝐧𝐜𝐞",
                callback_data="nature_spdefense"
            )
        ],
        [
            InlineKeyboardButton(
                "6. 𝐒𝐩𝐞𝐞𝐝",
                callback_data="nature_speed"
            )
        ],
        [
            InlineKeyboardButton(
                "7. 𝐀𝐥𝐥 𝐍𝐚𝐭𝐮𝐫𝐞𝐬",
                callback_data="nature_all"
            )
        ]
    ]

    await update.message.reply_text(
        "🌿 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐍𝐚𝐭𝐮𝐫𝐞𝐬\n\n"
        "Natures affect a Pokémon's stat growth:\n"
        "• 📈 +10% to one stat\n"
        "• 📉 -10% to another stat\n"
        "• ⚖️ Some natures are neutral (no effect)\n\n"
        "Select a category to view natures:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# BEST NATURE
# =========================================================

async def bestnat(update, context):

    if not context.args:
        await update.message.reply_text(
            "⚠️ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐞𝐧𝐭𝐞𝐫 𝐚 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐧𝐚𝐦𝐞.\n\n"
            "𝐄𝐱𝐚𝐦𝐩𝐥𝐞:\n"
            "/bestnat Pikachu"
        )
        return

    pokemon_name = " ".join(context.args).strip()

    await update.message.reply_text(
        f"⭐ 𝐁𝐞𝐬𝐭 𝐍𝐚𝐭𝐮𝐫𝐞 — {pokemon_name}\n\n"
        "⚠️ 𝐁𝐞𝐬𝐭 𝐧𝐚𝐭𝐮𝐫𝐞 𝐝𝐚𝐭𝐚𝐛𝐚𝐬𝐞 𝐜𝐨𝐧𝐧𝐞𝐜𝐭𝐢𝐨𝐧 𝐰𝐢𝐥𝐥 𝐛𝐞 𝐚𝐝𝐝𝐞𝐝."
    )


# =========================================================
# EV TRAINING GUIDE
# =========================================================

async def evbuild(update, context):

    keyboard = [
        [
            InlineKeyboardButton(
                "𝐇𝐏",
                callback_data="ev_hp"
            ),
            InlineKeyboardButton(
                "𝐀𝐭𝐭𝐚𝐜𝐤",
                callback_data="ev_attack"
            )
        ],
        [
            InlineKeyboardButton(
                "𝐃𝐞𝐟𝐞𝐧𝐜𝐞",
                callback_data="ev_defense"
            ),
            InlineKeyboardButton(
                "𝐒𝐩𝐞𝐜𝐢𝐚𝐥 𝐀𝐭𝐭𝐚𝐜𝐤",
                callback_data="ev_spattack"
            )
        ],
        [
            InlineKeyboardButton(
                "𝐒𝐩𝐞𝐜𝐢𝐚𝐥 𝐃𝐞𝐟𝐞𝐧𝐜𝐞",
                callback_data="ev_spdefense"
            ),
            InlineKeyboardButton(
                "𝐒𝐩𝐞𝐞𝐝",
                callback_data="ev_speed"
            )
        ],
        [
            InlineKeyboardButton(
                "𝐇𝐨𝐰 𝐄𝐕 𝐓𝐫𝐚𝐢𝐧𝐢𝐧𝐠 𝐖𝐨𝐫𝐤𝐬",
                callback_data="ev_how"
            )
        ]
    ]

    await update.message.reply_text(
        "🏋️ 𝐏𝐨𝐤𝐞́𝐦𝐨𝐧 𝐄𝐕 𝐓𝐫𝐚𝐢𝐧𝐢𝐧𝐠 𝐆𝐮𝐢𝐝𝐞\n\n"
        "Each Pokémon defeated gives Effort Values (EVs) "
        "that boost your Pokémon's stats.\n\n"
        "Pokémon listed here give 3 EVs in their respective "
        "stat when defeated.\n\n"
        "Select a stat to see which Pokémon to battle for "
        "EV training:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# OFFICIAL TM DATA
# =========================================================

TM_PAGES = {

    1: """
🏆 𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌 𝐋𝐢𝐬𝐭 (Page 1/6)

• TM001 - Take Down
  ➥ PWR: 90 | Acc: 85 | Type: Physical

• TM002 - Charm
  ➥ PWR: — | Acc: 100 | Type: Status

• TM003 - Fake Tears
  ➥ PWR: — | Acc: 100 | Type: Status

• TM004 - Agility
  ➥ PWR: — | Acc: 100 | Type: Status

• TM005 - Mud-Slap
  ➥ PWR: 20 | Acc: 100 | Type: Special

• TM006 - Scary Face
  ➥ PWR: — | Acc: 100 | Type: Status

• TM007 - Protect
  ➥ PWR: — | Acc: 100 | Type: Status

• TM008 - Fire Fang
  ➥ PWR: 65 | Acc: 95 | Type: Physical

• TM009 - Thunder Fang
  ➥ PWR: 65 | Acc: 95 | Type: Physical

• TM010 - Ice Fang
  ➥ PWR: 65 | Acc: 95 | Type: Physical

• TM011 - Water Pulse
  ➥ PWR: 60 | Acc: 100 | Type: Special

• TM012 - Low Kick
  ➥ PWR: — | Acc: 100 | Type: Physical

• TM013 - Acid Spray
  ➥ PWR: 40 | Acc: 100 | Type: Special

• TM014 - Acrobatics
  ➥ PWR: 55 | Acc: 100 | Type: Physical

• TM015 - Struggle Bug
  ➥ PWR: 50 | Acc: 100 | Type: Special

• TM016 - Psybeam
  ➥ PWR: 65 | Acc: 100 | Type: Special

• TM017 - Confuse Ray
  ➥ PWR: — | Acc: 100 | Type: Status

• TM018 - Thief
  ➥ PWR: 60 | Acc: 100 | Type: Physical

• TM019 - Disarming Voice
  ➥ PWR: 40 | Acc: 100 | Type: Special

• TM020 - Trailblaze
  ➥ PWR: 50 | Acc: 100 | Type: Physical

• TM021 - Pounce
  ➥ PWR: 50 | Acc: 100 | Type: Physical

• TM022 - Chilling Water
  ➥ PWR: 50 | Acc: 100 | Type: Special

• TM023 - Charge Beam
  ➥ PWR: 50 | Acc: 90 | Type: Special

• TM024 - Fire Spin
  ➥ PWR: 35 | Acc: 85 | Type: Special

• TM025 - Facade
  ➥ PWR: 70 | Acc: 100 | Type: Physical

• TM026 - Poison Tail
  ➥ PWR: 50 | Acc: 100 | Type: Physical

• TM027 - Aerial Ace
  ➥ PWR: 60 | Acc: 100 | Type: Physical

• TM028 - Bulldoze
  ➥ PWR: 60 | Acc: 100 | Type: Physical

• TM029 - Hex
  ➥ PWR: 65 | Acc: 100 | Type: Special

• TM030 - Snarl
  ➥ PWR: 55 | Acc: 95 | Type: Special
""",

    2: """
🏆 𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌 𝐋𝐢𝐬𝐭 (Page 2/6)

• TM031 - Metal Claw
  ➥ PWR: 50 | Acc: 95 | Type: Physical

• TM032 - Swift
  ➥ PWR: 60 | Acc: 100 | Type: Special

• TM033 - Magical Leaf
  ➥ PWR: 60 | Acc: 100 | Type: Special

• TM034 - Icy Wind
  ➥ PWR: 55 | Acc: 95 | Type: Special

• TM035 - Mud Shot
  ➥ PWR: 55 | Acc: 95 | Type: Special

• TM036 - Rock Tomb
  ➥ PWR: 60 | Acc: 95 | Type: Physical

• TM037 - Draining Kiss
  ➥ PWR: 50 | Acc: 100 | Type: Special

• TM038 - Flame Charge
  ➥ PWR: 50 | Acc: 100 | Type: Physical

• TM039 - Low Sweep
  ➥ PWR: 65 | Acc: 100 | Type: Physical

• TM040 - Air Cutter
  ➥ PWR: 60 | Acc: 95 | Type: Special

• TM041 - Stored Power
  ➥ PWR: 20 | Acc: 100 | Type: Special

• TM042 - Night Shade
  ➥ PWR: — | Acc: 100 | Type: Special

• TM043 - Foul Play
  ➥ PWR: 95 | Acc: 100 | Type: Physical

• TM044 - Dragon Tail
  ➥ PWR: 60 | Acc: 90 | Type: Physical

• TM045 - Venoshock
  ➥ PWR: 65 | Acc: 100 | Type: Special

• TM046 - Avalanche
  ➥ PWR: 60 | Acc: 100 | Type: Physical

• TM047 - Endure
  ➥ PWR: — | Acc: 100 | Type: Status

• TM048 - Volt Switch
  ➥ PWR: 70 | Acc: 100 | Type: Special

• TM049 - Sunny Day
  ➥ PWR: — | Acc: 100 | Type: Status

• TM050 - Rain Dance
  ➥ PWR: — | Acc: 100 | Type: Status

• TM051 - Sandstorm
  ➥ PWR: — | Acc: 100 | Type: Status

• TM052 - Snowscape
  ➥ PWR: — | Acc: 100 | Type: Status

• TM053 - Smart Strike
  ➥ PWR: 70 | Acc: 100 | Type: Physical

• TM054 - Psyshock
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM055 - Dig
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM056 - Bullet Seed
  ➥ PWR: 25 | Acc: 100 | Type: Physical

• TM057 - False Swipe
  ➥ PWR: 40 | Acc: 100 | Type: Physical

• TM058 - Brick Break
  ➥ PWR: 75 | Acc: 100 | Type: Physical

• TM059 - Zen Headbutt
  ➥ PWR: 80 | Acc: 90 | Type: Physical

• TM060 - U-turn
  ➥ PWR: 70 | Acc: 100 | Type: Physical
""",

    3: """
🏆 𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌 𝐋𝐢𝐬𝐭 (Page 3/6)

• TM061 - Shadow Claw
  ➥ PWR: 70 | Acc: 100 | Type: Physical

• TM062 - Foul Play
  ➥ PWR: 95 | Acc: 100 | Type: Physical

• TM063 - Psychic Fangs
  ➥ PWR: 85 | Acc: 100 | Type: Physical

• TM064 - Bulk Up
  ➥ PWR: — | Acc: 100 | Type: Status

• TM065 - Air Slash
  ➥ PWR: 75 | Acc: 95 | Type: Special

• TM066 - Body Slam
  ➥ PWR: 85 | Acc: 100 | Type: Physical

• TM067 - Fire Punch
  ➥ PWR: 75 | Acc: 100 | Type: Physical

• TM068 - Thunder Punch
  ➥ PWR: 75 | Acc: 100 | Type: Physical

• TM069 - Ice Punch
  ➥ PWR: 75 | Acc: 100 | Type: Physical

• TM070 - Sleep Talk
  ➥ PWR: — | Acc: 100 | Type: Status

• TM071 - Seed Bomb
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM072 - Electro Ball
  ➥ PWR: — | Acc: 100 | Type: Special

• TM073 - Drain Punch
  ➥ PWR: 75 | Acc: 100 | Type: Physical

• TM074 - Reflect
  ➥ PWR: — | Acc: 100 | Type: Status

• TM075 - Light Screen
  ➥ PWR: — | Acc: 100 | Type: Status

• TM076 - Rock Blast
  ➥ PWR: 25 | Acc: 90 | Type: Physical

• TM077 - Waterfall
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM078 - Dragon Claw
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM079 - Dazzling Gleam
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM080 - Metronome
  ➥ PWR: — | Acc: 100 | Type: Status

• TM081 - Grass Knot
  ➥ PWR: — | Acc: 100 | Type: Special

• TM082 - Thunder Wave
  ➥ PWR: — | Acc: 90 | Type: Status

• TM083 - Poison Jab
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM084 - Stomping Tantrum
  ➥ PWR: 75 | Acc: 100 | Type: Physical

• TM085 - Rest
  ➥ PWR: — | Acc: 100 | Type: Status

• TM086 - Rock Slide
  ➥ PWR: 75 | Acc: 90 | Type: Physical

• TM087 - Taunt
  ➥ PWR: — | Acc: 100 | Type: Status

• TM088 - Swords Dance
  ➥ PWR: — | Acc: 100 | Type: Status

• TM089 - Body Press
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM090 - Spikes
  ➥ PWR: — | Acc: 100 | Type: Status
""",

    4: """
🏆 𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌 𝐋𝐢𝐬𝐭 (Page 4/6)

• TM091 - Toxic Spikes
  ➥ PWR: — | Acc: 100 | Type: Status

• TM092 - Imprison
  ➥ PWR: — | Acc: 100 | Type: Status

• TM093 - Flash Cannon
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM094 - Dark Pulse
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM095 - Leech Life
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM096 - Eerie Impulse
  ➥ PWR: — | Acc: 100 | Type: Status

• TM097 - Fly
  ➥ PWR: 90 | Acc: 95 | Type: Physical

• TM098 - Skill Swap
  ➥ PWR: — | Acc: 100 | Type: Status

• TM099 - Iron Head
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM100 - Dragon Dance
  ➥ PWR: — | Acc: 100 | Type: Status

• TM101 - Power Gem
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM102 - Gunk Shot
  ➥ PWR: 120 | Acc: 80 | Type: Physical

• TM103 - Substitute
  ➥ PWR: — | Acc: 100 | Type: Status

• TM104 - Iron Defense
  ➥ PWR: — | Acc: 100 | Type: Status

• TM105 - X-Scissor
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM106 - Drill Run
  ➥ PWR: 80 | Acc: 95 | Type: Physical

• TM107 - Will-O-Wisp
  ➥ PWR: — | Acc: 85 | Type: Status

• TM108 - Crunch
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM109 - Trick
  ➥ PWR: — | Acc: 100 | Type: Status

• TM110 - Liquidation
  ➥ PWR: 85 | Acc: 100 | Type: Physical

• TM111 - Giga Drain
  ➥ PWR: 75 | Acc: 100 | Type: Special

• TM112 - Aura Sphere
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM113 - Tailwind
  ➥ PWR: — | Acc: 100 | Type: Status

• TM114 - Shadow Ball
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM115 - Dragon Pulse
  ➥ PWR: 85 | Acc: 100 | Type: Special

• TM116 - Stealth Rock
  ➥ PWR: — | Acc: 100 | Type: Status

• TM117 - Hyper Voice
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM118 - Heat Wave
  ➥ PWR: 95 | Acc: 90 | Type: Special

• TM119 - Energy Ball
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM120 - Psychic
  ➥ PWR: 90 | Acc: 100 | Type: Special
""",

    5: """
🏆 𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌 𝐋𝐢𝐬𝐭 (Page 5/6)

• TM121 - Heavy Slam
  ➥ PWR: — | Acc: 100 | Type: Physical

• TM122 - Encore
  ➥ PWR: — | Acc: 100 | Type: Status

• TM123 - Surf
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM124 - Ice Spinner
  ➥ PWR: 80 | Acc: 100 | Type: Physical

• TM125 - Flamethrower
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM126 - Thunderbolt
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM127 - Play Rough
  ➥ PWR: 90 | Acc: 90 | Type: Physical

• TM128 - Amnesia
  ➥ PWR: — | Acc: 100 | Type: Status

• TM129 - Calm Mind
  ➥ PWR: — | Acc: 100 | Type: Status

• TM130 - Helping Hand
  ➥ PWR: — | Acc: 100 | Type: Status

• TM131 - Pollen Puff
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM132 - Baton Pass
  ➥ PWR: — | Acc: 100 | Type: Status

• TM133 - Earth Power
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM134 - Reversal
  ➥ PWR: — | Acc: 100 | Type: Physical

• TM135 - Ice Beam
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM136 - Electric Terrain
  ➥ PWR: — | Acc: 100 | Type: Status

• TM137 - Grassy Terrain
  ➥ PWR: — | Acc: 100 | Type: Status

• TM138 - Psychic Terrain
  ➥ PWR: — | Acc: 100 | Type: Status

• TM139 - Misty Terrain
  ➥ PWR: — | Acc: 100 | Type: Status

• TM140 - Nasty Plot
  ➥ PWR: — | Acc: 100 | Type: Status

• TM141 - Fire Blast
  ➥ PWR: 110 | Acc: 85 | Type: Special

• TM142 - Hydro Pump
  ➥ PWR: 110 | Acc: 80 | Type: Special

• TM143 - Blizzard
  ➥ PWR: 110 | Acc: 70 | Type: Special

• TM144 - Fire Pledge
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM145 - Water Pledge
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM146 - Grass Pledge
  ➥ PWR: 80 | Acc: 100 | Type: Special

• TM147 - Wild Charge
  ➥ PWR: 90 | Acc: 100 | Type: Physical

• TM148 - Sludge Bomb
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM149 - Earthquake
  ➥ PWR: 100 | Acc: 100 | Type: Physical

• TM150 - Stone Edge
  ➥ PWR: 100 | Acc: 80 | Type: Physical
""",

    6: """
🏆 𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌 𝐋𝐢𝐬𝐭 (Page 6/6)

• TM151 - Phantom Force
  ➥ PWR: 90 | Acc: 100 | Type: Physical

• TM152 - Giga Impact
  ➥ PWR: 150 | Acc: 90 | Type: Physical

• TM153 - Blast Burn
  ➥ PWR: 150 | Acc: 90 | Type: Special

• TM154 - Hurricane
  ➥ PWR: 110 | Acc: 70 | Type: Special

• TM155 - Frenzy Plant
  ➥ PWR: 150 | Acc: 90 | Type: Special

• TM156 - Outrage
  ➥ PWR: 120 | Acc: 100 | Type: Physical

• TM157 - Overheat
  ➥ PWR: 130 | Acc: 90 | Type: Special

• TM158 - Focus Blast
  ➥ PWR: 120 | Acc: 70 | Type: Special

• TM159 - Leaf Storm
  ➥ PWR: 130 | Acc: 90 | Type: Special

• TM160 - Hydro Cannon
  ➥ PWR: 150 | Acc: 90 | Type: Special

• TM161 - Trick Room
  ➥ PWR: — | Acc: 100 | Type: Status

• TM162 - Bug Buzz
  ➥ PWR: 90 | Acc: 100 | Type: Special

• TM163 - Hyper Beam
  ➥ PWR: 150 | Acc: 90 | Type: Special

• TM164 - Brave Bird
  ➥ PWR: 120 | Acc: 100 | Type: Physical

• TM165 - Flare Blitz
  ➥ PWR: 120 | Acc: 100 | Type: Physical

• TM166 - Thunder
  ➥ PWR: 110 | Acc: 70 | Type: Special

• TM167 - Close Combat
  ➥ PWR: 120 | Acc: 100 | Type: Physical

• TM168 - Solar Beam
  ➥ PWR: 120 | Acc: 100 | Type: Special

• TM169 - Draco Meteor
  ➥ PWR: 130 | Acc: 90 | Type: Special

• TM170 - Steel Beam
  ➥ PWR: 140 | Acc: 95 | Type: Special

• TM171 - Tera Blast
  ➥ PWR: 80 | Acc: 100 | Type: Special
"""
}


# =========================================================
# DATATM
# =========================================================

async def datatm(update, context):

    keyboard = [
        [
            InlineKeyboardButton(
                "𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌𝐬",
                callback_data="tm_page_1"
            )
        ]
    ]

    await update.message.reply_text(
        "🏆 𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐓𝐌 𝐋𝐢𝐬𝐭",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# TM PAGE CALLBACK
# =========================================================

async def tm_callback(update, context):

    query = update.callback_query
    await query.answer()

    page = int(query.data.split("_")[-1])

    text = TM_PAGES.get(page)

    if not text:
        return

    keyboard = []

    navigation = []

    if page > 1:
        navigation.append(
            InlineKeyboardButton(
                "◀️ 𝐁𝐚𝐜𝐤",
                callback_data=f"tm_page_{page - 1}"
            )
        )

    if page < 6:
        navigation.append(
            InlineKeyboardButton(
                "𝐍𝐞𝐱𝐭 ▶️",
                callback_data=f"tm_page_{page + 1}"
            )
        )

    if navigation:
        keyboard.append(navigation)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# POKEBALLS GUIDE
# =========================================================

async def pokeballs(update, context):

    await update.message.reply_text(
        "🎯 𝐏𝐨𝐤𝐞́ 𝐁𝐚𝐥𝐥𝐬 𝐆𝐮𝐢𝐝𝐞\n\n"
        "𝐑𝐞𝐠𝐮𝐥𝐚𝐫 𝐁𝐚𝐥𝐥: Multiplier: x1\n\n"
        "𝐆𝐫𝐞𝐚𝐭 𝐁𝐚𝐥𝐥: Multiplier: x1.5\n\n"
        "𝐔𝐥𝐭𝐫𝐚 𝐁𝐚𝐥𝐥: Multiplier: x2\n\n"
        "𝐋𝐞𝐯𝐞𝐥 𝐁𝐚𝐥𝐥: Multiplier:\n"
        "• x8 if your Pokémon's level is ≥ 4× wild Pokémon\n"
        "• x4 if ≥ 2× wild Pokémon\n"
        "• x2 if higher than wild Pokémon\n"
        "• x1 otherwise\n\n"
        "𝐅𝐚𝐬𝐭 𝐁𝐚𝐥𝐥: Multiplier: x4 if base speed ≥ 100 "
        "(or Magnemite, Grimer, Tangela), x1 otherwise\n\n"
        "𝐑𝐞𝐩𝐞𝐚𝐭 𝐁𝐚𝐥𝐥: Multiplier: x3.5 if you have previously "
        "caught the Pokémon, x1 otherwise\n\n"
        "𝐍𝐞𝐬𝐭 𝐁𝐚𝐥𝐥: Multiplier: Works better on low level "
        "Pokémon (up to x4)\n\n"
        "𝐍𝐞𝐭 𝐁𝐚𝐥𝐥: Multiplier: x3.5 if the Pokémon is Water "
        "or Bug type, x1 otherwise\n\n"
        "𝐐𝐮𝐢𝐜𝐤 𝐁𝐚𝐥𝐥: Multiplier: x5 if used in the first "
        "turn, x1 otherwise\n\n"
        "𝐌𝐚𝐬𝐭𝐞𝐫 𝐁𝐚𝐥𝐥: Multiplier: x255 "
        "(100% capture guaranteed)\n\n"
        "𝐒𝐚𝐟𝐚𝐫𝐢 𝐁𝐚𝐥𝐥: Multiplier: x1.5 "
        "(only used in Safari zone)"
    )


# =========================================================
# MOVE DATABASE
# =========================================================

MOVE_DATA = {}


# =========================================================
# ADD TM MOVE
# =========================================================

def add_tm_move(
    name,
    move_type,
    power,
    accuracy,
    category
):
    MOVE_DATA[name.lower()] = {
        "name": name,
        "type": move_type,
        "power": power,
        "accuracy": accuracy,
        "category": category,
        "pp": None,
        "priority": 0,
        "target": "selected-pokemon",
        "description": "Move data available."
    }


# =========================================================
# TM MOVES
# =========================================================

add_tm_move("Take Down", "Normal", 90, 85, "Physical")
add_tm_move("Charm", "Fairy", None, 100, "Status")
add_tm_move("Fake Tears", "Dark", None, 100, "Status")
add_tm_move("Agility", "Psychic", None, 100, "Status")
add_tm_move("Mud-Slap", "Ground", 20, 100, "Special")
add_tm_move("Scary Face", "Normal", None, 100, "Status")
add_tm_move("Protect", "Normal", None, 100, "Status")
add_tm_move("Fire Fang", "Fire", 65, 95, "Physical")
add_tm_move("Thunder Fang", "Electric", 65, 95, "Physical")
add_tm_move("Ice Fang", "Ice", 65, 95, "Physical")
add_tm_move("Water Pulse", "Water", 60, 100, "Special")
add_tm_move("Low Kick", "Fighting", None, 100, "Physical")
add_tm_move("Acid Spray", "Poison", 40, 100, "Special")
add_tm_move("Acrobatics", "Flying", 55, 100, "Physical")
add_tm_move("Struggle Bug", "Bug", 50, 100, "Special")
add_tm_move("Psybeam", "Psychic", 65, 100, "Special")
add_tm_move("Confuse Ray", "Ghost", None, 100, "Status")
add_tm_move("Thief", "Dark", 60, 100, "Physical")
add_tm_move("Disarming Voice", "Fairy", 40, 100, "Special")
add_tm_move("Trailblaze", "Grass", 50, 100, "Physical")
add_tm_move("Pounce", "Bug", 50, 100, "Physical")
add_tm_move("Chilling Water", "Water", 50, 100, "Special")
add_tm_move("Charge Beam", "Electric", 50, 90, "Special")
add_tm_move("Fire Spin", "Fire", 35, 85, "Special")
add_tm_move("Facade", "Normal", 70, 100, "Physical")
add_tm_move("Poison Tail", "Poison", 50, 100, "Physical")
add_tm_move("Aerial Ace", "Flying", 60, None, "Physical")
add_tm_move("Bulldoze", "Ground", 60, 100, "Physical")
add_tm_move("Hex", "Ghost", 65, 100, "Special")
add_tm_move("Snarl", "Dark", 55, 95, "Special")

add_tm_move("Metal Claw", "Steel", 50, 95, "Physical")
add_tm_move("Swift", "Normal", 60, None, "Special")
add_tm_move("Magical Leaf", "Grass", 60, None, "Special")
add_tm_move("Icy Wind", "Ice", 55, 95, "Special")
add_tm_move("Mud Shot", "Ground", 55, 95, "Special")
add_tm_move("Rock Tomb", "Rock", 60, 95, "Physical")
add_tm_move("Draining Kiss", "Fairy", 50, 100, "Special")
add_tm_move("Flame Charge", "Fire", 50, 100, "Physical")
add_tm_move("Low Sweep", "Fighting", 65, 100, "Physical")
add_tm_move("Air Cutter", "Flying", 60, 95, "Special")
add_tm_move("Stored Power", "Psychic", 20, 100, "Special")
add_tm_move("Night Shade", "Ghost", None, 100, "Special")
add_tm_move("Foul Play", "Dark", 95, 100, "Physical")
add_tm_move("Dragon Tail", "Dragon", 60, 90, "Physical")
add_tm_move("Venoshock", "Poison", 65, 100, "Special")
add_tm_move("Avalanche", "Ice", 60, 100, "Physical")
add_tm_move("Endure", "Normal", None, None, "Status")
add_tm_move("Volt Switch", "Electric", 70, 100, "Special")
add_tm_move("Sunny Day", "Fire", None, None, "Status")
add_tm_move("Rain Dance", "Water", None, None, "Status")
add_tm_move("Sandstorm", "Rock", None, None, "Status")
add_tm_move("Snowscape", "Ice", None, None, "Status")
add_tm_move("Smart Strike", "Steel", 70, None, "Physical")
add_tm_move("Psyshock", "Psychic", 80, 100, "Special")
add_tm_move("Dig", "Ground", 80, 100, "Physical")
add_tm_move("Bullet Seed", "Grass", 25, 100, "Physical")
add_tm_move("False Swipe", "Normal", 40, 100, "Physical")
add_tm_move("Brick Break", "Fighting", 75, 100, "Physical")
add_tm_move("Zen Headbutt", "Psychic", 80, 90, "Physical")
add_tm_move("U-turn", "Bug", 70, 100, "Physical")

add_tm_move("Shadow Claw", "Ghost", 70, 100, "Physical")
add_tm_move("Psychic Fangs", "Psychic", 85, 100, "Physical")
add_tm_move("Bulk Up", "Fighting", None, None, "Status")
add_tm_move("Air Slash", "Flying", 75, 95, "Special")
add_tm_move("Body Slam", "Normal", 85, 100, "Physical")
add_tm_move("Fire Punch", "Fire", 75, 100, "Physical")
add_tm_move("Thunder Punch", "Electric", 75, 100, "Physical")
add_tm_move("Ice Punch", "Ice", 75, 100, "Physical")
add_tm_move("Sleep Talk", "Normal", None, None, "Status")
add_tm_move("Seed Bomb", "Grass", 80, 100, "Physical")
add_tm_move("Electro Ball", "Electric", None, 100, "Special")
add_tm_move("Drain Punch", "Fighting", 75, 100, "Physical")
add_tm_move("Reflect", "Psychic", None, None, "Status")
add_tm_move("Light Screen", "Psychic", None, None, "Status")
add_tm_move("Rock Blast", "Rock", 25, 90, "Physical")
add_tm_move("Waterfall", "Water", 80, 100, "Physical")
add_tm_move("Dragon Claw", "Dragon", 80, 100, "Physical")
add_tm_move("Dazzling Gleam", "Fairy", 80, 100, "Special")
add_tm_move("Metronome", "Normal", None, None, "Status")
add_tm_move("Grass Knot", "Grass", None, 100, "Special")
add_tm_move("Thunder Wave", "Electric", None, 90, "Status")
add_tm_move("Poison Jab", "Poison", 80, 100, "Physical")
add_tm_move("Stomping Tantrum", "Ground", 75, 100, "Physical")
add_tm_move("Rest", "Psychic", None, None, "Status")
add_tm_move("Rock Slide", "Rock", 75, 90, "Physical")
add_tm_move("Taunt", "Dark", None, 100, "Status")
add_tm_move("Swords Dance", "Normal", None, None, "Status")
add_tm_move("Body Press", "Fighting", 80, 100, "Physical")
add_tm_move("Spikes", "Ground", None, None, "Status")

add_tm_move("Toxic Spikes", "Poison", None, None, "Status")
add_tm_move("Imprison", "Psychic", None, None, "Status")
add_tm_move("Flash Cannon", "Steel", 80, 100, "Special")
add_tm_move("Dark Pulse", "Dark", 80, 100, "Special")
add_tm_move("Leech Life", "Bug", 80, 100, "Physical")
add_tm_move("Eerie Impulse", "Electric", None, 100, "Status")
add_tm_move("Fly", "Flying", 90, 95, "Physical")
add_tm_move("Skill Swap", "Psychic", None, None, "Status")
add_tm_move("Iron Head", "Steel", 80, 100, "Physical")
add_tm_move("Dragon Dance", "Dragon", None, None, "Status")
add_tm_move("Power Gem", "Rock", 80, 100, "Special")
add_tm_move("Gunk Shot", "Poison", 120, 80, "Physical")
add_tm_move("Substitute", "Normal", None, None, "Status")
add_tm_move("Iron Defense", "Steel", None, None, "Status")
add_tm_move("X-Scissor", "Bug", 80, 100, "Physical")
add_tm_move("Drill Run", "Ground", 80, 95, "Physical")
add_tm_move("Will-O-Wisp", "Fire", None, 85, "Status")
add_tm_move("Crunch", "Dark", 80, 100, "Physical")
add_tm_move("Trick", "Psychic", None, 100, "Status")
add_tm_move("Liquidation", "Water", 85, 100, "Physical")
add_tm_move("Giga Drain", "Grass", 75, 100, "Special")
add_tm_move("Aura Sphere", "Fighting", 80, None, "Special")
add_tm_move("Tailwind", "Flying", None, None, "Status")
add_tm_move("Shadow Ball", "Ghost", 80, 100, "Special")
add_tm_move("Dragon Pulse", "Dragon", 85, 100, "Special")
add_tm_move("Stealth Rock", "Rock", None, None, "Status")
add_tm_move("Hyper Voice", "Normal", 90, 100, "Special")
add_tm_move("Heat Wave", "Fire", 95, 90, "Special")
add_tm_move("Energy Ball", "Grass", 90, 100, "Special")
add_tm_move("Psychic", "Psychic", 90, 100, "Special")

add_tm_move("Heavy Slam", "Steel", None, 100, "Physical")
add_tm_move("Encore", "Normal", None, 100, "Status")
add_tm_move("Surf", "Water", 90, 100, "Special")
add_tm_move("Ice Spinner", "Ice", 80, 100, "Physical")
add_tm_move("Flamethrower", "Fire", 90, 100, "Special")
add_tm_move("Thunderbolt", "Electric", 90, 100, "Special")
add_tm_move("Play Rough", "Fairy", 90, 90, "Physical")
add_tm_move("Amnesia", "Psychic", None, None, "Status")
add_tm_move("Calm Mind", "Psychic", None, None, "Status")
add_tm_move("Helping Hand", "Normal", None, None, "Status")
add_tm_move("Pollen Puff", "Bug", 90, 100, "Special")
add_tm_move("Baton Pass", "Normal", None, None, "Status")
add_tm_move("Earth Power", "Ground", 90, 100, "Special")
add_tm_move("Reversal", "Fighting", None, 100, "Physical")
add_tm_move("Ice Beam", "Ice", 90, 100, "Special")
add_tm_move("Electric Terrain", "Electric", None, None, "Status")
add_tm_move("Grassy Terrain", "Grass", None, None, "Status")
add_tm_move("Psychic Terrain", "Psychic", None, None, "Status")
add_tm_move("Misty Terrain", "Fairy", None, None, "Status")
add_tm_move("Nasty Plot", "Dark", None, None, "Status")
add_tm_move("Fire Blast", "Fire", 110, 85, "Special")
add_tm_move("Hydro Pump", "Water", 110, 80, "Special")
add_tm_move("Blizzard", "Ice", 110, 70, "Special")
add_tm_move("Fire Pledge", "Fire", 80, 100, "Special")
add_tm_move("Water Pledge", "Water", 80, 100, "Special")
add_tm_move("Grass Pledge", "Grass", 80, 100, "Special")
add_tm_move("Wild Charge", "Electric", 90, 100, "Physical")
add_tm_move("Sludge Bomb", "Poison", 90, 100, "Special")
add_tm_move("Earthquake", "Ground", 100, 100, "Physical")
add_tm_move("Stone Edge", "Rock", 100, 80, "Physical")

add_tm_move("Phantom Force", "Ghost", 90, 100, "Physical")
add_tm_move("Giga Impact", "Normal", 150, 90, "Physical")
add_tm_move("Blast Burn", "Fire", 150, 90, "Special")
add_tm_move("Hurricane", "Flying", 110, 70, "Special")
add_tm_move("Frenzy Plant", "Grass", 150, 90, "Special")
add_tm_move("Outrage", "Dragon", 120, 100, "Physical")
add_tm_move("Overheat", "Fire", 130, 90, "Special")
add_tm_move("Focus Blast", "Fighting", 120, 70, "Special")
add_tm_move("Leaf Storm", "Grass", 130, 90, "Special")
add_tm_move("Hydro Cannon", "Water", 150, 90, "Special")
add_tm_move("Trick Room", "Psychic", None, None, "Status")
add_tm_move("Bug Buzz", "Bug", 90, 100, "Special")
add_tm_move("Hyper Beam", "Normal", 150, 90, "Special")
add_tm_move("Brave Bird", "Flying", 120, 100, "Physical")
add_tm_move("Flare Blitz", "Fire", 120, 100, "Physical")
add_tm_move("Thunder", "Electric", 110, 70, "Special")
add_tm_move("Close Combat", "Fighting", 120, 100, "Physical")
add_tm_move("Solar Beam", "Grass", 120, 100, "Special")
add_tm_move("Draco Meteor", "Dragon", 130, 90, "Special")
add_tm_move("Steel Beam", "Steel", 140, 95, "Special")
add_tm_move("Tera Blast", "Normal", 80, 100, "Special")


# =========================================================
# MOVE COMMAND
# =========================================================

async def move(update, context):

    if not context.args:
        await update.message.reply_text(
            "⚠️ 𝐏𝐥𝐞𝐚𝐬𝐞 𝐞𝐧𝐭𝐞𝐫 𝐚 𝐦𝐨𝐯𝐞 𝐧𝐚𝐦𝐞.\n\n"
            "𝐄𝐱𝐚𝐦𝐩𝐥𝐞:\n"
            "/move Crunch"
        )
        return

    move_name = " ".join(context.args).strip().lower()

    data = MOVE_DATA.get(move_name)

    if not data:
        await update.message.reply_text(
            f"❌ 𝐌𝐨𝐯𝐞 𝐧𝐨𝐭 𝐟𝐨𝐮𝐧𝐝.\n\n"
            f"𝐒𝐞𝐚𝐫𝐜𝐡𝐞𝐝: {move_name.title()}"
        )
        return

    power = data["power"] if data["power"] is not None else "—"
    accuracy = (
        data["accuracy"]
        if data["accuracy"] is not None
        else "—"
    )

    await update.message.reply_text(
        f"⚔️ 𝐌𝐨𝐯𝐞: {data['name']}\n\n"
        f"🔹 𝐓𝐲𝐩𝐞: {data['type']}\n"
        f"🔹 𝐂𝐚𝐭𝐞𝐠𝐨𝐫𝐲: {data['category']}\n"
        f"🔹 𝐏𝐨𝐰𝐞𝐫: {power}\n"
        f"🔹 𝐀𝐜𝐜𝐮𝐫𝐚𝐜𝐲: {accuracy}\n"
        f"🔹 𝐏𝐏: {data['pp'] if data['pp'] else '—'}\n"
        f"🔹 𝐏𝐫𝐢𝐨𝐫𝐢𝐭𝐲: {data['priority']}\n"
        f"🔹 𝐓𝐚𝐫𝐠𝐞𝐭: {data['target']}\n\n"
        f"📝 {data['description']}"
    )


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
# BAG / INVENTORY
# =========================================================

async def bag(update, context):

    keyboard = [
        [
            InlineKeyboardButton(
                "֎ 𝐌𝐞𝐠𝐚 𝐒𝐭𝐨𝐧𝐞",
                callback_data="bag_mega"
            ),
            InlineKeyboardButton(
                "⌘ 𝐈𝐭𝐞𝐦𝐬",
                callback_data="bag_items"
            )
        ],
        [
            InlineKeyboardButton(
                "🀪 𝐓𝐮𝐭𝐨𝐫𝐬",
                callback_data="bag_tutors"
            ),
            InlineKeyboardButton(
                "💿 𝐓𝐌𝐬",
                callback_data="bag_tms"
            )
        ],
        [
            InlineKeyboardButton(
                "✪ 𝐙-𝐂𝐫𝐲𝐬𝐭𝐚𝐥",
                callback_data="bag_zcrystal"
            ),
            InlineKeyboardButton(
                "⎉ 𝐏𝐨𝐤𝐞𝐛𝐚𝐥𝐥𝐬",
                callback_data="bag_pokeballs"
            )
        ]
    ]

    await update.message.reply_text(
        "⍛ 𝐈𝐧𝐯𝐞𝐧𝐭𝐨𝐫𝐲 𝐈𝐭𝐞𝐦𝐬 :\n\n"
        "⤷ ⛁ ✘ 𝐓𝐨𝐤𝐞𝐧𝐬 :\n"
        "⤷ ⛁ 𝐏𝐨𝐤𝐞𝐜𝐨𝐢𝐧𝐬 :",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# BAG CALLBACKS
# =========================================================

async def bag_callback(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data

    # -------------------------
    # MAIN BAG PAGE
    # -------------------------
    if data == "bag_main":
        text = (
            "🎒 𝐈𝐧𝐯𝐞𝐧𝐭𝐨𝐫𝐲 𝐈𝐭𝐞𝐦𝐬 :\n\n"
            "⤷⛁ ✘ 𝐓𝐨𝐤𝐞𝐧𝐬 :\n"
            "⤷⛁ 𝐏𝐨𝐤𝐞𝐜𝐨𝐢𝐧𝐬 :"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "֎ 𝐌𝐞𝐠𝐚 𝐒𝐭𝐨𝐧𝐞",
                    callback_data="bag_mega"
                ),
                InlineKeyboardButton(
                    "⌘ 𝐈𝐭𝐞𝐦𝐬",
                    callback_data="bag_items"
                )
            ],
            [
                InlineKeyboardButton(
                    "🀪 𝐓𝐮𝐭𝐨𝐫𝐬",
                    callback_data="bag_tutors"
                ),
                InlineKeyboardButton(
                    "💿 𝐓𝐌𝐬",
                    callback_data="bag_tms"
                )
            ],
            [
                InlineKeyboardButton(
                    "✪ 𝐙-𝐂𝐫𝐲𝐬𝐭𝐚𝐥",
                    callback_data="bag_zcrystal"
                ),
                InlineKeyboardButton(
                    "⎉ 𝐏𝐨𝐤𝐞𝐛𝐚𝐥𝐥𝐬",
                    callback_data="bag_pokeballs"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # -------------------------
    # SECTION NAMES
    # -------------------------
    sections = {
        "bag_mega": "֎ 𝐌𝐞𝐠𝐚 𝐒𝐭𝐨𝐧𝐞𝐬",
        "bag_items": "⌘ 𝐈𝐭𝐞𝐦𝐬",
        "bag_tutors": "🀪 𝐓𝐮𝐭𝐨𝐫𝐬",
        "bag_tms": "💿 𝐓𝐌𝐬",
        "bag_zcrystal": "✪ 𝐙-𝐂𝐫𝐲𝐬𝐭𝐚𝐥𝐬",
        "bag_pokeballs": "⎉ 𝐏𝐨𝐤𝐞𝐛𝐚𝐥𝐥𝐬"
    }

    if data in sections:
        text = (
            f"{sections[data]} :\n\n"
            "⤷ 𝝬 𝐍𝐨 𝐢𝐭𝐞𝐦𝐬 𝐚𝐯𝐚𝐢𝐥𝐚𝐛𝐥𝐞."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "◀ 𝐁𝐚𝐜𝐤",
                    callback_data="bag_main"
                )
            ]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
       

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

    keyboard = [
        [
            InlineKeyboardButton(
                "𝐒𝐭𝐚𝐫𝐭 𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐉𝐨𝐮𝐫𝐧𝐞𝐲",
                callback_data="start_pokemon_journey"
            )
        ],
        [
            InlineKeyboardButton(
                "𝐔𝐩𝐝𝐚𝐭𝐞𝐬",
                callback_data="start_updates"
            ),
            InlineKeyboardButton(
                "𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬",
                callback_data="start_commands"
            )
        ],
        [
            InlineKeyboardButton(
                "𝐀𝐝𝐝 𝐦𝐞 𝐭𝐨 𝐠𝐫𝐨𝐮𝐩",
                url=f"https://t.me/{context.bot.username}?startgroup=true"
            )
        ]
    ]
    
    await update.message.reply_text(
        "╭━━━━━━━━━━━━━━━━━╮\n"
        "         𝛸𝛴𝛤𝛸𝛴𝑆\n"
        "╰━━━━━━━━━━━━━━━━━╯\n"
        "𝐀𝐧 𝐨𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐛𝐨𝐭 𝐛𝐮𝐢𝐥𝐭 𝐭𝐨 𝐛𝐫𝐢𝐧𝐠\n"
        "𝐏𝐨𝐤𝐞𝐦𝐨𝐧 , 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭 & 𝐌𝐮𝐬𝐢𝐜\n"
        "𝐭𝐨𝐠𝐞𝐭𝐡𝐞𝐫 𝐢𝐧 𝐨𝐧𝐞 𝐩𝐥𝐚𝐜𝐞 — 𝐦𝐚𝐤𝐢𝐧𝐠 𝐲𝐨𝐮𝐫\n"
        "𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲 𝐞𝐱𝐩𝐞𝐫𝐢𝐞𝐧𝐜𝐞 𝐬𝐦𝐚𝐫𝐭𝐞𝐫, 𝐬𝐦𝐨𝐨𝐭𝐡𝐞𝐫,\n"
        "𝐚𝐧𝐝 𝐦𝐨𝐫𝐞 𝐞𝐧𝐠𝐚𝐠𝐢𝐧𝐠.\n\n"
        "𝐇𝐞𝐫𝐞 𝐮 𝐠𝐞𝐭 𝐚𝐥𝐥 𝐭𝐡𝐞 𝐥𝐢𝐧𝐤𝐬 𝐚𝐧𝐝 𝐚𝐜𝐜𝐞𝐬𝐬 𝐭𝐨\n"
        "𝐚𝐥𝐥 𝐭𝐡𝐞 𝐠𝐫𝐨𝐮𝐩𝐬 𝐚𝐧𝐝 𝐜𝐡𝐚𝐧𝐧𝐞𝐥𝐬 𝐨𝐟 𝐭𝐡𝐞 𝐗𝐞𝐫𝐱𝐞𝐬 𝐜𝐨𝐦𝐦𝐮𝐧𝐢𝐭𝐲.\n\n"
        "https://t.me/XERXES_COMMUNITY\n\n"
        "          ── ⋆⋅𖤓⋅⋆ ──",
    reply_markup=InlineKeyboardMarkup(keyboard)
    )
    

# =========================================================
# START POKEMON JOURNEY BUTTON
# =========================================================

async def start_pokemon_journey(update, context):
    query = update.callback_query
    await query.answer()

    await start_pokedex(update, context)


# =========================================================
# START MENU CALLBACK
# =========================================================

async def start_menu_callback(update, context):
    query = update.callback_query
    await query.answer()

    # =====================================================
    # COMMANDS MENU
    # =====================================================

    if query.data == "start_commands":

        keyboard = [
            [
                InlineKeyboardButton(
                    "𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭 𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬",
                    callback_data="commands_management"
                )
            ],
            [
                InlineKeyboardButton(
                    "𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬",
                    callback_data="commands_pokemon"
                )
            ],
            [
                InlineKeyboardButton(
                    "𝐌𝐮𝐬𝐢𝐜 𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬",
                    callback_data="commands_music"
                )
            ],
            [
                InlineKeyboardButton(
                    "◀️ 𝐁𝐚𝐜𝐤",
                    callback_data="start_main"
                )
            ]
        ]

        await query.edit_message_text(
            "𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # =====================================================
    # MANAGEMENT COMMANDS
    # =====================================================

    elif query.data == "commands_management":

        await query.edit_message_text(
            "𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭 𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬\n\n"
            "/ban\n"
            "/unban\n"
            "/kick\n"
            "/mute\n"
            "/unmute\n"
            "/warn\n"
            "/warnings\n"
            "/resetwarns\n"
            "/antilink\n"
            "/antispam",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="start_commands"
                    )
                ]
            ])
        )

    # =====================================================
    # POKEMON COMMANDS
    # =====================================================

    elif query.data == "commands_pokemon":

        await query.edit_message_text(
            "𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬\n\n"
            "/startpokedex\n"
            "/trainer\n"
            "/status\n"
            "/bag\n"
            "/stopdex\n"
            "/ondex",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="start_commands"
                    )
                ]
            ])
        )

    # =====================================================
    # MUSIC COMMANDS
    # =====================================================

    elif query.data == "commands_music":

        await query.edit_message_text(
            "𝐌𝐮𝐬𝐢𝐜 𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬\n\n"
            "Music commands will be available here.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="start_commands"
                    )
                ]
            ])
        )

    # =====================================================
    # UPDATES
    # =====================================================

    elif query.data == "start_updates":

        await query.edit_message_text(
            "𝐗𝐄𝐑𝐗𝐄𝐒 𝐔𝐩𝐝𝐚𝐭𝐞𝐬\n\n"
            "🔹 𝐗𝐄𝐑𝐗𝐄𝐒 𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐏𝐨𝐤𝐞𝐃𝐞𝐱\n"
            "🔹 𝐓𝐫𝐚𝐢𝐧𝐞𝐫 𝐒𝐲𝐬𝐭𝐞𝐦\n"
            "🔹 𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐁𝐚𝐭𝐭𝐥𝐞 𝐒𝐲𝐬𝐭𝐞𝐦\n"
            "🔹 𝐈𝐧𝐯𝐞𝐧𝐭𝐨𝐫𝐲 & 𝐈𝐭𝐞𝐦𝐬\n"
            "🔹 𝐅𝐮𝐭𝐮𝐫𝐞 𝐌𝐢𝐧𝐢 𝐀𝐩𝐩\n\n"
            "𝐌𝐨𝐫𝐞 𝐮𝐩𝐝𝐚𝐭𝐞𝐬 𝐜𝐨𝐦𝐢𝐧𝐠 𝐬𝐨𝐨𝐧! 🔥",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "◀️ 𝐁𝐚𝐜𝐤",
                        callback_data="start_main"
                    )
                ]
            ])
        )

    # =====================================================
    # BACK TO MAIN MENU
    # =====================================================

    elif query.data == "start_main":

        keyboard = [
            [
                InlineKeyboardButton(
                    "𝐒𝐭𝐚𝐫𝐭 𝐏𝐨𝐤𝐞𝐦𝐨𝐧 𝐉𝐨𝐮𝐫𝐧𝐞𝐲",
                    callback_data="start_pokemon_journey"
                )
            ],
            [
                InlineKeyboardButton(
                    "𝐔𝐩𝐝𝐚𝐭𝐞𝐬",
                    callback_data="start_updates"
                ),
                InlineKeyboardButton(
                    "𝐂𝐨𝐦𝐦𝐚𝐧𝐝𝐬",
                    callback_data="start_commands"
                )
            ],
            [
                InlineKeyboardButton(
                    "𝐀𝐝𝐝 𝐦𝐞 𝐭𝐨 𝐠𝐫𝐨𝐮𝐩",
                    url=f"https://t.me/{context.bot.username}?startgroup=true"
                )
            ]
        ]

        await query.edit_message_text(
            "𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐭𝐨 𝐗𝐄𝐑𝐗𝐄𝐒",
            reply_markup=InlineKeyboardMarkup(keyboard)
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


async def start_pokemon_journey(update, context):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "🍥 𝐖𝐞𝐥𝐜𝐨𝐦𝐞, 𝐟𝐮𝐭𝐮𝐫𝐞 𝐓𝐫𝐚𝐢𝐧𝐞𝐫!\n\n"
        "𝐖𝐡𝐚𝐭 𝐧𝐚𝐦𝐞 𝐰𝐨𝐮𝐥𝐝 𝐲𝐨𝐮 𝐥𝐢𝐤𝐞 𝐭𝐨 𝐮𝐬𝐞 𝐚𝐬 𝐲𝐨𝐮𝐫 "
        "𝐓𝐫𝐚𝐢𝐧𝐞𝐫 𝐧𝐚𝐦𝐞?"
    )

    return TRAINER_NAME

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
        "🍥 𝐖𝐞𝐥𝐜𝐨𝐦𝐞, 𝐟𝐮𝐭𝐮𝐫𝐞 𝐓𝐫𝐚𝐢𝐧𝐞𝐫!\n\n"
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
# START MINI APP API
# =========================================================

def run_api():
    port = int(os.environ.get("PORT", 8080))
    api.run(
        host="0.0.0.0",
        port=port
    )


# =========================================================
# START BOT
# =========================================================

def main():

    threading.Thread(
        target=run_api,
        daemon=True
    ).start()
    
    init_db()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN environment variable is missing."
        )

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("helpdex", helpdex))
    app.add_handler(CommandHandler("data", pokemon_data))
    app.add_handler(CommandHandler("datadamage", datadamage))
    app.add_handler(CommandHandler("buildpoke", buildpoke))
    app.add_handler(CommandHandler("type", pokemon_type)) 
    app.add_handler(CommandHandler("datanature", datanature))
    app.add_handler(CommandHandler("bestnat", bestnat))
    app.add_handler(CommandHandler("evbuild", evbuild))
    app.add_handler(CommandHandler("datatm", datatm))
    app.add_handler(CommandHandler("pokeballs", pokeballs))
    app.add_handler(CommandHandler("move", move))
  
    app.add_handler(
        CallbackQueryHandler(
            tm_callback,
            pattern="^tm_page_[1-6]$"
        )
    )
 
    app.add_handler(
        CallbackQueryHandler(
            helpdex_callback,
            pattern="^(dex_|nature_|ev_|tm_)"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            start_menu_callback,
            pattern="^(start_commands|start_main|start_updates|commands_management|commands_pokemon|commands_music)$"
        )
    )
  
    app.add_handler(CommandHandler("trainer", trainer))
    app.add_handler(CommandHandler("bag", bag))
  
    app.add_handler(
        CallbackQueryHandler(
            bag_callback,
            pattern="^bag_"
        )
    )
 
    app.add_handler(CommandHandler("stopdex", stopdex))
    app.add_handler(CommandHandler("ondex", ondex))
    pokedex_registration = ConversationHandler(
    entry_points=[
        CommandHandler("startpokedex", start_pokedex),
        CallbackQueryHandler(
            start_pokemon_journey,
            pattern="^start_pokemon_journey$"
        )
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
