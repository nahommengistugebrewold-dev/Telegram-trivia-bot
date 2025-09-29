import os
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
db_pool = None

async def create_pool():
    return await asyncpg.create_pool(DATABASE_URL)

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (id, username) VALUES ($1,$2)
            ON CONFLICT (id) DO NOTHING
        """, message.from_user.id, message.from_user.username)
    await message.reply("👋 እንኳን ወደ ትሪቪያ ቦት በደህና መጡ።")

@dp.message_handler(commands=["aboutus"])
async def about_cmd(message: types.Message):
    await message.reply(
        "ℹ️ ስለ እኛ:\n\n"
        "ነፃ: በቀን 15 ጥያቄ\n"
        "ፕሪሚየም: በወር 100 ብር – አስቸጋሪ ጥያቄዎች እና ወርሃዊ ሽልማት\n\n"
        "💳 ክፍያ በ Chapa (በቅርቡ)"
    )

@dp.message_handler(commands=["premium"])
async def premium_cmd(message: types.Message):
    await message.reply("💎 ፕሪሚየም አባልነት በወር 100 ብር።\nChapa ክፍያ ከተጨመረ በኋላ ይሰራል።")

@dp.message_handler(commands=["feedback"])
async def feedback_cmd(message: types.Message):
    await message.reply("✍️ ግብረ መልስዎን እዚህ ይጻፉ።")

@dp.message_handler(lambda msg: msg.text and not msg.text.startswith("/"))
async def handle_feedback(message: types.Message):
    await bot.send_message(ADMIN_ID, f"Feedback @{message.from_user.username}: {message.text}")
    await message.reply("✅ ግብረ መልስዎ ተልኳል።")

async def on_startup(dp):
    global db_pool
    db_pool = await create_pool()
    print("Bot started.")

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)