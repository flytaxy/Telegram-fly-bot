import os
import logging
import openrouteservice
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ContentType
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
import asyncio

# Завантаження змінних середовища
load_dotenv()
ORS_API_KEY = os.getenv("ORS_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ініціалізація
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_locations = {}

# Хендлер /start
@dp.message(Command("start"))
async def send_welcome(message: Message):
    location_button = KeyboardButton(
        text="📍 Надіслати локацію",
        request_location=True
    )

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[location_button]],
        resize_keyboard=True
    )

    await message.answer(
        "Привіт! Надішли свою локацію, щоб викликати таксі 🚕",
        reply_markup=keyboard
    )

# Хендлер локації
@dp.message(lambda message: message.location is not None)
async def handle_location(message: Message):
    lat = message.location.latitude
    lon = message.location.longitude
    user_locations[message.from_user.id] = (lat, lon)
    await message.answer("Локацію отримано. Введіть адресу призначення")

# Хендлер адреси
@dp.message()
async def handle_destination(message: Message):
    user_id = message.from_user.id
    if user_id not in user_locations:
        await message.answer("Спочатку надішліть локацію 📍")
        return

    client = openrouteservice.Client(key=ORS_API_KEY)
    coords = [
        (user_locations[user_id][1], user_locations[user_id][0]),  # (lon, lat)
        message.text  # Спрощено: розглядається текст як координати
    ]

    try:
        route = client.directions(coords)
        distance = route['routes'][0]['summary']['distance'] / 1000
        await message.answer(f"Довжина маршруту: {distance:.2f} км")
    except Exception as e:
        await message.answer(f"Помилка побудови маршруту: {e}")

# Старт бота
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__== "__main__":
    asyncio.run(main())