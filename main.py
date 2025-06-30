from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.utils import executor
import os

API_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start_command(message: Message):
    await message.answer("Привіт! Це FlyTaxi бот. Чим можу допомогти?")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
