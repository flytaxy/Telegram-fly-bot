import os
import logging
import openrouteservice
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, Router
from aiogram.enums import ContentType
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import asyncio

# Завантаження змінних середовища
load_dotenv()
ORS_API_KEY = os.getenv("ORS_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ініціалізація
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)
user_locations = {}

# Логування
logging.basicConfig(level=logging.INFO)

# /start
@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
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

# Локація
@dp.message(lambda m: m.content_type == ContentType.LOCATION)
async def handle_location(message: types.Message):
    user_id = message.from_user.id
    latitude = message.location.latitude
    longitude = message.location.longitude

    user_locations[user_id] = {"lat": latitude, "lon": longitude}

    await message.answer(
        f"Ми отримали твою локацію:\nШирота: {latitude}\nДовгота: {longitude}\n"
        "Тепер надішли адресу призначення 📬",
        reply_markup=ReplyKeyboardRemove()
    )

# Адреса
@dp.message(lambda m: m.content_type == ContentType.TEXT)
async def handle_destination(message: types.Message):
    user_id = message.from_user.id
    destination = message.text

    if user_id not in user_locations:
        await message.answer("Спочатку надішли свою локацію 📍")
        return

    start = user_locations[user_id]
    await message.answer(f"📦 Пункт призначення: {destination}\nПочаткова точка: {start['lat']}, {start['lon']}")

    route = get_route(start_coords=start, end_coords=start)  # Поки тест
    # Ти можеш додати вивід маршруту тут

def get_route(start_coords, end_coords):
    client = openrouteservice.Client(key=ORS_API_KEY)
    route = client.directions(
        coordinates=[start_coords, end_coords],
        profile='driving-car',
        format='geojson'
    )
    return route

# Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())