import asyncio
import logging
from datetime import datetime
from database import get_subscriptions, update_last_sent_post_id
from instagram_parser import get_new_posts, get_stories
from aiogram import Bot

async def check_updates(bot: Bot, user_id=None, username=None, action=None):
    """
    Проверяет новые публикации и истории для всех подписок или конкретного пользователя.
    :param bot: экземпляр бота.
    :param user_id: ID пользователя Telegram (опционально).
    :param username: Никнейм Instagram (опционально).
    :param action: Действие ("story" или "post").
    """
    logging.info(f"{datetime.now()} - Проверка обновлений...")

    if user_id and username:
        # Если указан конкретный пользователь и действие
        subscriptions = [(user_id, username, None)]
    else:
        # Если проверяем все подписки
        subscriptions = get_subscriptions()

    for subscription in subscriptions:
        telegram_user_id, insta_username, last_sent_post_id = subscription

        if action == "post" or action is None:
            # Проверяем новые публикации
            new_posts = get_new_posts(insta_username, last_sent_post_id)
            if new_posts:
                for post in new_posts:
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=(
                            f"Новый пост от {insta_username}:\n"
                            f"{post['url']}\n"
                            f"👍 Лайков: {post['likes']} 📝 Комментариев: {post['comments']}"
                        )
                    )

                # Обновляем last_sent_post_id
                last_post_id = new_posts[-1]["id"]
                update_last_sent_post_id(telegram_user_id, insta_username, last_post_id)

        if action == "story" or action is None:
            # Проверяем новые истории
            stories = get_stories(insta_username)
            if stories:
                for story in stories:
                    await bot.send_photo(
                        chat_id=telegram_user_id,
                        photo=story['url'],
                        caption=f"Новая история от {insta_username}"
                    )

    logging.info(f"{datetime.now()} - Обновления проверены.")

async def start_scheduler(bot: Bot):
    """
    Запускает планировщик задач, который выполняется каждые 24 часа.
    :param bot: экземпляр бота.
    """
    while True:
        try:
            await check_updates(bot)
        except Exception as e:
            logging.error(f"Ошибка в планировщике: {e}")
        await asyncio.sleep(86400)  # 24 часа
