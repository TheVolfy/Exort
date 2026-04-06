import json
import os
from tkinter import messagebox
from .paths import get_paths

# --- Значения по умолчанию ---
DEFAULT_WAKE_PHRASE = "гей секс"
DEFAULT_GAME_PATH = "steam://rungameid/570"
DEFAULT_USE_CUSTOM_DICT = True
DEFAULT_VOLUME_PERCENT = 100
DEFAULT_SHOW_RECOG_LOG = True   # показывать распознанный текст
DEFAULT_SHOW_EVENT_LOG = True   # показывать служебные уведомления

# Команды/ключевые слова
DEFAULT_GLYPH_PHRASE    = "запиши укрепление"
DEFAULT_BUYBACK_PHRASE  = "запиши выкуп героя"
DEFAULT_KW_PAUSE        = "пауза"
DEFAULT_KW_RESUME       = "продолжить"
DEFAULT_KW_CANCEL       = "отмена"
DEFAULT_KW_ALL          = "все"

# Внешний вид
DEFAULT_UI_THEME   = "dark"       # "dark" | "light"
DEFAULT_UI_ACCENT  = "#00A2FF"    # акцентный цвет в HEX
DEFAULT_UI_SCALE   = 100          # %, 80..150

# Геометрия окна (например "1024x700+200+120") — None: использовать дефолт из app.py
DEFAULT_WINDOW_GEOMETRY = None


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def load_settings() -> dict:
    p = get_paths()
    try:
        with open(p.settings_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "wake_phrase":           _norm(data.get("wake_phrase", DEFAULT_WAKE_PHRASE)),
                "game_path":             (data.get("game_path", DEFAULT_GAME_PATH) or "").strip(),
                "input_device":          data.get("input_device", None),
                "use_custom_dict":       bool(data.get("use_custom_dict", DEFAULT_USE_CUSTOM_DICT)),
                "volume_percent":        int(data.get("volume_percent", DEFAULT_VOLUME_PERCENT)),
                "show_recognition_log":  bool(data.get("show_recognition_log", DEFAULT_SHOW_RECOG_LOG)),
                "show_event_log":        bool(data.get("show_event_log", DEFAULT_SHOW_EVENT_LOG)),
                # команды
                "glyph_phrase":          _norm(data.get("glyph_phrase", DEFAULT_GLYPH_PHRASE)),
                "buyback_phrase":        _norm(data.get("buyback_phrase", DEFAULT_BUYBACK_PHRASE)),
                "kw_pause":              _norm(data.get("kw_pause", DEFAULT_KW_PAUSE)),
                "kw_resume":             _norm(data.get("kw_resume", DEFAULT_KW_RESUME)),
                "kw_cancel":             _norm(data.get("kw_cancel", DEFAULT_KW_CANCEL)),
                "kw_all":                _norm(data.get("kw_all", DEFAULT_KW_ALL)),
                # внешний вид
                "ui_theme":              _norm(data.get("ui_theme", DEFAULT_UI_THEME)),
                "ui_accent":             (data.get("ui_accent", DEFAULT_UI_ACCENT) or "#00A2FF").strip(),
                "ui_scale":              int(data.get("ui_scale", DEFAULT_UI_SCALE)),
                # геометрия окна
                "window_geometry":       data.get("window_geometry", DEFAULT_WINDOW_GEOMETRY),
            }
    except Exception:
        # Файл отсутствует или битый — вернём дефолты
        return {
            "wake_phrase":          DEFAULT_WAKE_PHRASE,
            "game_path":            DEFAULT_GAME_PATH,
            "input_device":         None,
            "use_custom_dict":      DEFAULT_USE_CUSTOM_DICT,
            "volume_percent":       DEFAULT_VOLUME_PERCENT,
            "show_recognition_log": DEFAULT_SHOW_RECOG_LOG,
            "show_event_log":       DEFAULT_SHOW_EVENT_LOG,
            "glyph_phrase":         DEFAULT_GLYPH_PHRASE,
            "buyback_phrase":       DEFAULT_BUYBACK_PHRASE,
            "kw_pause":             DEFAULT_KW_PAUSE,
            "kw_resume":            DEFAULT_KW_RESUME,
            "kw_cancel":            DEFAULT_KW_CANCEL,
            "kw_all":               DEFAULT_KW_ALL,
            "ui_theme":             DEFAULT_UI_THEME,
            "ui_accent":            DEFAULT_UI_ACCENT,
            "ui_scale":             DEFAULT_UI_SCALE,
            "window_geometry":      DEFAULT_WINDOW_GEOMETRY,
        }


def save_settings(
    wake_phrase: str,
    game_path: str,
    input_device: int | None,
    use_custom_dict: bool,
    volume_percent: int,
    show_recognition_log: bool,
    show_event_log: bool,
    # команды:
    glyph_phrase: str,
    buyback_phrase: str,
    kw_pause: str,
    kw_resume: str,
    kw_cancel: str,
    kw_all: str,
    # внешний вид:
    ui_theme: str,
    ui_accent: str,
    ui_scale: int,
    # новое (опционально):
    window_geometry: str | None = None,
) -> None:
    """
    Сохраняет настройки. Параметр window_geometry опционален — если не передан,
    в файле останется текущее значение (если есть).
    """
    p = get_paths()
    try:
        # Если уже есть файл, подмерджим window_geometry (чтобы не терять при вызовах из UI)
        existing = {}
        if os.path.isfile(p.settings_json):
            try:
                with open(p.settings_json, "r", encoding="utf-8") as f:
                    existing = json.load(f) or {}
            except Exception:
                existing = {}

        os.makedirs(p.app_dir, exist_ok=True)
        with open(p.settings_json, "w", encoding="utf-8") as f:
            payload = {
                "wake_phrase":          _norm(wake_phrase),
                "game_path":            (game_path or "").strip(),
                "input_device":         input_device,
                "use_custom_dict":      bool(use_custom_dict),
                "volume_percent":       int(volume_percent),
                "show_recognition_log": bool(show_recognition_log),
                "show_event_log":       bool(show_event_log),

                "glyph_phrase":         _norm(glyph_phrase),
                "buyback_phrase":       _norm(buyback_phrase),
                "kw_pause":             _norm(kw_pause),
                "kw_resume":            _norm(kw_resume),
                "kw_cancel":            _norm(kw_cancel),
                "kw_all":               _norm(kw_all),

                "ui_theme":             _norm(ui_theme) if ui_theme else DEFAULT_UI_THEME,
                "ui_accent":            (ui_accent or DEFAULT_UI_ACCENT).strip(),
                "ui_scale":             max(80, min(150, int(ui_scale))),
                # если параметр не передали — оставим прежний (если был)
                "window_geometry":      window_geometry if window_geometry is not None
                                        else existing.get("window_geometry", DEFAULT_WINDOW_GEOMETRY),
            }
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # В UI мы можем быть без главного окна — поэтому try/except вокруг messagebox
        try:
            messagebox.showwarning("Сохранение настроек", f"Не удалось сохранить настройки:\n{e}")
        except Exception:
            pass
