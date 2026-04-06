from .ui import App
from .settings_store import load_settings, save_settings


def main():
    s = load_settings()

    # Читаем сохранённый размер и позицию окна (если есть)
    geom = s.get("window_geometry")
    if not geom or not isinstance(geom, str) or "x" not in geom:
        geom = "1000x650"  # значение по умолчанию

    app = App()
    try:
        app.geometry(geom)
    except Exception:
        app.geometry("1000x650")

    # Минимальный размер
    app.minsize(900, 600)

    # Сохраняем позицию и размер при закрытии
    old_on_close = getattr(app, "on_close", None)

    def _wrapped_on_close():
        try:
            geom_now = app.geometry()
            s2 = load_settings()
            s2["window_geometry"] = geom_now
            save_settings(**s2)
        except Exception:
            pass
        if callable(old_on_close):
            old_on_close()

    app.protocol("WM_DELETE_WINDOW", _wrapped_on_close)

    app.mainloop()
