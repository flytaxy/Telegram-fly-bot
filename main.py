import os
import logging
import requests
import folium
from datetime import datetime, time

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from geopy.geocoders import Nominatim
from dotenv import load_dotenv

# Завантаження .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ORS_API_KEY = os.getenv("ORS_API_KEY")

# Логування
logging.basicConfig(level=logging.INFO)

# Ініціалізація
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
geolocator = Nominatim(user_agent="flytaxi")

# Стан
class OrderTaxi(StatesGroup):
    waiting_for_location = State()
    waiting_for_address = State()
    waiting_for_car_class = State()

# Функція перевірки пікового часу
def is_peak_hour():
    now = datetime.now().time()
    return (
        time(7, 0) <= now <= time(10, 0) or
        time(17, 0) <= now <= time(20, 0)
    )

# Старт
@dp.message(commands=["start"])
async def start(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton(text="📍 Поділитись локацією", request_location=True))
    await message.answer("Привіт! Надішли свою локацію, щоб замовити таксі:", reply_markup=kb)
    await state.set_state(OrderTaxi.waiting_for_location)

# Локація
@dp.message(OrderTaxi.waiting_for_location)
async def process_location(message: types.Message, state: FSMContext):
    if not message.location:
        await message.answer("Будь ласка, натисни кнопку 'Поділитись локацією'")
        return

    await state.update_data(location=message.location)
    await message.answer("Тепер введи адресу призначення (наприклад: Хрещатик 22, Київ):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderTaxi.waiting_for_address)

# Адреса
@dp.message(OrderTaxi.waiting_for_address)
async def process_destination(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    location = user_data.get("location")

try:
        destination = geolocator.geocode(message.text)
        if not destination:
            await message.answer("❌ Не знайдено таку адресу. Спробуй ще раз.")
            return

        start_coords = [location.longitude, location.latitude]
        end_coords = [destination.longitude, destination.latitude]

        # Побудова маршруту
        route_url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {
            "Authorization": ORS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "coordinates": [start_coords, end_coords],
            "instructions": False
        }

        response = requests.post(route_url, json=payload, headers=headers)
        if response.status_code != 200:
            await message.answer(f"❌ OpenRouteService повернув помилку: {response.status_code}\n{response.text}")
            return

        route_response = response.json()
        geometry = route_response["features"][0]["geometry"]["coordinates"]
        distance_km = round(route_response["features"][0]["properties"]["segments"][0]["distance"] / 1000, 2)
        duration_min = round(route_response["features"][0]["properties"]["segments"][0]["duration"] / 60)

        # Мапа
        m = folium.Map(location=[start_coords[1], start_coords[0]], zoom_start=13)
        folium.Marker(location=[start_coords[1], start_coords[0]], tooltip="Початок").add_to(m)
        folium.Marker(location=[end_coords[1], end_coords[0]], tooltip="Кінець").add_to(m)
        folium.PolyLine([(coord[1], coord[0]) for coord in geometry], color="blue", weight=5).add_to(m)

        map_path = "route_map.png"
        m.save("route.html")
        os.system(f"wkhtmltoimage --quality 80 route.html {map_path}")

Сергій Вікторович, [03.07.2025 7:46]
await state.update_data(
            distance_km=distance_km,
            duration_min=duration_min,
            map_path=map_path
        )

        await message.answer(
            f"📍 Маршрут знайдено!\n"
            f"📏 Відстань: <b>{distance_km}</b> км\n"
            f"⏱️ Час: <b>{duration_min}</b> хв\n\n"
            "🚘 Обери клас авто:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🚗 Стандарт"), KeyboardButton(text="🚙 Комфорт"), KeyboardButton(text="🚘 Бізнес")]
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            ),
            parse_mode="HTML"
        )

        await state.set_state(OrderTaxi.waiting_for_car_class)

    except Exception as e:
        await message.answer(f"‼️ Не вдалося побудувати маршрут.\nПомилка: {str(e)}")
        await state.clear()

# Вибір класу авто
@dp.message(OrderTaxi.waiting_for_car_class)
async def process_car_class(message: types.Message, state: FSMContext):
    car_class_text = message.text.strip().lower()
    user_data = await state.get_data()
    distance = user_data.get("distance_km")
    duration = user_data.get("duration_min")
    map_path = user_data.get("map_path")

    peak = is_peak_hour()

    if "стандарт" in car_class_text or "економ" in car_class_text:
        car_class = "Стандарт"
        base = 150 if peak else 120
        per_km = 25 if peak else 20
        included_km = 2.0

    elif "комфорт" in car_class_text:
        car_class = "Комфорт"
        base = 150
        per_km = 27 if peak else 23
        included_km = 2.5

    elif "бізнес" in car_class_text:
        car_class = "Бізнес"
        base = 230 if peak else 180
        per_km = 32 if peak else 27
        included_km = 2.5

    else:
        await message.answer("❌ Будь ласка, обери варіант з кнопок.")
        return

    # Розрахунок
    billable_km = max(0, distance - included_km)
    total_price = round(base + billable_km * per_km)

    caption = (
        f"<b>🚖 Клас:</b> {car_class}\n"
        f"<b>📏 Відстань:</b> {distance} км (включено {included_km} км у подачу)\n"
        f"<b>💳 Платна відстань:</b> {round(billable_km, 2)} км\n"
        f"<b>⏱️ Час:</b> {duration} хв\n"
        f"<b>💰 Вартість:</b> {total_price} ₴\n"
    )

    if peak:
        caption += "⚠️ <i>Піковий тариф застосовано</i>\n"

    caption += "\nОплата здійснюється готівкою водію по завершенню поїздки."

    photo = FSInputFile(map_path)
    await bot.send_photo(
        message.chat.id,
        photo,
        caption=caption,
        parse_mode="HTML"
    )

    if os.path.exists(map_path):
        os.remove(map_path)

    await state.clear()

# Запуск бота
if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))