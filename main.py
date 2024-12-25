import asyncio
import logging
import os
import shutil

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardMarkup, InlineKeyboardButton

from database import initialize_database, add_subscription, remove_subscription, get_subscriptions
from instagram_parser import login, get_new_posts, get_new_posts_count, get_stories, delete_temp_file
from scheduler import start_scheduler
from config.config import TELEGRAM_TOKEN, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD


###############################
# НАСТРОЙКИ И ЛОГИРОВАНИЕ
###############################
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

###############################
# ИНИЦИАЛИЗАЦИЯ БОТА
###############################
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
router = Router()

###############################
# ГЛОБАЛЬНЫЕ СЛОВАРИ
###############################
# Храним текущее действие пользователя
user_actions = {}  # {user_id: {"action": "..."}}
# Храним последнее сообщение бота (чтобы удалять старые)
last_bot_message = {}  # {user_id: message_id}
# Храним выбранный язык пользователя
user_lang = {}  # {user_id: "ru" | "en"}

###############################
# ЛОКАЛИЗАЦИЯ
###############################
LOCALES = {
    "ru": {
        "choose_language": "Choose a language:",
        "lang_chosen": "Выбран язык: Русский.",
        "start_text": "👋 Привет! Я помогу тебе отслеживать публикации и истории в Instagram. Выбери действие:",
        "cancel_done": "❌ Действие отменено. Выбери другое действие:",

        "view_story": "📱 Посмотреть историю",
        "view_post": "📷 Посмотреть публикацию",
        "add_account": "➕ Добавить аккаунт",
        "remove_account": "➖ Удалить аккаунт",
        "my_subscriptions": "📋 Мои подписки",

        "cancel_action": "🔙 Назад",

        "ask_username_add": "Введите никнейм аккаунта, который вы хотите добавить:",
        "ask_username_remove": "Введите никнейм аккаунта, который вы хотите удалить:",
        "ask_username_story": "Введите никнейм аккаунта, чтобы посмотреть его истории:",
        "ask_username_post": "🔍 Введите никнейм аккаунта, чтобы посмотреть его публикации:",
        "my_subscriptions": "📋 Мои подписки",
        "no_subs": "❌ У вас пока нет подписок.",
        "subs_list_header": "Ваши подписки:\n",
        "found_publications": "📄 Найдено {count} публикаций. Выберите публикацию:",
        "no_publications_user": "❌ У аккаунта {username} нет доступных публикаций.",
        "no_publications_plain": "❌ Не удалось загрузить публикацию. Попробуйте снова.",
        "publications_error": "❌ Не удалось получить публикации. Попробуйте позже.",
        "add_account_success": "✅ Аккаунт {username} добавлен.",
        "add_account_error": "❌ Ошибка при добавлении. Попробуйте позже.",
        "remove_account_success": "❌ Аккаунт {username} удалён.",
        "remove_account_error": "❌ Не удалось удалить аккаунт. Попробуйте позже.",
        "stories_sent": "Все доступные истории отправлены!",
        "stories_error": "❌ Не удалось получить истории. Попробуйте позже.",
        "stories_none": "❌ У аккаунта {username} нет доступных историй.",
        "unknown_action": "❌ Неизвестное действие. Возвращаюсь в главное меню.",
        "pick_command": "Пожалуйста, выберите команду из меню:",
        "bot_owner_text": "Я не могу следить за своим создателем.",
        "loading": "Загрузка… Пожалуйста, подождите...",

        "change_language" : "🌍 Поменять язык"
    },
    "en": {
        "choose_language": "Choose a language:",
        "lang_chosen": "Language selected: English.",
        "start_text": "👋 Hello! I will help you track Instagram posts and stories. Choose an action:",
        "cancel_done": "❌ Action canceled. Choose another action:",

        "view_story": "📱 View story",
        "view_post": "📷 View publication",
        "add_account": "➕ Add account",
        "remove_account": "➖ Delete account",
        "my_subscriptions": "📋 My subscriptions",

        "cancel_action": "🔙 Back",

        "ask_username_add": "Enter the username you want to add:",
        "ask_username_remove": "Enter the username you want to remove:",
        "ask_username_story": "Enter the username to view stories:",
        "ask_username_post": "🔍 Enter the username to view posts:",
        "my_subscriptions": "📋 My subscriptions",
        "no_subs": "❌ You have no subscriptions yet.",
        "subs_list_header": "Your subscriptions:\n",
        "found_publications": "📄 Found {count} publications. Choose one:",
        "no_publications_user": "❌ This user has no available publications: {username}",
        "no_publications_plain": "❌ Could not load the publication. Try again.",
        "publications_error": "❌ Could not retrieve publications. Try later.",
        "add_account_success": "✅ Account {username} has been added.",
        "add_account_error": "❌ Unable to add account. Try later.",
        "remove_account_success": "❌ Account {username} has been removed.",
        "remove_account_error": "❌ Could not remove the account. Try later.",
        "stories_sent": "All available stories have been sent!",
        "stories_error": "❌ Could not retrieve stories. Try later.",
        "stories_none": "❌ This user has no available stories: {username}",
        "unknown_action": "❌ Unknown action. Returning to main menu.",
        "pick_command": "Please choose a command from the menu:",
        "bot_owner_text": "I cannot track my creator.",
        "loading": "Loading… Please wait...",

        "change_language" : "🌎 Change language"
    }
}

def get_lang(user_id: int) -> str:
    """
    Возвращает язык пользователя (по умолчанию 'ru', если нет в словаре).
    """
    return user_lang.get(user_id, "ru")

def t(user_id: int, key: str, **kwargs) -> str:
    """
    Функция для получения локализованного текста из LOCALES.
    """
    lang = get_lang(user_id)
    translation_dict = LOCALES.get(lang, LOCALES["ru"])
    text = translation_dict.get(key, f"[[{key}]]")
    if kwargs:
        text = text.format(**kwargs)
    return text

###############################
# ВЫБОР ЯЗЫКА: КЛАВИАТУРА И ОБРАБОТКА
###############################
def choose_language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="English", callback_data="lang:en")
        ],
        [
            InlineKeyboardButton(text="❌", callback_data="cancel")
        ]
    ])

@router.callback_query(lambda c: c.data.startswith("lang:"))
async def language_chosen(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang_code = callback.data.split(":")[1]
    if lang_code not in ["ru", "en"]:
        await callback.answer("Unsupported language!")
        return
    # Сохраняем язык
    user_lang[user_id] = lang_code
    await callback.answer(t(user_id, "lang_chosen"))
    # Показываем главное меню
    await callback.message.edit_text(
        t(user_id, "start_text"),
        reply_markup=start_keyboard(user_id)
    )

###############################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ОТПРАВКИ
###############################
async def delete_previous_message_if_exists(chat_id: int):
    old_msg_id = last_bot_message.get(chat_id)
    if old_msg_id:
        try:
            await bot.delete_message(chat_id, old_msg_id)
        except Exception as e:
            logging.warning(f"Failed to delete message {old_msg_id}: {e}")

async def send_text_message(chat_id: int, user_id: int, key: str, reply_markup=None, **fmt_kwargs):
    """
    Локализованная отправка текста (через key).
    """
    await delete_previous_message_if_exists(chat_id)
    text = t(user_id, key, **fmt_kwargs)
    new_msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    last_bot_message[chat_id] = new_msg.message_id
    return new_msg

async def send_custom_text(chat_id: int, text: str, user_id: int, reply_markup=None):
    """
    Отправка произвольного текста без локализации.
    """
    await delete_previous_message_if_exists(chat_id)
    new_msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    last_bot_message[chat_id] = new_msg.message_id
    return new_msg

async def send_photo_message(chat_id: int, photo, user_id: int, caption_key=None, **fmt):
    """
    Удаляет старое сообщение, затем отправляет фото
    caption_key => ключ из LOCALES (необязательно)
    """
    await delete_previous_message_if_exists(chat_id)
    caption_text = t(user_id, caption_key, **fmt) if caption_key else ""
    new_msg = await bot.send_photo(chat_id, photo=photo, caption=caption_text)
    last_bot_message[chat_id] = new_msg.message_id
    return new_msg

async def send_video_message(chat_id: int, video, user_id: int, caption_key=None, **fmt):
    """
    Аналогично send_photo_message
    """
    await delete_previous_message_if_exists(chat_id)
    caption_text = t(user_id, caption_key, **fmt) if caption_key else ""
    new_msg = await bot.send_video(chat_id, video=video, caption=caption_text)
    last_bot_message[chat_id] = new_msg.message_id
    return new_msg

async def send_loading_message(chat_id: int, user_id: int):
    """
    Отправляем "Загрузка…" (или "Loading...")
    """
    await delete_previous_message_if_exists(chat_id)
    new_msg = await bot.send_message(chat_id, t(user_id, "loading"))
    last_bot_message[chat_id] = new_msg.message_id
    return new_msg.message_id

###############################
# ГЛАВНОЕ МЕНЮ
###############################
def start_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(user_id, "view_story"), callback_data="ask_username_story")],
        [InlineKeyboardButton(text=t(user_id, "view_post"), callback_data="ask_username_post")],
        [InlineKeyboardButton(text=t(user_id, "add_account"), callback_data="ask_username_add")],
        [InlineKeyboardButton(text=t(user_id, "remove_account"), callback_data="ask_username_remove")],
        [InlineKeyboardButton(text=t(user_id, "my_subscriptions"), callback_data="list_subscriptions")],
        [InlineKeyboardButton(text=t(user_id, "change_language"), callback_data="choose_language")]
    ])

def generate_post_pagination_keyboard(user_id: int, current_page, total_pages, posts_per_page):
    keyboard = []
    start_index = (current_page - 1) * posts_per_page + 1
    end_index = min(current_page * posts_per_page, total_pages * posts_per_page)

    for i in range(start_index, end_index + 1):
        keyboard.append([InlineKeyboardButton(text=str(i), callback_data=f"select_post:{i}")])

    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"page:{current_page - 1}"))
    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"page:{current_page + 1}"))
    nav_buttons.append(InlineKeyboardButton(text=t(user_id, "cancel_action"), callback_data="cancel"))
    keyboard.append(nav_buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

###############################
# ХЕНДЛЕРЫ
###############################
@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user_actions.pop(user_id, None)

    # Если пользователь еще не выбирал язык, показываем кнопки выбора
    if user_id not in user_lang:
        await message.answer(LOCALES["ru"]["choose_language"], reply_markup=choose_language_keyboard())
    else:
        await message.answer(
            t(user_id, "start_text"),
            reply_markup=start_keyboard(user_id)
        )

@router.callback_query(lambda c: c.data == "choose_language")
async def callback_choose_language(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    await callback.message.edit_text(
        LOCALES["ru"]["choose_language"],  # Или брать t(user_id, "choose_language") если хотите
        reply_markup=choose_language_keyboard()
    )

@router.callback_query(lambda q: q.data == "cancel")
async def handle_cancel(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    user_actions.pop(user_id, None)
    await callback.message.edit_text(
        t(user_id, "cancel_done"),
        reply_markup=start_keyboard(user_id)
    )

@router.callback_query(lambda q: q.data == "ask_username_add")
async def cb_add_account(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    user_actions[user_id] = {"action": "add_account"}
    await callback.message.edit_text(
        t(user_id, "ask_username_add"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "cancel_action"), callback_data="cancel")]]
        )
    )

@router.callback_query(lambda q: q.data == "ask_username_remove")
async def cb_remove_account(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    user_actions[user_id] = {"action": "remove_account"}
    await callback.message.edit_text(
        t(user_id, "ask_username_remove"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "cancel_action"), callback_data="cancel")]]
        )
    )

@router.callback_query(lambda q: q.data == "ask_username_story")
async def view_story_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    user_actions[user_id] = {"action": "view_story"}
    await callback.message.edit_text(
        t(user_id, "ask_username_story"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "cancel_action"), callback_data="cancel")]]
        )
    )

@router.callback_query(lambda q: q.data == "ask_username_post")
async def view_post_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    user_actions[user_id] = {"action": "view_post"}
    await callback.message.edit_text(
        t(user_id, "ask_username_post"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "cancel_action"), callback_data="cancel")]]
        )
    )

@router.callback_query(lambda q: q.data == "list_subscriptions")
async def list_subscriptions_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    subs = get_subscriptions(user_id)
    if subs:
        response = t(user_id, "subs_list_header") + "\n".join(f"- {username}" for _, username, _ in subs)
    else:
        response = t(user_id, "no_subs")

    await callback.message.edit_text(
        response,
        reply_markup=start_keyboard(user_id)
    )

@router.callback_query(lambda q: q.data.startswith("page:"))
async def handle_pagination(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    action_data = user_actions.get(user_id)
    if action_data and action_data.get("action") == "pagination":
        current_page = int(callback.data.split(":")[1])
        total_pages = action_data["total_pages"]
        posts_per_page = action_data["posts_per_page"]
        await callback.message.edit_text(
            t(user_id, "found_publications", count="..."),  # Можно улучшить
            reply_markup=generate_post_pagination_keyboard(user_id, current_page, total_pages, posts_per_page)
        )

@router.callback_query(lambda q: q.data.startswith("select_post:"))
async def handle_post_selection(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    action_data = user_actions.get(user_id)
    if not action_data or action_data.get("action") != "pagination":
        return

    post_number = int(callback.data.split(":")[1]) - 1
    username = action_data["username"]

    # "Loading..."
    await delete_previous_message_if_exists(user_id)
    new_msg = await bot.send_message(user_id, t(user_id, "loading"))
    last_bot_message[user_id] = new_msg.message_id

    try:
        post = get_new_posts(username, index=post_number, time_filter=False)
        if post:
            for media in post["media"]:
                media_type = media["media_type"]
                file_path = media["file_path"]
                if media_type == "photo":
                    await send_photo_message(user_id, FSInputFile(file_path), user_id)
                else:
                    await send_video_message(user_id, FSInputFile(file_path), user_id)

            likes = post["likes"]
            comments = post["comments"]
            likes_text = "Лайки: скрыты" if (0 <= likes <= 3) else f"👍 Лайков: {likes}"
            caption = f"{likes_text}\n📝 Комментариев: {comments}\n📄 {post['caption']}"
            await send_custom_text(user_id, caption, user_id)
            
            for media in post["media"]:
                delete_temp_file(media["file_path"])
        else:
            await send_custom_text(user_id, t(user_id, "no_publications_plain"), user_id)
    except Exception as e:
        logging.error(f"Ошибка при получении поста: {e}")
        await send_custom_text(user_id, t(user_id, "publications_error"), user_id)

@router.message()
async def handle_user_input(message: Message):
    user_id = message.from_user.id
    action_data = user_actions.get(user_id)
    if not action_data:
        await send_custom_text(
            user_id,
            t(user_id, "pick_command"),
            user_id,
            reply_markup=start_keyboard(user_id)
        )
        return

    # Loading
    await delete_previous_message_if_exists(user_id)
    new_msg = await bot.send_message(user_id, t(user_id, "loading"))
    last_bot_message[user_id] = new_msg.message_id

    user_action = action_data["action"]
    username = message.text.strip().lower()

    try:
        # Запрет на lncemep / crazyportes
        if user_action in ["add_account", "view_post", "view_story"]:
            if username in ["lncemep", "crazyportes"]:
                await send_custom_text(
                    user_id, t(user_id, "bot_owner_text"), user_id,
                    reply_markup=start_keyboard(user_id)
                )
                user_actions.pop(user_id, None)
                return

        if user_action == "add_account":
            try:
                add_subscription(user_id, username)
                await send_custom_text(
                    user_id,
                    t(user_id, "add_account_success", username=username),
                    user_id,
                    reply_markup=start_keyboard(user_id)
                )
            except Exception as e:
                logging.error(f"Add account error: {e}")
                await send_custom_text(
                    user_id,
                    t(user_id, "add_account_error"),
                    user_id,
                    reply_markup=start_keyboard(user_id)
                )
            finally:
                user_actions.pop(user_id, None)

        elif user_action == "remove_account":
            try:
                remove_subscription(user_id, username)
                await send_custom_text(
                    user_id,
                    t(user_id, "remove_account_success", username=username),
                    user_id,
                    reply_markup=start_keyboard(user_id)
                )
            except Exception as e:
                logging.error(f"Remove account error: {e}")
                await send_custom_text(
                    user_id,
                    t(user_id, "remove_account_error"),
                    user_id,
                    reply_markup=start_keyboard(user_id)
                )
            finally:
                user_actions.pop(user_id, None)

        elif user_action == "view_post":
            try:
                post_count = get_new_posts_count(username)
                if post_count > 0:
                    posts_per_page = 5
                    total_pages = (post_count + posts_per_page - 1) // posts_per_page
                    user_actions[user_id] = {
                        "action": "pagination",
                        "username": username,
                        "total_pages": total_pages,
                        "posts_per_page": posts_per_page
                    }
                    await send_custom_text(
                        user_id,
                        t(user_id, "found_publications", count=post_count),
                        user_id,
                        reply_markup=generate_post_pagination_keyboard(user_id, 1, total_pages, posts_per_page)
                    )
                else:
                    await send_custom_text(
                        user_id,
                        t(user_id, "no_publications_user", username=username),
                        user_id,
                        reply_markup=start_keyboard(user_id)
                    )
                    user_actions.pop(user_id, None)
            except Exception as e:
                logging.error(f"Get publications error: {e}")
                await send_custom_text(
                    user_id,
                    t(user_id, "publications_error"),
                    user_id,
                    reply_markup=start_keyboard(user_id)
                )
                user_actions.pop(user_id, None)

        elif user_action == "view_story":
            try:
                stories = await asyncio.to_thread(get_stories, username)
                if stories:
                    for story in stories:
                        with open(story["url"], "rb") as f:
                            if story["type"] == "photo":
                                await send_photo_message(user_id, f, user_id)
                            else:
                                await send_video_message(user_id, f, user_id)
                        os.remove(story["url"])

                    temp_dir = os.path.dirname(stories[0]["url"])
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)

                    await send_custom_text(user_id, t(user_id, "stories_sent"), user_id, reply_markup=start_keyboard(user_id))
                else:
                    await send_custom_text(
                        user_id,
                        t(user_id, "stories_none", username=username),
                        user_id,
                        reply_markup=start_keyboard(user_id)
                    )
                user_actions.pop(user_id, None)
            except Exception as e:
                logging.error(f"Get stories error: {e}")
                await send_custom_text(
                    user_id,
                    t(user_id, "stories_error"),
                    user_id,
                    reply_markup=start_keyboard(user_id)
                )
                user_actions.pop(user_id, None)

        else:
            # Неизвестное действие
            await send_custom_text(
                user_id,
                t(user_id, "unknown_action"),
                user_id,
                reply_markup=start_keyboard(user_id)
            )
            user_actions.pop(user_id, None)

    finally:
        pass


###############################
# ЗАПУСК
###############################
async def main():
    logging.info("Инициализация базы данных...")
    initialize_database()

    logging.info("Авторизация в Instagram...")
    try:
        login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    except Exception as e:
        logging.error(f"Ошибка авторизации в Instagram: {e}")
        return

    dp.include_router(router)
    logging.info("Запуск планировщика задач...")
    asyncio.create_task(start_scheduler(bot))

    logging.info("Запуск Telegram-бота...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен вручную.")
