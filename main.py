from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
import logging
import os

# Ініціалізація бота з токеном із змінної середовища
API_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
user_locations = {}

# Увімкнення логування
logging.basicConfig(level=logging.INFO)

# Обробка команди /start
@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    # Кнопка для надсилання локації
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    location_button = KeyboardButton(text="📍 Надіслати локацію", request_location=True)
    keyboard.add(location_button)

    await message.answer(
        "Привіт! Надішли свою локацію, щоб викликати таксі 🚕",
        reply_markup=keyboard
    )

# Обробка отриманої локації
@dp.message_handler(content_types=types.ContentType.LOCATION)
async def handle_location(message: types.Message):
    latitude = message.location.latitude
    longitude = message.location.longitude

    await message.answer(f"Ми отримали твою локацію:\n📍 Широта: {latitude}\n📍 Довгота: {longitude}\nОчікуй авто!")
user_locations = {}

# Обробка отриманої локації
@dp.message_handler(content_types=types.ContentType.LOCATION)
async def handle_location(message: types.Message):
    user_id = message.from_user.id
    latitude = message.location.latitude
    longitude = message.location.longitude

    user_locations[user_id] = {"lat": latitude, "lon": longitude}

    await message.answer (
    f"Ми отримали твою локацію:\n📍 Широта: {latitude}\n📍 Довгота: {longitude}\n\n"
    "Тепер надішли адресу, куди їхати 🏁",
    reply_markup=types.ReplyKeyboardRemove())

# Обробка введеної адреси призначення
@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_destination(message: types.Message):
    user_id = message.from_user.id
    destination = message.text

    if user_id in user_locations:
        start = user_locations[user_id]
        await message.answer(
            f"🚕 Ваш маршрут:\n"
            f"Початкова точка: 📍 {start['lat']}, {start['lon']}\n"
            f"Пункт призначення: 📍 {destination}\n\n"
            "Очікуйте авто, скоро приїде! 😉"
        )
        del user_locations[user_id]
    else:
        await message.answer("Спочатку надішліть свою локацію 📍")
# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)