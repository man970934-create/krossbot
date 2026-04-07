import asyncio
import logging
import json

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode

import config
import texts
from database import (
    init_db, add_user, start_reading_session, update_reading_session,
    end_reading_session, get_bot_state, set_bot_state, get_all_users,
    get_reading_stats
)
from states import BroadcastStates, FeedbackStates
from middlewares import BotActiveMiddleware, CallbackActiveMiddleware

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

dp.message.middleware(BotActiveMiddleware())
dp.callback_query.middleware(CallbackActiveMiddleware())

init_db()


@dp.message(Command("start"))
async def start(message: Message):
    add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 Читать книгу (1 часть)", callback_data="open_book")],
            [InlineKeyboardButton(text="💬 Оставить обратную связь", callback_data="feedback_menu")]
        ]
    )

    await message.answer(texts.START_TEXT, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "open_book")
async def open_book(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 Открыть книгу KROSS", web_app={"url": config.WEBAPP_URL})],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_start")]
        ]
    )

    await callback.message.edit_text("Нажмите кнопку ниже, чтобы открыть книгу:", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data == "feedback_menu")
async def feedback_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❓ Вопросы", url=config.QUESTIONS_URL)],
            [InlineKeyboardButton(text="⭐️ Отзывы", callback_data="submit_feedback")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_start")]
        ]
    )

    await callback.message.edit_text("Выберите раздел:", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data == "submit_feedback")
async def start_feedback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "✍️ Напишите ваш отзыв. Он будет отправлен анонимно.\n\n"
        "Чтобы отменить, отправьте /cancel"
    )
    await state.set_state(FeedbackStates.waiting_for_text)
    await callback.answer()


@dp.message(StateFilter(FeedbackStates.waiting_for_text))
async def process_feedback(message: Message, state: FSMContext):
    feedback_text = message.text

    if feedback_text == "/cancel":
        await state.clear()
        await message.answer("❌ Отправка отзыва отменена.")
        return

    success = 0
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📝 <b>Анонимный отзыв</b>\n\n{feedback_text}",
                parse_mode=ParseMode.HTML
            )
            success += 1
        except Exception as e:
            logging.error(f"Не удалось отправить отзыв админу {admin_id}: {e}")

    if success > 0:
        await message.answer("✅ Спасибо! Ваш отзыв анонимно отправлен автору.")
    else:
        await message.answer("❌ Не удалось отправить отзыв. Попробуйте позже.")

    await state.clear()


@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("Действие отменено.")


@dp.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 Читать книгу", callback_data="open_book")],
            [InlineKeyboardButton(text="💬 Оставить обратную связь", callback_data="feedback_menu")]
        ]
    )

    await callback.message.edit_text(texts.START_TEXT, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.message(F.web_app_data)
async def webapp_data(message: Message):
    try:
        data = json.loads(message.web_app_data.data)

        user_id = message.from_user.id
        action = data.get("action")
        session_id = data.get("session_id")
        duration = data.get("duration", 0)
        chapter = data.get("chapter")
        page = data.get("page")

        if action == "start_reading" and session_id:
            start_reading_session(user_id, session_id)
            logging.info(f"Сессия начата: {session_id} для {user_id}")

        elif action == "heartbeat" and session_id:
            update_reading_session(session_id, duration)
            logging.info(f"Обновление сессии {session_id}, длительность {duration}")

        elif action == "end_reading" and session_id:
            end_reading_session(session_id, duration)
            logging.info(f"Сессия {session_id} завершена, длительность {duration}")

        elif action == "chapter_changed" and chapter:
            await message.answer(f"📖 Вы читаете главу {chapter} книги KROSS")

        elif action == "close_app":
            if chapter and page:
                await message.answer(
                    f"📖 Вы остановились:\n"
                    f"Глава {chapter}\n"
                    f"Страница — {page}%"
                )

        else:
            await message.answer("✅ Данные из приложения получены")

    except Exception as e:
        logging.error(f"Ошибка обработки Web App: {e}")
        await message.answer("✅ Данные из приложения получены")


# ================= АДМИН-ПАНЕЛЬ (без изменений) =================
@dp.message(Command("admkross743"))
async def admin_panel(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Включить бота", callback_data="admin_bot_on"),
             InlineKeyboardButton(text="🔴 Выключить бота", callback_data="admin_bot_off")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
        ]
    )

    await message.answer("🔐 Админ-панель", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("admin_"))
async def admin_callbacks(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    action = callback.data

    if action == "admin_bot_on":
        set_bot_state(True)
        await callback.message.edit_text("✅ Бот включён", reply_markup=back_to_admin_keyboard())
        await callback.answer()

    elif action == "admin_bot_off":
        set_bot_state(False)
        await callback.message.edit_text(
            "❌ Бот выключен (режим техобслуживания)",
            reply_markup=back_to_admin_keyboard()
        )
        await callback.answer()

    elif action == "admin_stats":
        stats = get_reading_stats()
        text = f"""📊 Статистика использования:

👥 Активных пользователей:
• за день: {stats['day']}
• за неделю: {stats['week']}
• за месяц: {stats['month']}

⏱ Читали дольше:
• 5 минут: {stats['duration']['>5 мин']}
• 10 минут: {stats['duration']['>10 мин']}
• 30 минут: {stats['duration']['>30 мин']}
• 60 минут: {stats['duration']['>60 мин']}
"""
        await callback.message.edit_text(text, reply_markup=back_to_admin_keyboard())
        await callback.answer()

    elif action == "admin_broadcast":
        await callback.message.edit_text(
            "Введите текст для рассылки (можно использовать HTML-разметку):"
        )
        await callback.answer()
        await state.set_state(BroadcastStates.waiting_for_message)

    elif action == "admin_close":
        await callback.message.delete()
        await callback.answer()


def back_to_admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в админ-панель", callback_data="admin_back")]
        ]
    )


@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Включить бота", callback_data="admin_bot_on"),
             InlineKeyboardButton(text="🔴 Выключить бота", callback_data="admin_bot_off")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
        ]
    )
    await callback.message.edit_text("🔐 Админ-панель", reply_markup=keyboard)
    await callback.answer()


@dp.message(StateFilter(BroadcastStates.waiting_for_message))
async def broadcast_get_message(message: Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.update_data(broadcast_text=message.html_text)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]
        ]
    )
    await message.answer(
        "Проверьте текст. Он будет отправлен всем пользователям.",
        reply_markup=keyboard
    )
    await state.set_state(BroadcastStates.confirm)


@dp.callback_query(StateFilter(BroadcastStates.confirm), F.data == "broadcast_confirm")
async def broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await callback.message.edit_text("Ошибка: текст не найден")
        await state.clear()
        return
    users = get_all_users()
    await callback.message.edit_text(f"Начинаю рассылку {len(users)} пользователям...")
    success = 0
    fail = 0
    for user_id in users:
        try:
            await bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            fail += 1
            logging.error(f"Ошибка отправки {user_id}: {e}")
    await callback.message.edit_text(f"✅ Рассылка завершена.\nУспешно: {success}\nОшибок: {fail}")
    await state.clear()


@dp.callback_query(StateFilter(BroadcastStates.confirm), F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Рассылка отменена", reply_markup=back_to_admin_keyboard())
    await callback.answer()


async def main():
    logging.info("Бот KROSS запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
