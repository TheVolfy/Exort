import os
import sys
from dataclasses import dataclass

# Отображаемое имя приложения/каталог данных
APP_NAME = "Exort"

# Старое имя каталога данных (для миграции)
OLD_APP_NAME = "VoiceLauncher"


def resource_path(rel: str) -> str:
    """
    Возвращает абсолютный путь к ресурсу.
    Поддерживает работу внутри PyInstaller (sys._MEIPASS).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    return os.path.join(os.path.abspath("."), rel)


@dataclass(frozen=True)
class Paths:
    app_dir: str
    settings_json: str
    words_user: str
    words_bundled: str
    model_dir: str
    icon_path: str


def _migrate_old_config(old_name: str, new_dir: str) -> None:
    """
    Переносит базовые файлы настроек из %LOCALAPPDATA%/<old_name> в %LOCALAPPDATA%/<APP_NAME>,
    если новая папка ещё не содержит этих файлов. Все ошибки тихо игнорируются.
    """
    try:
        import shutil

        base_parent = os.path.dirname(new_dir)
        old_dir = os.path.join(base_parent, old_name)

        if not os.path.isdir(old_dir):
            return

        os.makedirs(new_dir, exist_ok=True)

        for fname in ("settings.json", "words.txt"):
            src = os.path.join(old_dir, fname)
            dst = os.path.join(new_dir, fname)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
    except Exception:
        # Миграция — best-effort, падать нельзя
        pass


def get_paths() -> Paths:
    """
    Создаёт структуру путей приложения.
    База: %LOCALAPPDATA%/<APP_NAME> (или домашняя директория, если переменная не определена).
    Выполняет одноразовую миграцию из старой папки (VoiceLauncher) при первом запуске.
    """
    base_root = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
    app_dir = os.path.join(base_root, APP_NAME)

    # Обеспечим существование каталога и попробуем мигрировать старые файлы
    try:
        os.makedirs(app_dir, exist_ok=True)
    finally:
        _migrate_old_config(OLD_APP_NAME, app_dir)

    return Paths(
        app_dir=app_dir,
        settings_json=os.path.join(app_dir, "settings.json"),
        words_user=os.path.join(app_dir, "words.txt"),
        words_bundled=resource_path("words.txt"),
        model_dir=resource_path("model-ru"),
        icon_path=resource_path("icon.ico"),
    )
