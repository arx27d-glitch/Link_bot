import os
import asyncio
import sqlite3
import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "bot.db")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing!")

if OWNER_ID == 0:
    raise ValueError("OWNER_ID is missing!")


# =========================================================
# BOT
# =========================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return sqlite3.connect(DB_PATH)


def init_db():

    conn = get_db()
    cur = conn.cursor()

    # Content
    cur.execute("""
        CREATE TABLE IF NOT EXISTS content (
            id INTEGER PRIMARY KEY,
            photo_file_id TEXT NOT NULL,
            url TEXT NOT NULL
        )
    """)

    # Channels
    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            position INTEGER PRIMARY KEY,
            channel TEXT NOT NULL,
            link TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# CONTENT FUNCTIONS
# =========================================================

def save_content(photo_file_id, url):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM content")

    cur.execute("""
        INSERT INTO content
        (id, photo_file_id, url)
        VALUES (1, ?, ?)
    """, (photo_file_id, url))

    conn.commit()
    conn.close()


def get_content():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT photo_file_id, url
        FROM content
        WHERE id = 1
    """)

    result = cur.fetchone()

    conn.close()

    return result


def delete_content():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM content")

    conn.commit()
    conn.close()


# =========================================================
# CHANNEL FUNCTIONS
# =========================================================

def save_channel(position, channel, link):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO channels
        (position, channel, link)
        VALUES (?, ?, ?)
    """, (position, channel, link))

    conn.commit()
    conn.close()


def get_channels():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT position, channel, link
        FROM channels
        ORDER BY position ASC
    """)

    result = cur.fetchall()

    conn.close()

    return result


def delete_channel(position):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM channels
        WHERE position = ?
    """, (position,))

    conn.commit()
    conn.close()


# =========================================================
# OWNER CHECK
# =========================================================

def is_owner(user_id):

    return user_id == OWNER_ID


# =========================================================
# URL VALIDATION
# =========================================================

def valid_url(url):

    pattern = re.compile(
        r"^https?://[^\s]+$",
        re.IGNORECASE
    )

    return bool(pattern.match(url))


# =========================================================
# JOIN KEYBOARD
# =========================================================

def join_keyboard():

    channels = get_channels()

    rows = []
    current_row = []

    for position, channel, link in channels:

        button = InlineKeyboardButton(
            text=f"🔗 Join {position}",
            url=link
        )

        current_row.append(button)

        # 2 buttons per row
        if len(current_row) == 2:

            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    # Claim button
    rows.append([
        InlineKeyboardButton(
            text="🔒 Claim",
            callback_data="claim"
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# WELCOME
# =========================================================

def welcome_text(user):

    name = user.first_name or "User"

    return (
        f"👋 <b>Hello {name}!</b>\n\n"
        "📢 <b>Join all required channels to continue.</b>\n\n"
        "After joining all channels, "
        "press the button below.\n\n"
        "🔒 <b>Then press Claim.</b>"
    )


# =========================================================
# MEMBERSHIP CHECK
# =========================================================

async def check_member(user_id, channel):

    try:

        member = await bot.get_chat_member(
            chat_id=channel,
            user_id=user_id
        )

        status = member.status

        # Normal member
        if status == "member":
            return True

        # Admin
        if status == "administrator":
            return True

        # Channel owner
        if status == "creator":
            return True

        # Restricted member
        if status == "restricted":

            return getattr(
                member,
                "is_member",
                False
            )

        return False

    except Exception as e:

        print(
            f"[Membership Error] "
            f"{channel}: {e}"
        )

        return False


# =========================================================
# CHECK ALL CONFIGURED CHANNELS
# =========================================================

async def check_all_channels(user_id):

    channels = get_channels()

    # IMPORTANT:
    # Agar owner ne koi channel set nahi kiya
    # to verification required nahi hai.

    if not channels:
        return True

    # Sirf configured channels check honge.
    for position, channel, link in channels:

        joined = await check_member(
            user_id,
            channel
        )

        if not joined:
            return False

    return True


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: Message):

    channels = get_channels()

    if not channels:

        await message.answer(
            "⚠️ <b>Bot is currently unavailable.</b>\n\n"
            "Please try again later.",
            parse_mode="HTML"
        )

        return

    await message.answer(
        welcome_text(message.from_user),
        reply_markup=join_keyboard(),
        parse_mode="HTML"
    )


# =========================================================
# /SETCHNL
# =========================================================

@dp.message(Command("setchnl"))
async def set_channel_handler(message: Message):

    if not is_owner(message.from_user.id):

        # Don't expose owner information
        return

    args = message.text.split(maxsplit=2)

    if len(args) < 3:

        await message.answer(
            "❌ <b>Wrong format!</b>\n\n"
            "Example:\n"
            "<code>/setchnl 1 @AR_Network</code>\n\n"
            "Or:\n"
            "<code>/setchnl 1 https://t.me/AR_Network</code>",
            parse_mode="HTML"
        )

        return

    # Channel position
    try:

        position = int(args[1])

    except ValueError:

        await message.answer(
            "❌ Channel number must be a number."
        )

        return

    # Maximum 10
    if position < 1 or position > 10:

        await message.answer(
            "❌ Channel number must be between "
            "<b>1 and 10</b>.",
            parse_mode="HTML"
        )

        return

    value = args[2].strip()

    # =====================================================
    # @USERNAME
    # =====================================================

    if value.startswith("@"):

        username = value[1:].strip()

        if not username:

            await message.answer(
                "❌ Invalid channel username."
            )

            return

        channel = value
        link = f"https://t.me/{username}"

    # =====================================================
    # TELEGRAM LINK
    # =====================================================

    elif value.startswith("https://t.me/"):

        username = value.replace(
            "https://t.me/",
            "",
            1
        ).strip("/")

        if not username:

            await message.answer(
                "❌ Invalid Telegram link."
            )

            return

        channel = f"@{username}"
        link = f"https://t.me/{username}"

    else:

        await message.answer(
            "❌ <b>Invalid channel.</b>\n\n"
            "Use:\n"
            "<code>/setchnl 1 @channel</code>",
            parse_mode="HTML"
        )

        return

    # Save
    save_channel(
        position,
        channel,
        link
    )

    await message.answer(
        f"✅ <b>Channel {position} Saved!</b>\n\n"
        f"📢 Channel: <code>{channel}</code>\n"
        f"🔗 Link: {link}\n\n"
        f"Required channels currently: "
        f"<b>{len(get_channels())}</b>",
        parse_mode="HTML"
    )


# =========================================================
# /DELCHNL
# =========================================================

@dp.message(Command("delchnl"))
async def delete_channel_handler(message: Message):

    if not is_owner(message.from_user.id):
        return

    args = message.text.split()

    if len(args) != 2:

        await message.answer(
            "Use:\n"
            "<code>/delchnl 1</code>",
            parse_mode="HTML"
        )

        return

    try:

        position = int(args[1])

    except ValueError:

        await message.answer(
            "❌ Invalid channel number."
        )

        return

    if position < 1 or position > 10:

        await message.answer(
            "❌ Number must be between 1 and 10."
        )

        return

    channels = get_channels()

    if not any(
        item[0] == position
        for item in channels
    ):

        await message.answer(
            f"⚠️ Channel {position} is not configured."
        )

        return

    delete_channel(position)

    await message.answer(
        f"🗑 <b>Channel {position} deleted.</b>\n\n"
        f"Required channels now: "
        f"<b>{len(get_channels())}</b>",
        parse_mode="HTML"
    )


# =========================================================
# /CHANNELS
# =========================================================

@dp.message(Command("channels"))
async def channels_handler(message: Message):

    if not is_owner(message.from_user.id):
        return

    channels = get_channels()

    if not channels:

        await message.answer(
            "📭 <b>No channels configured.</b>",
            parse_mode="HTML"
        )

        return

    text = "📢 <b>CONFIGURED CHANNELS</b>\n\n"

    for position, channel, link in channels:

        text += (
            f"<b>{position}.</b> "
            f"<code>{channel}</code>\n"
            f"🔗 {link}\n\n"
        )

    text += (
        "━━━━━━━━━━━━━━\n"
        f"📊 Required: <b>{len(channels)}/10</b>"
    )

    await message.answer(
        text,
        parse_mode="HTML"
    )


# =========================================================
# /LINK
# =========================================================

@dp.message(Command("link"))
async def link_handler(message: Message):

    if not is_owner(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:

        await message.answer(
            "❌ <b>URL missing!</b>\n\n"
            "Send an image with:\n"
            "<code>/link https://example.com</code>\n\n"
            "Or reply to an image with the same command.",
            parse_mode="HTML"
        )

        return

    url = args[1].strip()

    if not valid_url(url):

        await message.answer(
            "❌ <b>Invalid URL!</b>\n\n"
            "URL must start with "
            "<code>http://</code> or "
            "<code>https://</code>.",
            parse_mode="HTML"
        )

        return

    photo_file_id = None

    # =====================================================
    # IMAGE + CAPTION
    # =====================================================

    if message.photo:

        photo_file_id = message.photo[-1].file_id

    # =====================================================
    # REPLY TO IMAGE
    # =====================================================

    elif message.reply_to_message:

        replied = message.reply_to_message

        if replied.photo:

            photo_file_id = replied.photo[-1].file_id

    # =====================================================
    # NO IMAGE
    # =====================================================

    if not photo_file_id:

        await message.answer(
            "❌ <b>Image not found!</b>\n\n"
            "Send an image with:\n"
            "<code>/link https://example.com</code>\n\n"
            "OR reply to an image with:\n"
            "<code>/link https://example.com</code>",
            parse_mode="HTML"
        )

        return

    save_content(
        photo_file_id,
        url
    )

    await message.answer(
        "✅ <b>CONTENT SAVED</b>\n\n"
        "🖼 Image: ✅\n"
        "🔗 Link: ✅\n\n"
        "Users who complete verification "
        "will receive this content.",
        parse_mode="HTML"
    )


# =========================================================
# /LINKCLEAR
# =========================================================

@dp.message(Command("linkclear"))
async def link_clear_handler(message: Message):

    if not is_owner(message.from_user.id):
        return

    content = get_content()

    if not content:

        await message.answer(
            "📭 No saved content."
        )

        return

    delete_content()

    await message.answer(
        "🗑 <b>Saved content deleted.</b>",
        parse_mode="HTML"
    )


# =========================================================
# /LINKINFO
# =========================================================

@dp.message(Command("linkinfo"))
async def link_info_handler(message: Message):

    if not is_owner(message.from_user.id):
        return

    content = get_content()

    if not content:

        await message.answer(
            "📭 <b>No content saved.</b>",
            parse_mode="HTML"
        )

        return

    photo_id, url = content

    await message.answer(
        "📦 <b>SAVED CONTENT</b>\n\n"
        "🖼 Image: ✅ Saved\n\n"
        f"🔗 URL:\n<code>{url}</code>",
        parse_mode="HTML"
    )


# =========================================================
# CLAIM
# =========================================================

@dp.callback_query(F.data == "claim")
async def claim_handler(callback: CallbackQuery):

    user = callback.from_user

    await callback.answer(
        "🔍 Checking membership..."
    )

    channels = get_channels()

    if not channels:

        await callback.message.edit_text(
            "⚠️ <b>Bot is currently unavailable.</b>",
            parse_mode="HTML"
        )

        return

    # =====================================================
    # CHECK ONLY CONFIGURED CHANNELS
    # =====================================================

    verified = await check_all_channels(
        user.id
    )

    # =====================================================
    # NOT JOINED
    # =====================================================

    if not verified:

        await callback.message.edit_text(
            "❌ <b>Verification Failed!</b>\n\n"
            "Please join <b>ALL</b> required channels.\n\n"
            "After joining them, press "
            "🔒 <b>Claim</b> again.",
            reply_markup=join_keyboard(),
            parse_mode="HTML"
        )

        return

    # =====================================================
    # VERIFIED
    # =====================================================

    content = get_content()

    if not content:

        await callback.message.edit_text(
            "✅ <b>Verification Successful!</b>\n\n"
            "⚠️ No content is currently available.",
            parse_mode="HTML"
        )

        return

    photo_file_id, url = content

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 OPEN LINK",
                    url=url
                )
            ]
        ]
    )

    # Send content
    await callback.message.answer_photo(
        photo=photo_file_id,
        caption=(
            "🎉 <b>Congratulations!</b>\n\n"
            "✅ Verification successful.\n\n"
            "🎁 <b>Your content is ready!</b>\n\n"
            "👇 Tap the button below."
        ),
        reply_markup=keyboard,
        parse_mode="HTML"
    )

    # Update old message
    try:

        await callback.message.edit_text(
            "✅ <b>Verification Successful!</b>\n\n"
            "🎁 Your content has been delivered.",
            parse_mode="HTML"
        )

    except Exception as e:

        print(
            f"[Edit Error] {e}"
        )


# =========================================================
# /ADMIN
# =========================================================

@dp.message(Command("admin"))
async def admin_handler(message: Message):

    if not is_owner(message.from_user.id):
        return

    await message.answer(
        "👑 <b>OWNER PANEL</b>\n\n"

        "📢 <b>CHANNEL MANAGEMENT</b>\n\n"

        "<code>/setchnl 1 @channel</code>\n"
        "<code>/setchnl 2 @channel</code>\n"
        "<code>/setchnl 3 @channel</code>\n"
        "...\n"
        "<code>/setchnl 10 @channel</code>\n\n"

        "<code>/delchnl 1</code>\n"
        "Delete a channel\n\n"

        "<code>/channels</code>\n"
        "Show configured channels\n\n"

        "🎁 <b>CONTENT</b>\n\n"

        "<code>/link URL</code>\n"
        "Reply/send image + URL\n\n"

        "<code>/linkinfo</code>\n"
        "Show current content\n\n"

        "<code>/linkclear</code>\n"
        "Delete current content\n\n"

        "━━━━━━━━━━━━━━\n"
        "📌 <b>Dynamic Channel System</b>\n\n"
        "1 channel set = 1 required\n"
        "3 channels set = 3 required\n"
        "10 channels set = 10 required",
        parse_mode="HTML"
    )


# =========================================================
# START
# =========================================================

async def main():

    init_db()

    print("========================================")
    print("🚀 VIRAL VIDEO LINK BOT STARTED")
    print("========================================")

    await dp.start_polling(bot)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    asyncio.run(main())
