import os
import json
import logging
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    CallbackQuery,
    Message,
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, StateFilter
from aiogram import F
from cd import calculate_price
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)


class RideStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_location = State()
    waiting_for_destination = State()
    waiting_for_waypoints = State()
    choosing_car_class = State()
    confirming_order = State()
    rating_driver = State


def load_users():
    if os.path.exists("users.json"):
        with open("users.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_users(users):
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def load_ratings():
    if os.path.exists("drivers_rating.json"):
        with open("drivers_rating.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_ratings(ratings):
    with open("drivers_rating.json", "w", encoding="utf-8") as f:
        json.dump(ratings, f, ensure_ascii=False, indent=2)


def is_peak_time(now_kyiv):
    weekday = now_kyiv.weekday()
    time_str = now_kyiv.strftime("%H:%M")
    peak_periods = [
        ("05:00", "06:00"),
        ("07:30", "11:00"),
        ("16:30", "19:30"),
        ("21:30", "00:00"),
    ]
    weekend_peak = ("22:30", "00:00")
    if weekday in [4, 5, 6]:  # п'ятниця, субота, неділя
        if weekend_peak[0] <= time_str < weekend_peak[1]:
            return True, 2.0
    for start, end in peak_periods:
        if start <= time_str < end:
            return True, 1.5
    return False, 1.0


def is_curfew(now_kyiv):
    return now_kyiv.time() < datetime.strptime("05:00", "%H:%M").time()


users = load_users()
ratings = load_ratings()


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    now_kyiv = datetime.now(ZoneInfo("Europe/Kyiv"))
    if is_curfew(now_kyiv):
        await message.answer(
            "🚫 Сервіс тимчасово недоступний через комендантську годину (00:00–05:00)."
        )
        return

    if user_id not in users:
        await state.set_state(RideStates.waiting_for_phone)
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("📱 Надіслати номер телефону", request_contact=True))
        await message.answer(
            "Вас вітає таксі Fly!\n\nЩоб продовжити, надішліть номер телефону:",
            reply_markup=kb,
        )
    else:
        await message.answer(
            "👋 Вітаємо знову!\nНатисніть кнопку нижче, щоб розпочати замовлення.",
            reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(
                KeyboardButton("📍 Поділитись локацією", request_location=True)
            ),
        )
        await state.set_state(RideStates.waiting_for_location)


@dp.message(RideStates.waiting_for_phone, F.contact)
async def process_contact(message: Message, state: FSMContext):
    contact = message.contact
    user_id = str(message.from_user.id)
    users[user_id] = {
        "id": user_id,
        "name": message.from_user.full_name,
        "username": message.from_user.username,
        "phone_number": contact.phone_number,
    }
    save_users(users)
    await message.answer(
        "✅ Номер збережено.\nТепер надішліть вашу локацію:",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(
            KeyboardButton("📍 Поділитись локацією", request_location=True)
        ),
    )
    await state.set_state(RideStates.waiting_for_location)


@dp.message(RideStates.waiting_for_location, F.location)
async def process_location(message: Message, state: FSMContext):
    latitude = message.location.latitude
    longitude = message.location.longitude
    await state.update_data(start_lat=latitude, start_lng=longitude)
    await message.answer(
        "📍 Ваша точка A збережена.\n\nВведіть адресу призначення (точка B):",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(RideStates.waiting_for_destination)


@dp.message(RideStates.waiting_for_destination, F.text)
async def process_destination(message: Message, state: FSMContext):
    destination = message.text
    await state.update_data(destination=destination)
    await message.answer(
        "🔁 Хочете додати зупинки?\nВведіть до 5 адрес по черзі або напишіть «Готово»."
    )
    await state.update_data(waypoints=[])
    await state.set_state(RideStates.waiting_for_waypoints)


@dp.message(RideStates.waiting_for_waypoints, F.text)
async def process_waypoints(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    waypoints = data.get("waypoints", [])

    if text.lower() == "готово":
        await state.update_data(waypoints=waypoints)
        await send_route_and_prices(message, state)
        return

    if len(waypoints) >= 5:
        await message.answer(
            "❗ Максимум 5 зупинок. Напишіть «Готово», щоб продовжити."
        )
        return

    waypoints.append(text)
    await state.update_data(waypoints=waypoints)
    await message.answer(
        f"✅ Зупинка додана. Всього зупинок: {len(waypoints)}.\n\nДодайте ще або напишіть «Готово»."
    )
async def send_route_and_prices(message: Message, state: FSMContext):
    data = await state.get_data()
    origin = f"{data['start_lat']},{data['start_lng']}"
    destination = data['destination']
    waypoints = data.get("waypoints", [])

    waypoint_param = ""
    if waypoints:
        waypoint_param = "&waypoints=" + "|".join(waypoints)

    directions_url = (
        f"https://maps.googleapis.com/maps/api/directions/json?"
        f"origin={origin}&destination={destination}"
        f"{waypoint_param}&key={GOOGLE_MAPS_API_KEY}&language=uk"
    )

    directions_response = requests.get(directions_url)
    directions = directions_response.json()

    if directions["status"] != "OK":
        await message.answer("❌ Не вдалося побудувати маршрут. Перевірте адресу.")
        return

    route = directions["routes"][0]["legs"]
    polyline = directions["routes"][0]["overview_polyline"]["points"]

    total_distance_km = sum(leg["distance"]["value"] for leg in route) / 1000

    map_url = (
        f"https://maps.googleapis.com/maps/api/staticmap?"
        f"size=600x400&path=enc:{polyline}&key={GOOGLE_MAPS_API_KEY}"
    )

    map_image = requests.get(map_url)
    map_path = "route_map.png"
    with open(map_path, "wb") as f:
        f.write(map_image.content)

    now_kyiv = datetime.now(ZoneInfo("Europe/Kyiv"))
    is_peak, multiplier = is_peak_time(now_kyiv)
    is_alert = not is_peak and False  # Підключення тривоги можливо пізніше

    standard_price = calculate_price(total_distance_km, "standard", is_peak, is_alert)
    comfort_price = calculate_price(total_distance_km, "comfort", is_peak, is_alert)
    business_price = calculate_price(total_distance_km, "business", is_peak, is_alert)

    await state.update_data(distance=total_distance_km,
                            is_peak=is_peak,
                            is_alert=is_alert)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🚗 Стандарт – {standard_price}₴", callback_data="car_standard")],
        [InlineKeyboardButton(text=f"🚙 Комфорт – {comfort_price}₴", callback_data="car_comfort")],
        [InlineKeyboardButton(text=f"🚘 Бізнес – {business_price}₴", callback_data="car_business")]
    ])

    await message.answer_photo(FSInputFile(map_path), caption="🗺️ Ось ваш маршрут.\n\n Оберіть клас авто:", reply_markup=kb)
    await state.set_state(RideStates.choosing_car_class)
    @dp.callback_query(RideStates.choosing_car_class, F.data.startswith("car_"))
    async def car_chosen(callback: CallbackQuery, state: FSMContext)
         
    car_class = callback.data.replace("car_", "")
    await state.update_data(car_class=car_class)
    await callback.message.answer("✅ Авто вибрано.\n\nНатисніть «Підтвердити», щоб замовити поїздку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Підтвердити замовлення", callback_data="confirm_order")]
        ]))
    await state.set_state(RideStates.confirming_order)

@dp.callback_query(RideStates.confirming_order, F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    price = calculate_price(data['distance'], data['car_class'], data['is_peak'], data['is_alert'])

    await callback.message.answer(
        f"🚖 Замовлення підтверджено!\n\n"
        f"Клас авто: {data['car_class'].capitalize()}\n"
        f"Вартість: {price}₴\n"
        f"Маршрут: {round(data['distance'], 1)} км\n\n"
        f"🔄 Якщо хочете змінити точку призначення — натисніть нижче.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Змінити адресу", callback_data="change_address")],
            [InlineKeyboardButton(text="🔄 Перезапустити", callback_data="restart")]
        ])
    )
    await state.set_state(RideStates.rating_driver)

@dp.callback_query(F.data == "change_address")
async def change_address(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Введіть нову адресу призначення (точку B):")
    await state.set_state(RideStates.waiting_for_destination)

@dp.callback_query(F.data == "restart")
async def restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("🔄 Замовлення скасовано.\nНатисніть /start, щоб почати заново.")
    @dp.message(RideStates.rating_driver, F.text.in_(["1", "2", "3", "4", "5"]))
@dp.message(RideStates.rating_driver, F.text.in_(["1", "2", "3", "4", "5"]))
async def rate_driver(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    driver_id = "demo_driver_001"  # У реальній версії — підставляється ID водія
    rating = int(message.text)

    driver = ratings.get(driver_id, {"total": 0, "count": 0, "history": []})
    driver["history"].append(rating)
    driver["count"] += 1
    driver["total"] += rating

    # Видаляємо стару погану оцінку через 100 поїздок
    if len(driver["history"]) > 100:
        removed = driver["history"].pop(0)
        driver["total"] -= removed
        driver["count"] -= 1

    ratings[driver_id] = driver
    save_ratings(ratings)

    average = driver["total"] / driver["count"] if driver["count"] else 5.0
    await message.answer(f"✅ Дякуємо за оцінку!\nПоточний рейтинг водія: {average:.2f}⭐️")

    await state.clear()
    await message.answer("🔁 Натисніть /start, щоб зробити нове замовлення.")
@dp.message(RideStates.rating_driver, F.text.in_(["1", "2", "3", "4", "5"]))
async def rate_driver(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    driver_id = "demo_driver_001"  # У реальній версії — підставляється ID водія
    rating = int(message.text)

    driver = ratings.get(driver_id, {"total": 0, "count": 0, "history": []})
    driver["history"].append(rating)
    driver["count"] += 1
    driver["total"] += rating

    if len(driver["history"]) > 100:
        removed = driver["history"].pop(0)
        driver["total"] -= removed
        driver["count"] -= 1

    ratings[driver_id] = driver
    save_ratings(ratings)

    average = driver["total"] / driver["count"] if driver["count"] else 5.0
    await message.answer(f"✅ Дякуємо за оцінку!\nПоточний рейтинг водія: {average:.2f}⭐️")
    await state.clear()
    await message.answer("🔁 Натисніть /start, щоб зробити нове замовлення.")
    async def on_startup(dispatcher: Dispatcher):logging.info("🚀 FlyTaxi бот запущено.")
def main():
    dp.startup.register(on_startup)
    import asyncio
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    main()