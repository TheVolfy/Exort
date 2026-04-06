import os
from typing import Tuple, List
from .paths import get_paths


def ensure_words_file(wake_phrase: str) -> None:
    """Создаёт пользовательский файл словаря, если его нет."""
    p = get_paths()
    os.makedirs(p.app_dir, exist_ok=True)
    if not os.path.isfile(p.words_user):
        template = f"""# Список слов и фраз (по одной в строке)
# Пустые строки и строки, начинающиеся с #, игнорируются.
# После изменения сохраните файл и нажмите «Перезагрузить словарь».

{(wake_phrase or '').lower()}
дота
гта
сталкер
киберпанк
запусти игру
"""
        with open(p.words_user, "w", encoding="utf-8") as f:
            f.write(template)


def _read_words(path: str) -> List[str]:
    """Читает слова из файла словаря, исключая комментарии и пустые строки."""
    items: List[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                items.append(line.lower())
    except Exception:
        pass
    return items


def pick_words_file() -> Tuple[str, str]:
    """Определяет, какой словарь использовать — пользовательский или встроенный."""
    p = get_paths()
    if os.path.isfile(p.words_user) and os.path.getsize(p.words_user) > 0:
        return p.words_user, "пользовательский"
    return p.words_bundled, "встроенный"


def load_words_list(wake_phrase: str) -> tuple[list[str], str, str]:
    """Загружает список слов и возвращает (список, путь, источник)."""
    path, source = pick_words_file()
    items = _read_words(path)
    if wake_phrase and wake_phrase.lower() not in items:
        items.append(wake_phrase.lower())
    if not items and wake_phrase:
        items = [wake_phrase.lower()]
    return items, path, source


def get_mtime(path: str) -> float:
    """Возвращает время последнего изменения файла словаря."""
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0
