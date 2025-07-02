from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
import logging
import os

# Ініціалізація бота з токеном із змінної оточення
API_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Увімкнення логування
logging.basicConfig(level=logging.INFO)

# Обробка команди /start
@dp.message_handler(commands=["start"])
async def send_welcome(message: Message):
    # Кнопка для надсилання локації
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    location_button = KeyboardButton(text="📍 Надіслати локацію", request_location=True)
    keyboard.add(location_button)
    await message.answer("Привіт! Надішли свою локацію, щоб викликати таксі 🚕", reply_markup=keyboard)

# Обробка отриманої локації
@dp.message_handler(content_types=types.ContentType.LOCATION)