import logging
import os
import requests
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, Location, FSInputFile
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ORS_API_KEY = os.getenv("ORS_API_KEY")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())

logging.basicConfig(level=logging.INFO)

class OrderTaxi(StatesGroup):
    waiting_for_location = State()
    waiting_for_destination = State()

@dp.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Надіслати локацію", request_location=True)]],
        resize_keyboard=True
    )
    await message.answer("Привіт! Надішли свою локацію, щоб почати замовлення таксі:", reply_markup=keyboard)
    await state.set_state(OrderTaxi.waiting_for_location)

@dp.message(OrderTaxi.waiting_for_location, F.location)
async def process_location(message: Message, state: FSMContext):
    await state.update_data(location=message.location)
    await message.answer("Тепер введи адресу призначення (наприклад: Хрещатик 22, Київ):", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))
    await state.set_state(OrderTaxi.waiting_for_destination)

@dp.message(OrderTaxi.waiting_for_destination)
async def process_destination(message: Message, state: FSMContext):
    user_data = await state.get_data()
    location = user_data["location"]
    start_coords = [location.longitude, location.latitude]

    destination_text = message.text

    # Геокодування
    geo_url = f"https://api.openrouteservice.org/geocode/search?api_key={ORS_API_KEY}&text={destination_text}&boundary.country=UA"
    geo_response = requests.get(geo_url).json()

    if not geo_response.get("features"):
        await message.answer("Не вдалося знайти адресу. Спробуй ще раз.")
        return

    end_coords = geo_response["features"][0]["geometry"]["coordinates"]

    # Побудова маршруту
   route_url = "https://api.openrouteservice.org/v2/directions/driving-car"
headers = {
    "Authorization": ORS_API_KEY,
    "Content-Type": "application/json"
}
payload = {
    "coordinates": [start_coords, end_coords],
    "instructions": False,  # прибираємо текстові інструкції, щоб не зламалось
}
response = requests.post(route_url, json=payload, headers=headers)

if response.status_code != 200:
    await message.answer(f"❌ OpenRouteService повернув помилку: {response.status_code}\n{response.text}")
    return

route_response = response.json()

    try:
        segment = route_response["features"][0]["properties"]["segments"][0]
        distance_km = round(segment["distance"] / 1000, 2)
        duration_min = round(segment["duration"] / 60, 1)
    except Exception:
        await message.answer("Помилка при побудові маршруту.")
        return

    # Генерація зображення маршруту
    coords_str = f"{start_coords[0]},{start_coords[1]}|{end_coords[0]},{end_coords[1]}"
    map_url = f"https://api.openrouteservice.org/maps/staticmap?api_key={ORS_API_KEY}&layer=mapnik&size=600x400&markers={coords_str}&path={coords_str}"

    try:
        map_img = requests.get(map_url)
        map_path = "route_map.png"
        with open(map_path, "wb") as f:
            f.write(map_img.content)
        photo = FSInputFile(map_path)
        await bot.send_photo(message.chat.id, photo, caption=(
            f"<b>Маршрут побудовано!</b> 🗺️\n"
            f"Відстань: <b>{distance_km} км</b>\n"
            f"Орієнтовний час: <b>{duration_min} хв</b>"
        ), parse_mode="HTML")
        os.remove(map_path)
    except Exception:
        await message.answer("Не вдалося завантажити карту маршруту, але відстань: "
                             f"{distance_km} км, час: {duration_min} хв")

    await state.clear()

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))