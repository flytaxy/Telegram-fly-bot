from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

API_TOKEN = "7841476557:AAGbZa8RxgmJcw5shIz2WcxiCrETntc9Ccs"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("Привіт! Я бот Flytaxy 🚕")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)