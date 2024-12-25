import os
import logging
import requests
import instaloader
import shutil
from datetime import datetime, timedelta
from config.config import INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD

TEMP_FOLDER = "temp"
SESSION_FOLDER = "sessions"  # Папка, где будем хранить файл сессии (по желанию)

# Создание временных папок, если их нет
os.makedirs(TEMP_FOLDER, exist_ok=True)
os.makedirs(SESSION_FOLDER, exist_ok=True)

# Инициализация Instaloader
loader = instaloader.Instaloader()

# -- Если хотите использовать прокси, раскомментируйте строки ниже и укажите ваш прокси --
# proxy = "https://173.212.237.43:32562"
# loader.context._session.proxies = {
#     'http': proxy,
#     'https': proxy
# }

def load_session(username: str, session_file: str = None) -> bool:
    """
    Пытается загрузить ранее сохранённую сессию из файла session_file (по умолчанию session-USERNAME).
    Возвращает True, если сессия загружена успешно, иначе False.
    """
    if session_file is None:
        session_file = os.path.join(SESSION_FOLDER, f"session-{username.lower()}")

    if os.path.exists(session_file):
        try:
            loader.load_session_from_file(username, filename=session_file)
            logging.info(f"Сессия загружена из файла: {session_file}")
            return True
        except Exception as e:
            logging.warning(f"Не удалось загрузить сессию ({session_file}): {e}")
            return False
    else:
        logging.info(f"Файл сессии не найден: {session_file}")
        return False

def save_session(username: str, session_file: str = None):
    """
    Сохраняет текущую сессию Instaloader в файл (по умолчанию session-USERNAME).
    """
    if session_file is None:
        session_file = os.path.join(SESSION_FOLDER, f"session-{username.lower()}")
    try:
        loader.save_session_to_file(filename=session_file)
        logging.info(f"Сессия сохранена в файл: {session_file}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении сессии {session_file}: {e}")

def login(username: str, password: str, use_session=True) -> None:
    """
    Авторизация в Instagram через Instaloader.
    Если use_session=True, сначала пытается загрузить сессию.
    Если не удалось, то логинится по логину/паролю и (при успехе) сохраняет сессию.
    """
    # Попробуем загрузить сессию, если хотим
    if use_session:
        loaded = load_session(username)
        if loaded:
            logging.info("Сессия Instaloader загружена; повторный логин не требуется.")
            return

    # Если не загрузили или use_session=False, делаем классический логин
    try:
        loader.login(username, password)
        logging.info("Успешная авторизация в Instagram.")
        # Если нужно, сохраняем сессию
        if use_session:
            save_session(username)
    except instaloader.exceptions.BadCredentialsException:
        logging.error("Неверный логин или пароль.")
        raise
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        logging.error("Требуется двухфакторная аутентификация.")
        raise
    except Exception as e:
        logging.error(f"Ошибка авторизации: {e}")
        raise

def save_file_from_url(url: str, filename: str, proxies: dict = None) -> str:
    """
    Скачивает файл по URL и сохраняет его во временную папку.
    Возвращает путь к файлу или None при ошибке.
    """
    try:
        filepath = os.path.join(TEMP_FOLDER, filename)
        response = requests.get(url, stream=True, proxies=proxies)
        response.raise_for_status()

        with open(filepath, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)

        return filepath
    except Exception as e:
        logging.error(f"Ошибка при скачивании файла {url}: {e}")
        return None

def delete_temp_file(filepath: str) -> None:
    """
    Удаляет временный файл, если он существует.
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logging.info(f"Удалён временный файл: {filepath}")
    except Exception as e:
        logging.error(f"Ошибка при удалении файла {filepath}: {e}")

def _download_sidecar_nodes(post, username: str, post_id: str) -> list:
    """
    Внутренняя функция: скачивает медиа из карусели (sidecar).
    Возвращает список словарей формата:
    [
      {
        "file_path": "/path/to/file",
        "media_type": "photo" / "video"
      },
      ...
    ]
    """
    media_list = []
    nodes = post.get_sidecar_nodes()
    for node_index, node in enumerate(nodes, start=1):
        if "display_url" in node:
            file_url = node["display_url"]
            is_video = node.get("is_video", False)
            file_extension = "mp4" if is_video else "jpg"
            filename = f"{username}_{post_id}_{node_index}.{file_extension}"
            filepath = save_file_from_url(file_url, filename)
            media_type = "video" if is_video else "photo"
            if filepath:
                media_list.append({
                    "file_path": filepath,
                    "media_type": media_type
                })
    return media_list

def get_stories(username: str):
    """
    Возвращает список сторис пользователя (list[dict]) с ключами:
      [
        {
          "id": int,
          "url": "/path/to/story/file",
          "type": "photo"/"video",
          "date": datetime
        },
        ...
      ]
    Файлы сохраняются в temp/<username>/.
    Если нет сторис, вернёт пустой список.
    """
    try:
        profile = instaloader.Profile.from_username(loader.context, username)
        if not profile.has_viewable_story:
            logging.info(f"У пользователя {username} нет доступных историй.")
            return []

        temp_dir = os.path.join(TEMP_FOLDER, username)
        os.makedirs(temp_dir, exist_ok=True)

        stories = []
        for story in loader.get_stories(userids=[profile.userid]):
            for item in story.get_items():
                file_path = loader.download_storyitem(item, target=temp_dir)
                stories.append({
                    "id": item.mediaid,
                    "url": file_path,
                    "type": "video" if item.is_video else "photo",
                    "date": item.date_local
                })
        return stories

    except instaloader.exceptions.LoginRequiredException:
        logging.warning("Сессия Instaloader истекла. Повторная авторизация...")
        # Переавторизация (загружаем/логиним) и пробуем снова
        login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, use_session=True)
        return get_stories(username)
    except Exception as e:
        logging.error(f"Ошибка при получении историй пользователя {username}: {e}")
        return []

def get_new_posts_count(username: str) -> int:
    """
    Возвращает общее количество публикаций (int) в ленте пользователя username.
    Включает фото, видео, reels (если они в основной ленте).
    """
    try:
        profile = instaloader.Profile.from_username(loader.context, username)
        if not profile:
            return 0
        return profile.mediacount
    except instaloader.exceptions.ProfileNotExistsException:
        logging.error(f"Профиль {username} не существует.")
        return 0
    except Exception as e:
        logging.error(f"Ошибка при получении количества публикаций {username}: {e}")
        return 0

def get_new_posts(
    username: str,
    last_sent_post_id: str = None,
    time_filter: bool = True,
    index: int = None
):
    """
    Получение новых публикаций (или одной конкретной по index).
    Возвращает:
      - dict, если указан index (одна публикация)
      - list[dict], если index не указан (все/новые публикации)

    Параметры:
      - last_sent_post_id: Строковое ID (mediaid) последнего отправленного поста,
        чтобы фильтровать только более "свежие" посты.
      - time_filter: Если True, останавливаемся на постах старше 24 часов (экономия).
      - index: Если задан (int), вернём только конкретный пост из ленты (0-based индекс).
               Если индекс некорректный, вернётся None.
    """
    try:
        profile = instaloader.Profile.from_username(loader.context, username)
        if not profile:
            # Если профиль не найден
            return [] if index is None else None

        # Загружаем список всех постов (ленты)
        posts = list(profile.get_posts())
        if not posts:
            return [] if index is None else None

        # Если запрошен конкретный индекс
        if index is not None:
            if index < 0 or index >= len(posts):
                return None
            post = posts[index]
            post_data = {
                "id": str(post.mediaid),
                "media": [],
                "likes": post.likes,
                "comments": post.comments,  # число комментариев
                "caption": post.caption or ""
            }

            # Если карусель
            if post.typename == "GraphSidecar":
                post_data["media"] = _download_sidecar_nodes(post, username, str(post.mediaid))
            else:
                # Одиночное фото/видео (включая Reels, т.к. GraphVideo)
                is_video = (post.typename == "GraphVideo")
                file_extension = "mp4" if is_video else "jpg"
                filename = f"{username}_{post.mediaid}.{file_extension}"
                filepath = save_file_from_url(post.url, filename)
                if filepath:
                    post_data["media"].append({
                        "file_path": filepath,
                        "media_type": "video" if is_video else "photo"
                    })
            return post_data

        # Иначе — ищем все «новые» посты (за 24 часа), если time_filter=True
        new_posts = []
        now = datetime.now()
        for post in posts:
            post_id = str(post.mediaid)
            post_date = post.date_utc

            # Прекращаем цикл, если пост старше 24 часов (time_filter=True)
            if time_filter and post_date < now - timedelta(days=1):
                break

            # Проверяем, не отправляли ли мы уже этот пост (last_sent_post_id)
            if last_sent_post_id is None or post_id > last_sent_post_id:
                post_data = {
                    "id": post_id,
                    "media": [],
                    "likes": post.likes,
                    "comments": post.comments,
                    "caption": post.caption or ""
                }

                if post.typename == "GraphSidecar":
                    post_data["media"] = _download_sidecar_nodes(post, username, post_id)
                else:
                    is_video = (post.typename == "GraphVideo")
                    file_extension = "mp4" if is_video else "jpg"
                    filename = f"{username}_{post_id}.{file_extension}"
                    filepath = save_file_from_url(post.url, filename)
                    if filepath:
                        post_data["media"].append({
                            "file_path": filepath,
                            "media_type": "video" if is_video else "photo"
                        })

                new_posts.append(post_data)

        return new_posts

    except instaloader.exceptions.ProfileNotExistsException:
        logging.error(f"Профиль {username} не существует.")
        return [] if index is None else None
    except instaloader.exceptions.LoginRequiredException:
        logging.warning("Сессия Instaloader истекла. Переавторизация...")
        login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, use_session=True)
        return get_new_posts(username, last_sent_post_id, time_filter, index)
    except Exception as e:
        logging.error(f"Ошибка при получении публикаций {username}: {e}")
        return [] if index is None else None
