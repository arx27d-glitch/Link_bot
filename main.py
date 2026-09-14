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
    raise ValueError("❌ BOT_TOKEN is missing!")

if OWNER_ID == 0:
    raise ValueError("❌ OWNER_ID is missing!")


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
    cursor = conn.cursor()

    # Saved image + URL
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content (
            id INTEGER PRIMARY KEY,
            photo_file_id TEXT,
            url TEXT
        )
    """)

    # Maximum 10 channels
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            position INTEGER PRIMARY KEY,
            channel TEXT NOT NULL,
            link TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# CONTENT DATABASE
# =========================================================

def save_content(photo_file_id, url):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM content")

    cursor.execute("""
        INSERT INTO content
        (id, photo_file_id, url)
        VALUES (1, ?, ?)
    """, (photo_file_id, url))

    conn.commit()
    conn.close()


def get_content():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT photo_file_id, url
        FROM content
        WHERE id = 1
    """)

    result = cursor.fetchone()

    conn.close()

    return result


def delete_content():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM content")

    conn.commit()
    conn.close()


# =========================================================
# CHANNEL DATABASE
# =========================================================

def save_channel(position, channel, link):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO channels
        (position, channel, link)
        VALUES (?, ?, ?)
    """, (position, channel, link))

    conn.commit()
    conn.close()


def get_channels():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT position, channel, link
        FROM channels
        ORDER BY position ASC
    """)

    result = cursor.fetchall()

    conn.close()

    return result


def delete_channel(position):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
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
            text=f"Join {position} ↗",
            url=link
        )

        current_row.append(button)

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
# WELCOME TEXT
# =========================================================

def welcome_text(user):

    name = user.first_name or "User"

    return (
        f"👋 <b>Hello {name}!</b>\n\n"
        "📢 <b>Join All Channels To Continue.</b>\n\n"
        "👇 Join all required channels and then "
        "press <b>🔒 Claim</b>."
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

        if member.status in (
            "member",
            "administrator",
            "creator"
        ):
            return True

        # Restricted user who can still access the channel
        if member.status == "restricted":

            if getattr(member, "is_member", False):
                return True

        return False

    except Exception as e:

        print(
            f"Membership check error "
            f"{channel}: {e}"
        )

        return False


async def check_all_channels(user_id):

    channels = get_channels()

    # No channels configured
    if not channels:
        return True

    for position, channel, link in channels:

        joined = await check_member(
            user_id,
            channel
        )

        if not joined:
            return False

    return True


# =========================================================
# /START
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: Message):

    channels = get_channels()

    if not channels:

        await message.answer(
            "⚠️ <b>Bot is not configured yet.</b>\n\n"
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

        await message.answer(
            "❌ <b>Owner Only Command.</b>",
            parse_mode="HTML"
        )

        return

    args = message.text.split(maxsplit=2)

    if len(args) < 3:

        await message.answer(
            "❌ <b>Wrong format!</b>\n\n"
            "Use:\n"
            "<code>/setchnl 1 @AR_Network</code>\n\n"
            "Or:\n"
            "<code>/setchnl 1 https://t.me/AR_Network</code>",
            parse_mode="HTML"
        )

        return

    # Position
    try:

        position = int(args[1])

    except ValueError:

        await message.answer(
            "❌ Channel number must be a number."
        )

        return

    if position < 1 or position > 10:

        await message.answer(
            "❌ Channel number must be between "
            "<b>1 and 10</b>.",
            parse_mode="HTML"
        )

        return

    value = args[2].strip()

    # =============================================
    # @USERNAME
    # =============================================

    if value.startswith("@"):

        username = value[1:].strip()

        if not username:

            await message.answer(
                "❌ Invalid channel username."
            )

            return

        channel = value
        link = f"https://t.me/{username}"

    # =============================================
    # TELEGRAM LINK
    # =============================================

    elif value.startswith("https://t.me/"):

        username = value.replace(
            "https://t.me/",
            "",
            1
        ).strip("/")

        if not username:

            await message.answer(
                "❌ Invalid Telegram channel link."
            )

            return

        channel = f"@{username}"
        link = f"https://t.me/{username}"

    else:

        await message.answer(
            "❌ <b>Invalid channel.</b>\n\n"
            "Example:\n"
            "<code>/setchnl 1 @AR_Network</code>",
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
        "This channel will now appear "
        "in the Join list.",
        parse_mode="HTML"
    )


# =========================================================
# /DELCHNL
# =========================================================

@dp.message(Command("delchnl"))
async def delete_channel_handler(message: Message):

    if not is_owner(message.from_user.id):

        await message.answer(
            "❌ <b>Owner Only Command.</b>",
            parse_mode="HTML"
        )

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
            "❌ Number must be 1-10."
        )

        return

    existing = get_channels()

    found = any(
        x[0] == position
        for x in existing
    )

    if not found:

        await message.answer(
            f"⚠️ Channel {position} is not configured."
        )

        return

    delete_channel(position)

    await message.answer(
        f"🗑 <b>Channel {position} deleted.</b>",
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

    text = "📢 <b>Configured Channels</b>\n\n"

    for position, channel, link in channels:

        text += (
            f"<b>{position}.</b> "
            f"<code>{channel}</code>\n"
            f"🔗 {link}\n\n"
        )

    text += "Maximum: <b>10 channels</b>"

    await message.answer(
        text,
        parse_mode="HTML"
    )


# =========================================================
# /LINK
# =========================================================
#
# METHOD 1:
# Send image with caption:
#
# /link https://example.com/video
#
# METHOD 2:
# Reply to an image:
#
# /link https://example.com/video
#
# =========================================================

@dp.message(Command("link"))
async def link_handler(message: Message):

    if not is_owner(message.from_user.id):

        await message.answer(
            "❌ <b>Owner Only Command.</b>",
            parse_mode="HTML"
        )

        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:

        await message.answer(
            "❌ <b>URL missing!</b>\n\n"
            "Send image with:\n"
            "<code>/link https://example.com/video</code>\n\n"
            "Or reply to an image with the same command.",
            parse_mode="HTML"
        )

        return

    url = args[1].strip()

    if not valid_url(url):

        await message.answer(
            "❌ <b>Invalid URL!</b>\n\n"
            "URL must start with:\n"
            "<code>https://</code>\n"
            "or\n"
            "<code>http://</code>",
            parse_mode="HTML"
        )

        return

    photo_file_id = None

    # =====================================================
    # CASE 1: IMAGE + CAPTION
    # =====================================================

    if message.photo:

        photo_file_id = message.photo[-1].file_id

    # =====================================================
    # CASE 2: REPLY TO IMAGE
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
            "Use either:\n\n"
            "1️⃣ Send an image with:\n"
            "<code>/link https://example.com</code>\n\n"
            "2️⃣ Reply to an image with:\n"
            "<code>/link https://example.com</code>",
            parse_mode="HTML"
        )

        return

    # Save
    save_content(
        photo_file_id,
        url
    )

    await message.answer(
        "✅ <b>Content Saved Successfully!</b>\n\n"
        "🖼 Image: Saved\n"
        "🔗 URL: Saved\n\n"
        "Users who complete the channel "
        "verification will receive this content.",
        parse_mode="HTML"
    )


# =========================================================
# /LINKCLEAR
# =========================================================

@dp.message(Command("linkclear"))
async def link_clear_handler(message: Message):

    if not is_owner(message.from_user.id):

        await message.answer(
            "❌ <b>Owner Only Command.</b>",
            parse_mode="HTML"
        )

        return

    content = get_content()

    if not content:

        await message.answer(
            "📭 No saved content found."
        )

        return

    delete_content()

    await message.answer(
        "🗑 <b>Saved content deleted successfully.</b>",
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
            "📭 <b>No content is currently saved.</b>",
            parse_mode="HTML"
        )

        return

    photo_id, url = content

    await message.answer(
        "📦 <b>Current Content</b>\n\n"
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
        "🔍 Checking your membership..."
    )

    channels = get_channels()

    if not channels:

        await callback.message.edit_text(
            "⚠️ <b>Bot is not configured yet.</b>",
            parse_mode="HTML"
        )

        return

    # Check channels
    verified = await check_all_channels(
        user.id
    )

    if not verified:

        await callback.message.edit_text(
            "❌ <b>Verification Failed!</b>\n\n"
            "📢 You haven't joined all required "
            "channels yet.\n\n"
            "Join all channels and press "
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
            "⚠️ There is currently no content available.",
            parse_mode="HTML"
        )

        return

    photo_file_id, url = content

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Open Link",
                    url=url
                )
            ]
        ]
    )

    # Send image
    await callback.message.answer_photo(
        photo=photo_file_id,
        caption=(
            "🎉 <b>Congratulations!</b>\n\n"
            "✅ Membership verified successfully.\n\n"
            "👇 Your content is ready.\n"
            "Tap the button below."
        ),
        reply_markup=keyboard,
        parse_mode="HTML"
    )

    # Change old message
    try:

        await callback.message.edit_text(
            "✅ <b>Verification Successful!</b>\n\n"
            "🎁 Your content has been delivered.",
            parse_mode="HTML"
        )

    except Exception as e:

        print(f"Edit message error: {e}")


# =========================================================
# OWNER HELP
# =========================================================

@dp.message(Command("admin"))
async def admin_handler(message: Message):

    if not is_owner(message.from_user.id):

        await message.answer(
            "❌ Owner only."
        )

        return

    await message.answer(
        "👑 <b>OWNER PANEL</b>\n\n"

        "📢 <b>CHANNEL COMMANDS</b>\n"
        "<code>/setchnl 1 @channel</code>\n"
        "<code>/setchnl 2 @channel</code>\n"
        "... up to 10\n\n"

        "<code>/delchnl 1</code>\n"
        "Delete channel\n\n"

        "<code>/channels</code>\n"
        "Show all channels\n\n"

        "🎁 <b>CONTENT COMMANDS</b>\n"
        "<code>/link URL</code>\n"
        "Reply to/send an image\n\n"

        "<code>/linkinfo</code>\n"
        "Show saved content\n\n"

        "<code>/linkclear</code>\n"
        "Delete saved content",
        parse_mode="HTML"
    )


# =========================================================
# START BOT
# =========================================================

async def main():

    init_db()

    print("================================")
    print("🚀 VIRAL VIDEO STYLE BOT STARTED")
    print("================================")

    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
