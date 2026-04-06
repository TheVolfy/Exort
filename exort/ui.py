import os
import sys
import subprocess
import difflib
import tkinter as tk
from tkinter import scrolledtext, messagebox, colorchooser
import tkinter.ttk as ttk
import tkinter.font as tkfont

import vosk

# --- ГИБКИЕ ИМПОРТЫ ---
try:
    from .paths import get_paths, resource_path
    from .settings_store import load_settings, save_settings
    from .dictionary import ensure_words_file
    from .audio_recognizer import RecognizerEngine
except Exception:
    try:
        from exort.paths import get_paths, resource_path
        from exort.settings_store import load_settings, save_settings
        from exort.dictionary import ensure_words_file
        from exort.audio_recognizer import RecognizerEngine
    except Exception:
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
        from paths import get_paths, resource_path          # type: ignore
        from settings_store import load_settings, save_settings  # type: ignore
        from dictionary import ensure_words_file            # type: ignore
        from audio_recognizer import RecognizerEngine       # type: ignore

# Порог "похожести" для фаззи-сопоставления
SIM_THRESHOLD = 0.86

# Пресеты акцент-цветов
ACCENT_PRESETS = {
    "Cyan":   "#00A2FF",
    "Lime":   "#7ED321",
    "Purple": "#8A63D2",
    "Amber":  "#FFB300",
    "Pink":   "#FF4DA6",
}

# Диалоговые шрифты (используем именованные для автоскейла)
DLG_FONT_LABEL_NAME = "ExortDlgLabel"
DLG_FONT_EDIT_NAME  = "ExortDlgEdit"
DLG_FONT_BOLD_NAME  = "ExortDlgBold"


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "").strip()
    if not h.startswith("#"):
        raise ValueError("HEX color must start with #")
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError("HEX color must be 3 or 6 digits")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(x))) for x in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _blend(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return _rgb_to_hex((r, g, b))


class SettingsDialog(tk.Toplevel):
    """
    Диалог настроек:
      - поля, логи, команды
      - внешний вид: тема, акцент, пресеты, масштаб UI (лейбл %, кнопка «Сбросить», применение при отпускании)
      - «Открыть словарь…» центрируется
      - кнопки «Сохранить/Закрыть» — самым нижним блоком
    """

    def __init__(
        self,
        parent,
        icon_path: str,
        wake_phrase: str,
        game_path: str,
        input_device: int | None,
        use_custom_dict: bool,
        current_volume_percent: int,
        cur_show_recog: bool,
        cur_show_events: bool,
        # команды
        glyph_phrase: str,
        buyback_phrase: str,
        kw_pause: str,
        kw_resume: str,
        kw_cancel: str,
        kw_all: str,
        # внешний вид
        ui_theme: str,
        ui_accent: str,
        ui_scale: int,
        # callbacks
        on_save,
        on_test_sound_with_volume,
    ):
        super().__init__(parent)
        self.title("Настройки")
        self.resizable(True, True)
        self.on_save = on_save
        self.on_test_sound_with_volume = on_test_sound_with_volume
        self._parent_app = parent

        # Иконка
        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        # --------- Локальные стили диалога ----------
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Именованные шрифты диалога (подчиняются глобальному пересчёту)
        sf = max(0.8, min(1.6, (getattr(parent, "ui_scale", ui_scale) or 100) / 100.0))
        self.font_label = tkfont.Font(name=DLG_FONT_LABEL_NAME, family="Segoe UI", size=int(11 * sf), exists=True) \
            if DLG_FONT_LABEL_NAME in tkfont.names() else tkfont.Font(name=DLG_FONT_LABEL_NAME, family="Segoe UI", size=int(11 * sf))
        self.font_edit  = tkfont.Font(name=DLG_FONT_EDIT_NAME,  family="Segoe UI", size=int(12 * sf), exists=True) \
            if DLG_FONT_EDIT_NAME in tkfont.names() else tkfont.Font(name=DLG_FONT_EDIT_NAME,  family="Segoe UI", size=int(12 * sf))
        self.font_bold  = tkfont.Font(name=DLG_FONT_BOLD_NAME,  family="Segoe UI", size=int(11 * sf), weight="bold", exists=True) \
            if DLG_FONT_BOLD_NAME in tkfont.names() else tkfont.Font(name=DLG_FONT_BOLD_NAME,  family="Segoe UI", size=int(11 * sf), weight="bold")

        style.configure("Dlg.TFrame")
        style.configure("Dlg.TLabel", font=self.font_label)
        style.configure("DlgBold.TLabel", font=self.font_bold)
        style.configure("Dlg.TButton", font=self.font_edit, padding=8)
        style.configure("DlgAccent.TButton", font=self.font_edit, padding=8)
        style.configure("Dlg.TCheckbutton", font=self.font_label)
        style.configure("Dlg.TRadiobutton", font=self.font_label)
        style.configure("Dlg.TEntry", font=self.font_edit)
        style.configure("Dlg.TCombobox", font=self.font_edit)
        style.configure("Dlg.TLabelframe")
        style.configure("Dlg.TLabelframe.Label", font=self.font_bold)

        # --- Кастомный индикатор чекбокса ---
        self._img_chk = None
        self._img_unchk = None
        try:
            size = 14
            pad = 1
            img0 = tk.PhotoImage(width=size, height=size)
            bg = self.cget("bg") or "#FFFFFF"
            img0.put(bg, to=(0, 0, size, size))
            for x in range(size):
                img0.put("#6c6c6c", (x, 0))
                img0.put("#6c6c6c", (x, size-1))
            for y in range(size):
                img0.put("#6c6c6c", (0, y))
                img0.put("#6c6c6c", (size-1, y))

            img1 = tk.PhotoImage(width=size, height=size)
            img1.put(bg, to=(0, 0, size, size))
            for x in range(size):
                img1.put("#6c6c6c", (x, 0))
                img1.put("#6c6c6c", (x, size-1))
            for y in range(size):
                img1.put("#6c6c6c", (0, y))
                img1.put("#6c6c6c", (size-1, y))
            img1.put("#3a8dde", to=(pad, pad, size-pad, size-pad))

            self._img_unchk, self._img_chk = img0, img1

            style.element_create("Chk.indicator", "image", self._img_unchk,
                                 ("selected", self._img_chk), ("!selected", self._img_unchk),
                                 ("active", self._img_chk))
            style.layout("Chk.TCheckbutton", [
                ("Checkbutton.padding", {"children": [
                    ("Chk.indicator", {"side": "left"}),
                    ("Checkbutton.label", {"side": "left", "sticky": "w"})
                ]})
            ])
            style.configure("Chk.TCheckbutton", font=self.font_label)
            chk_style_name = "Chk.TCheckbutton"
        except Exception:
            chk_style_name = "Dlg.TCheckbutton"
        self._chk_style = chk_style_name

        # ====== Контент ======
        root = ttk.Frame(self, style="Dlg.TFrame")
        root.pack(fill="both", expand=True)
        content = ttk.Frame(root, style="Dlg.TFrame")
        content.pack(fill="both", expand=True, padx=12, pady=12)

        # --- Основные поля ---
        ttk.Label(content, text="Ключевая фраза (запуск игры):", style="Dlg.TLabel").grid(row=0, column=0, sticky="w")
        self.e_phrase = ttk.Entry(content, style="Dlg.TEntry")
        self.e_phrase.grid(row=0, column=1, sticky="we", padx=(8, 0))
        self.e_phrase.insert(0, wake_phrase)

        ttk.Label(content, text="Игра / URI:", style="Dlg.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.e_game = ttk.Entry(content, style="Dlg.TEntry")
        self.e_game.grid(row=1, column=1, sticky="we", padx=(8, 0), pady=(8, 0))
        self.e_game.insert(0, game_path)

        # Источник словаря
        ttk.Label(content, text="Источник словаря:", style="Dlg.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))
        dict_row = ttk.Frame(content, style="Dlg.TFrame")
        dict_row.grid(row=2, column=1, sticky="we", padx=(8, 0), pady=(8, 0))
        dict_row.columnconfigure(0, weight=0)
        dict_row.columnconfigure(1, weight=1)

        self.dict_mode = tk.BooleanVar(value=bool(use_custom_dict))
        rad_frame = ttk.Frame(dict_row, style="Dlg.TFrame")
        rad_frame.grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(rad_frame, text="Пользовательский (words.txt)",
                        variable=self.dict_mode, value=True, style="Dlg.TRadiobutton").pack(anchor="w")
        ttk.Radiobutton(rad_frame, text="Стандартный (полная модель)",
                        variable=self.dict_mode, value=False, style="Dlg.TRadiobutton").pack(anchor="w")

        btn_center = ttk.Frame(dict_row, style="Dlg.TFrame")
        btn_center.grid(row=0, column=1, sticky="we")
        btn_center.columnconfigure(0, weight=1)
        btn_center.columnconfigure(2, weight=1)
        ttk.Label(btn_center, text="", style="Dlg.TLabel").grid(row=0, column=0, sticky="we")
        ttk.Button(btn_center, text="📄 Открыть словарь…", style="Dlg.TButton",
                   command=self._open_words).grid(row=0, column=1, sticky="n")
        ttk.Label(btn_center, text="", style="Dlg.TLabel").grid(row=0, column=2, sticky="we")

        # Микрофон
        ttk.Label(content, text="Микрофон:", style="Dlg.TLabel").grid(row=3, column=0, sticky="w", pady=(8, 0))
        import sounddevice as sd
        devices = []
        try:
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", f"Device {idx}")
                    hostapi = sd.query_hostapis(dev.get("hostapi", 0)).get("name", "")
                    devices.append({"index": idx, "name": f"{idx}: {name} ({hostapi})"})
        except Exception:
            pass
        values = [d["name"] for d in devices] or ["(устройств не найдено)"]
        self.cb_device = ttk.Combobox(content, state="readonly", values=values, style="Dlg.TCombobox")
        self.cb_device.grid(row=3, column=1, sticky="we", padx=(8, 0), pady=(8, 0))

        def _select_current_device():
            if not devices:
                self.cb_device.current(0); return
            indices = [d["index"] for d in devices]
            if input_device in indices: self.cb_device.current(indices.index(input_device))
            else: self.cb_device.current(0)
        _select_current_device()

        # Громкость
        vol_row = ttk.Frame(content, style="Dlg.TFrame")
        vol_row.grid(row=4, column=0, columnspan=2, sticky="we", pady=(8, 0))
        vol_row.columnconfigure(1, weight=1)
        self.volume_var = tk.IntVar(value=int(current_volume_percent))
        self.lbl_vol = ttk.Label(vol_row, text=f"Громкость уведомлений: {int(self.volume_var.get())}%", style="Dlg.TLabel")
        self.lbl_vol.grid(row=0, column=0, sticky="w")

        def on_volume_change(_):
            self.lbl_vol.config(text=f"Громкость уведомлений: {int(self.volume_var.get())}%")

        scale = ttk.Scale(vol_row, from_=0, to=100, orient="horizontal",
                          variable=self.volume_var, command=on_volume_change)
        scale.grid(row=0, column=1, sticky="we", padx=(8, 0))

        # Логи
        self.show_recog_var = tk.BooleanVar(value=bool(cur_show_recog))
        self.show_events_var = tk.BooleanVar(value=bool(cur_show_events))
        ttk.Checkbutton(content, text="Показывать распознанную речь",
                        variable=self.show_recog_var, style=self._chk_style).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(content, text="Показывать служебные уведомления (статусы, таймеры, ошибки)",
                        variable=self.show_events_var, style=self._chk_style).grid(row=6, column=0, columnspan=2, sticky="w")

        content.columnconfigure(1, weight=1)

        # ---- Команды ----
        cmds = ttk.LabelFrame(content, text="Команды (фразы/слова)", style="Dlg.TLabelframe")
        cmds.grid(row=7, column=0, columnspan=2, sticky="we", pady=(8, 12))
        grid = ttk.Frame(cmds, style="Dlg.TFrame"); grid.pack(fill="x", padx=8, pady=8)
        for i in range(2): grid.columnconfigure(i, weight=1)

        ttk.Label(grid, text="Фраза глиф:", style="Dlg.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.e_glyph = ttk.Entry(grid, style="Dlg.TEntry"); self.e_glyph.grid(row=0, column=1, sticky="we", padx=(8, 0), pady=(0, 4))
        self.e_glyph.insert(0, glyph_phrase)

        ttk.Label(grid, text="Фраза байбек (без номера):", style="Dlg.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 4))
        self.e_buyback = ttk.Entry(grid, style="Dlg.TEntry"); self.e_buyback.grid(row=1, column=1, sticky="we", padx=(8, 0), pady=(0, 4))
        self.e_buyback.insert(0, buyback_phrase)

        ttk.Label(grid, text="Поставить на паузу:", style="Dlg.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.e_kw_pause = ttk.Entry(grid, style="Dlg.TEntry"); self.e_kw_pause.grid(row=2, column=1, sticky="we", padx=(8, 0), pady=(0, 4))
        self.e_kw_pause.insert(0, kw_pause)

        ttk.Label(grid, text="Продолжить таймер:", style="Dlg.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 4))
        self.e_kw_resume = ttk.Entry(grid, style="Dlg.TEntry"); self.e_kw_resume.grid(row=3, column=1, sticky="we", padx=(8, 0), pady=(0, 4))
        self.e_kw_resume.insert(0, kw_resume)

        ttk.Label(grid, text="Отменить таймер:", style="Dlg.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 4))
        self.e_kw_cancel = ttk.Entry(grid, style="Dlg.TEntry"); self.e_kw_cancel.grid(row=4, column=1, sticky="we", padx=(8, 0), pady=(0, 4))
        self.e_kw_cancel.insert(0, kw_cancel)

        ttk.Label(grid, text="Все таймеры:", style="Dlg.TLabel").grid(row=5, column=0, sticky="w")
        self.e_kw_all = ttk.Entry(grid, style="Dlg.TEntry"); self.e_kw_all.grid(row=5, column=1, sticky="we", padx=(8, 0))
        self.e_kw_all.insert(0, kw_all)

        # ---- Внешний вид ----
        ui = ttk.LabelFrame(content, text="Внешний вид", style="Dlg.TLabelframe")
        ui.grid(row=8, column=0, columnspan=2, sticky="we", pady=(0, 8))
        row = ttk.Frame(ui, style="Dlg.TFrame"); row.pack(fill="x", padx=8, pady=8)
        for i in range(8): row.columnconfigure(i, weight=1)

        ttk.Label(row, text="Тема:", style="Dlg.TLabel").grid(row=0, column=0, sticky="w")
        self.cb_theme = ttk.Combobox(row, state="readonly", values=["dark", "light"], width=10, style="Dlg.TCombobox")
        self.cb_theme.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.cb_theme.set((ui_theme or "dark"))

        ttk.Label(row, text="Акцент-цвет:", style="Dlg.TLabel").grid(row=0, column=2, sticky="e")
        accent_frame = ttk.Frame(row, style="Dlg.TFrame"); accent_frame.grid(row=0, column=3, sticky="we", padx=(8, 0))
        accent_frame.columnconfigure(1, weight=1)
        self.e_accent = ttk.Entry(accent_frame, style="Dlg.TEntry")
        self.e_accent.grid(row=0, column=0, sticky="we")
        self.e_accent.insert(0, ui_accent or "#00A2FF")
        ttk.Button(accent_frame, text="🎨 Палитра", command=self._pick_color, style="Dlg.TButton").grid(row=0, column=1, padx=(6, 0))

        ttk.Label(row, text="Пресет:", style="Dlg.TLabel").grid(row=0, column=4, sticky="e")
        self.cb_preset = ttk.Combobox(row, state="readonly", values=list(ACCENT_PRESETS.keys()), width=10, style="Dlg.TCombobox")
        self.cb_preset.grid(row=0, column=5, sticky="w", padx=(8, 0))
        self.cb_preset.bind("<<ComboboxSelected>>", self._apply_preset)

        # Строка масштаба
        row2 = ttk.Frame(ui, style="Dlg.TFrame"); row2.pack(fill="x", padx=8, pady=(0, 4))
        for i in range(5): row2.columnconfigure(i, weight=(1 if i in (1,) else 0))
        ttk.Label(row2, text="Масштаб UI (%):", style="Dlg.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_scale_val = ttk.Label(row2, text=f"{int(ui_scale)}%", style="DlgBold.TLabel")
        self.lbl_scale_val.grid(row=0, column=2, sticky="w", padx=(8,0))
        self.ui_scale_var = tk.IntVar(value=int(ui_scale or 100))
        self.scale_ui = ttk.Scale(
            row2, from_=80, to=150, orient="horizontal",
            variable=self.ui_scale_var,
            command=self._on_ui_scale_label_only  # меняем только подпись, без применения
        )
        self.scale_ui.grid(row=0, column=1, sticky="we", padx=(8, 0))
        # применяем масштаб при отпускании/клавишах
        self.scale_ui.bind("<ButtonRelease-1>", self._on_ui_scale_apply)
        self.scale_ui.bind("<KeyRelease>", self._on_ui_scale_apply)

        ttk.Button(row2, text="⟲ Сбросить масштаб", style="Dlg.TButton",
                   command=self._reset_scale).grid(row=0, column=4, sticky="e", padx=(8,0))

        # ---- Проверить звуки ----
        snd = ttk.LabelFrame(content, text="Проверить звуки", style="Dlg.TLabelframe")
        snd.grid(row=9, column=0, columnspan=2, sticky="we", pady=(0, 8))
        ttk.Button(snd, text="🔔 Глиф", width=14, command=lambda: self._test("glyph.wav"), style="Dlg.TButton").pack(padx=8, pady=6)
        row2b = ttk.Frame(snd, style="Dlg.TFrame"); row2b.pack(padx=8, pady=(0, 8))
        for i in range(1, 6):
            ttk.Button(row2b, text=f"🔊 Байбек {i}", width=12,
                       command=lambda n=i: self._test(f"buyback{n}.wav"), style="Dlg.TButton").pack(side="left", padx=(0 if i == 1 else 6, 0))

        # ---- Кнопки НИЗОМ ----
        btns_outer = ttk.Frame(root, style="Dlg.TFrame")
        btns_outer.pack(fill="x", padx=12, pady=(0, 12), side="bottom")
        btns = ttk.Frame(btns_outer, style="Dlg.TFrame"); btns.pack(fill="x")
        for i in (0, 2, 4): btns.columnconfigure(i, weight=1)
        btns.columnconfigure(1, weight=0); btns.columnconfigure(3, weight=0)
        ttk.Label(btns, text="", style="Dlg.TLabel").grid(row=0, column=0, sticky="we")
        ttk.Button(btns, text="💾 Сохранить", width=18, command=self._save, style="DlgAccent.TButton").grid(row=0, column=1, sticky="e")
        ttk.Label(btns, text="", style="Dlg.TLabel").grid(row=0, column=2, sticky="we")
        ttk.Button(btns, text="✖ Закрыть", width=16, command=self.destroy, style="Dlg.TButton").grid(row=0, column=3, sticky="w")
        ttk.Label(btns, text="", style="Dlg.TLabel").grid(row=0, column=4, sticky="we")

        self.lbl_saved = ttk.Label(root, text="", style="Dlg.TLabel")
        self.lbl_saved.pack(padx=12, pady=(0, 6), anchor="center")

        # Модальность + центрирование
        self.transient(parent); self.grab_set(); self.e_phrase.focus_set()
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        x = px + (pw - w) // 2; y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")
        try:
            self.attributes("-topmost", True); self.after(200, lambda: self.attributes("-topmost", False))
            self.attributes("-alpha", 0.0); self._fade_to(1.0, step=0.08, delay=12)
        except Exception:
            pass

        try: self.bind("<Control-s>", lambda e: (self._save(), "break"))
        except Exception: pass

        self._devices = devices

    # ---------- Helpers ----------
    def _fade_to(self, target: float, step: float = 0.06, delay: int = 14):
        try:
            cur = float(self.attributes("-alpha"))
            if abs(cur - target) < 1e-3:
                self.attributes("-alpha", target); return
            cur = min(target, cur + step) if target > cur else max(target, cur - step)
            self.attributes("-alpha", cur)
            self.after(delay, lambda: self._fade_to(target, step, delay))
        except Exception:
            pass

    def _apply_preset(self, _evt=None):
        name = self.cb_preset.get()
        if name in ACCENT_PRESETS:
            self.e_accent.delete(0, "end")
            self.e_accent.insert(0, ACCENT_PRESETS[name])

    def _pick_color(self):
        try:
            c = colorchooser.askcolor(color=self.e_accent.get() or "#00A2FF", title="Выбор акцент-цвета")
            if c and c[1]:
                self.e_accent.delete(0, "end"); self.e_accent.insert(0, c[1])
        except Exception:
            pass

    def _test(self, filename: str):
        try:
            self.on_test_sound_with_volume(filename, int(self.volume_var.get()))
        except Exception as e:
            try: messagebox.showwarning("Проверка звука", f"Не удалось воспроизвести звук:\n{e}")
            except Exception: pass

    def _selected_device_index(self) -> int | None:
        if not self._devices: return None
        sel = self.cb_device.current()
        if sel < 0: return None
        return self._devices[sel]["index"]

    def _open_words(self):
        phrase = (self.e_phrase.get() or "").strip().lower()
        ensure_words_file(phrase)
        p = get_paths()
        try:
            os.startfile(p.words_user)
        except Exception:
            try: subprocess.Popen(["notepad", p.words_user], shell=True)
            except Exception as e:
                messagebox.showerror("Словарь", f"Не удалось открыть файл словаря:\n{e}")

    # --- Масштаб UI: во время перетаскивания — только подпись ---
    def _on_ui_scale_label_only(self, value_str: str):
        try: val = int(float(value_str))
        except Exception: return
        self.lbl_scale_val.config(text=f"{val}%")

    # --- Применяем при отпускании/клавише ---
    def _on_ui_scale_apply(self, _evt=None):
        try: val = int(float(self.ui_scale_var.get()))
        except Exception: return
        val = max(80, min(150, val))
        self.lbl_scale_val.config(text=f"{val}%")
        try:
            if hasattr(self._parent_app, "_apply_scaling_live"):
                self._parent_app._apply_scaling_live(val)
        except Exception:
            pass

    def _reset_scale(self):
        self.ui_scale_var.set(100)
        self._on_ui_scale_apply()

    def _save(self):
        # Основные
        phrase = (self.e_phrase.get() or "").strip().lower()
        game = (self.e_game.get() or "").strip()
        dev = self._selected_device_index()
        use_custom = bool(self.dict_mode.get())
        vol = int(self.volume_var.get())
        show_recog = bool(self.show_recog_var.get())
        show_events = bool(self.show_events_var.get())
        # Команды
        glyph = (self.e_glyph.get() or "").strip().lower()
        buyback = (self.e_buyback.get() or "").strip().lower()
        kw_pause = (self.e_kw_pause.get() or "").strip().lower()
        kw_resume = (self.e_kw_resume.get() or "").strip().lower()
        kw_cancel = (self.e_kw_cancel.get() or "").strip().lower()
        kw_all = (self.e_kw_all.get() or "").strip().lower()
        # Внешний вид
        ui_theme = (self.cb_theme.get() or "dark").strip().lower()
        ui_accent = (self.e_accent.get() or "#00A2FF").strip()
        ui_scale = max(80, min(150, int(self.ui_scale_var.get() or 100)))

        if not all([phrase, game, glyph, buyback, kw_pause, kw_resume, kw_cancel, kw_all, ui_theme, ui_accent]):
            messagebox.showwarning("Настройки", "Заполните все поля."); return
        try:
            self.on_save(phrase, game, dev, use_custom, vol, show_recog, show_events,
                         glyph, buyback, kw_pause, kw_resume, kw_cancel, kw_all,
                         ui_theme, ui_accent, ui_scale)
            self.lbl_saved.config(text="✓ Сохранено")
            self.after(1600, lambda: self.lbl_saved.config(text=""))
        except Exception as e:
            try: messagebox.showerror("Настройки", f"Не удалось сохранить:\n{e}")
            except Exception: pass


# -------------------- Таймеры --------------------

class TimerManager:
    def __init__(self, app):
        self.app = app
        self.timers: dict[str, dict] = {}
        self._running = False

    def start_timer(self, name: str, duration: int):
        if name in self.timers:
            self.app._event(f"⏳ Таймер «{name}» уже запущен."); return
        self.timers[name] = {"remain": int(duration), "paused": False}
        self.app._event(f"🕒 Таймер «{name}» запущен на {duration} сек.")
        self.app._refresh_timers_view(); self._ensure_loop()

    def pause_timer(self, name: str):
        t = self.timers.get(name)
        if not t: self.app._event(f"ℹ️ Таймер «{name}» не найден."); return
        if t["paused"]: self.app._event(f"⏸ Таймер «{name}» уже на паузе."); return
        t["paused"] = True; self.app._event(f"⏸ Таймер «{name}» поставлен на паузу."); self.app._refresh_timers_view()

    def resume_timer(self, name: str):
        t = self.timers.get(name)
        if not t: self.app._event(f"ℹ️ Таймер «{name}» не найден."); return
        if not t["paused"]: self.app._event(f"▶️ Таймер «{name}» уже идёт."); return
        t["paused"] = False; self.app._event(f"▶️ Таймер «{name}» продолжен."); self.app._refresh_timers_view(); self._ensure_loop()

    def cancel_timer(self, name: str):
        if name not in self.timers: self.app._event(f"ℹ️ Таймер «{name}» не найден."); return
        del self.timers[name]; self.app._event(f"🛑 Таймер «{name}» отменён."); self.app._refresh_timers_view()

    def pause_all(self):
        if not self.timers: self.app._event("ℹ️ Нет активных таймеров.")
        cnt = 0
        for t in self.timers.values():
            if not t["paused"]: t["paused"] = True; cnt += 1
        if cnt: self.app._event(f"⏸ Пауза для {cnt} таймер(ов).")
        self.app._refresh_timers_view()

    def resume_all(self):
        if not self.timers: self.app._event("ℹ️ Нет активных таймеров.")
        cnt = 0
        for t in self.timers.values():
            if t["paused"]: t["paused"] = False; cnt += 1
        if cnt: self.app._event(f"▶️ Продолжено {cnt} таймер(ов).")
        self.app._refresh_timers_view(); self._ensure_loop()

    def cancel_all(self):
        if self.timers:
            self.timers.clear(); self.app._event("🛑 Все таймеры остановлены."); self.app._refresh_timers_view()

    def _ensure_loop(self):
        if not self._running:
            self._running = True; self.app.after(1000, self._tick)

    def _tick(self):
        if not self.timers:
            self._running = False; self.app._refresh_timers_view(); return
        finished = []
        for n, state in list(self.timers.items()):
            if state["paused"]: continue
            state["remain"] -= 1
            if state["remain"] <= 0: finished.append(n)
        for n in finished:
            del self.timers[n]; self.app._event(f"✅ Таймер «{n}» завершён!")
            try: self.app._on_timer_finished(n)
            except Exception: pass
        self.app._refresh_timers_view(); self.app.after(1000, self._tick)


# -------------------- Приложение --------------------

class App(tk.Tk):
    """Главное окно + темы/шрифты + распознавание + таймеры."""

    def __init__(self):
        super().__init__()
        self.title("Exort")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Иконка
        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        # --- Верхняя панель кнопок ---
        top = ttk.Frame(self); top.pack(padx=10, pady=8, fill="x")
        self.btn_start = ttk.Button(top, text="▶ Старт", width=12, command=self.start_listening, style="Toolbar.TButton")
        self.btn_stop = ttk.Button(top, text="■ Стоп", width=12, command=self.stop_listening, state="disabled", style="Toolbar.TButton")
        self.btn_settings = ttk.Button(top, text="⚙ Настройки", width=14, command=self.open_settings, style="Accent.TButton")
        self.btn_start.pack(side="left"); self.btn_stop.pack(side="left", padx=(8, 0)); self.btn_settings.pack(side="right")

        # Информационные лейблы
        self.lbl_dict = ttk.Label(self, text="", anchor="w"); self.lbl_dict.pack(padx=10, pady=(0, 2), fill="x")
        self.lbl_mic = ttk.Label(self, text="", anchor="w"); self.lbl_mic.pack(padx=10, pady=(0, 6), fill="x")

        # Таймеры
        self.timers = TimerManager(self)

        # --- Центральная область ---
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(padx=10, pady=(0, 10), fill="both", expand=True)

        left = ttk.Labelframe(paned, text="Сообщения", style="Section.TLabelframe", labelanchor="nw")
        left_inner = ttk.Frame(left); left_inner.pack(fill="both", expand=True, padx=8, pady=6)
        self.text = scrolledtext.ScrolledText(left_inner, width=80, height=18, wrap="word", state="disabled", undo=False)
        self.text.pack(fill="both", expand=True)
        paned.add(left, weight=2)

        right = ttk.Frame(paned); self._build_timers_panel(right); paned.add(right, weight=3)

        # Статус-строка
        self.status = ttk.Label(self, text="Готово", anchor="w"); self.status.pack(fill="x", padx=10, pady=(0, 8))

        # --- Настройки из файла ---
        s = load_settings()
        self.wake_phrase = s["wake_phrase"]
        self.game_path = s["game_path"]
        self.input_device = s.get("input_device")
        self.use_custom_dict = bool(s.get("use_custom_dict", True))
        self.volume_percent = int(s.get("volume_percent", 100))
        self.show_recognition_log = bool(s.get("show_recognition_log", True))
        self.show_event_log = bool(s.get("show_event_log", True))
        self.glyph_phrase   = s.get("glyph_phrase", "запиши укрепление")
        self.buyback_phrase = s.get("buyback_phrase", "запиши выкуп героя")
        self.kw_pause       = s.get("kw_pause", "пауза")
        self.kw_resume      = s.get("kw_resume", "продолжить")
        self.kw_cancel      = s.get("kw_cancel", "отмена")
        self.kw_all         = s.get("kw_all", "все")
        self.ui_theme  = s.get("ui_theme", "dark")
        self.ui_accent = s.get("ui_accent", "#00A2FF")
        self.ui_scale  = int(s.get("ui_scale", 100))

        # Модель Vosk
        p = get_paths()
        try:
            if not os.path.isdir(p.model_dir):
                raise FileNotFoundError(f"Не найдена модель: {p.model_dir}")
            self.model = vosk.Model(p.model_dir)
        except Exception as e:
            messagebox.showerror("Ошибка модели", str(e)); self.after(100, self.destroy); return

        self._update_dict_status(); self._update_mic_status()

        # Тема/шрифты
        self._apply_theme()

        self._event(f"✅ Готово. Ключевая фраза: «{self.wake_phrase}». Игра: {self.game_path}")

        # Движок распознавания
        self.engine = RecognizerEngine(
            model=self.model,
            grammar_provider=lambda: None,
            on_text=self._on_text,
            on_error=self._on_audio_error,
            device=self.input_device,
            emit_partials=False,
        )

        try:
            self.attributes("-alpha", 0.0); self.after(50, lambda: self._fade_to(1.0, step=0.06, delay=14))
        except Exception: pass

        self.after(200, self.start_listening)

    # ---- Fade helpers ----
    def _fade_to(self, target: float, step: float = 0.06, delay: int = 14):
        try:
            cur = float(self.attributes("-alpha"))
            if abs(cur - target) < 1e-3: self.attributes("-alpha", target); return
            cur = min(target, cur + step) if target > cur else max(target, cur - step)
            self.attributes("-alpha", cur); self.after(delay, lambda: self._fade_to(target, step, delay))
        except Exception: pass

    # ---- Тема/шрифты/стили ----
    def _apply_theme(self):
        # 1) tk scaling
        try:
            self.tk.call("tk", "scaling", max(0.8, min(1.6, self.ui_scale / 100.0)))
        except Exception:
            pass

        # 2) глобальные именованные шрифты — масштабируются на лету
        scale = max(0.8, min(1.6, self.ui_scale / 100.0))
        try:
            base = tkfont.nametofont("TkDefaultFont"); base.configure(size=max(8, int(9 * scale)))
            textf = tkfont.nametofont("TkTextFont");   textf.configure(size=max(8, int(10 * scale)))
            head  = tkfont.nametofont("TkHeadingFont");head.configure(size=max(9, int(10 * scale)))
        except Exception:
            pass

        # 3) шрифты диалога (если открыт) — обновим размеры
        try:
            if DLG_FONT_LABEL_NAME in tkfont.names():
                tkfont.nametofont(DLG_FONT_LABEL_NAME).configure(size=int(11 * scale))
            if DLG_FONT_EDIT_NAME in tkfont.names():
                tkfont.nametofont(DLG_FONT_EDIT_NAME).configure(size=int(12 * scale))
            if DLG_FONT_BOLD_NAME in tkfont.names():
                tkfont.nametofont(DLG_FONT_BOLD_NAME).configure(size=int(11 * scale))
        except Exception:
            pass

        style = ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass

        if (self.ui_theme or "dark").lower() == "dark":
            bg = "#1e2126"; panel = "#252a31"; panel2 = "#2e343d"
            fg = "#E6E6E6"; sub = "#ABB2BF"
            tree_bg = panel; tree_sel = self.ui_accent
            text_bg = panel; text_fg = fg
            btn_hover = _blend(panel2, "#FFFFFF", 0.10)
            btn_hover_strong = _blend(panel2, "#FFFFFF", 0.16)
            accent_hover = _blend(self.ui_accent, "#FFFFFF", 0.12)
            border_col = _blend(self.ui_accent, bg, 0.65)
        else:
            bg = "#FFFFFF"; panel = "#F5F6F8"; panel2 = "#ECEFF3"
            fg = "#1C2128"; sub = "#5C6672"
            tree_bg = "#FFFFFF"; tree_sel = self.ui_accent
            text_bg = "#FFFFFF"; text_fg = "#1C2128"
            btn_hover = _blend(panel2, "#000000", 0.06)
            btn_hover_strong = _blend(panel2, "#000000", 0.10)
            accent_hover = _blend(self.ui_accent, "#000000", 0.10)
            border_col = _blend(self.ui_accent, bg, 0.55)

        try: self.configure(bg=bg)
        except Exception: pass

        style.configure(".", background=bg, foreground=fg)
        for cls in ("TFrame", "TLabelframe", "TLabelframe.Label", "TLabel"):
            style.configure(cls, background=bg if cls in ("TFrame", "TLabel") else panel, foreground=fg)

        style.configure("Section.TLabelframe",
                        background=panel, foreground=fg, borderwidth=2, relief="solid")
        style.configure("Section.TLabelframe", bordercolor=border_col)
        style.configure("Section.TLabelframe.Label",
                        background=panel, foreground=fg, font=("Segoe UI", max(9, int(10*scale)), "bold"))

        style.configure("TButton", background=panel2, foreground=fg, padding=6, relief="flat", borderwidth=0)
        style.map("TButton",
                  background=[("active", btn_hover), ("pressed", btn_hover), ("disabled", panel2)],
                  relief=[("pressed", "flat"), ("!pressed", "flat")],
                  foreground=[("disabled", _blend(fg, bg, 0.5))])

        style.configure("Toolbar.TButton", background=panel2, foreground=fg, padding=8, relief="flat", borderwidth=1)
        style.map("Toolbar.TButton",
                  background=[("active", btn_hover_strong), ("pressed", btn_hover_strong), ("disabled", panel2)],
                  foreground=[("disabled", _blend(fg, bg, 0.5))])

        style.configure("Accent.TButton", background=self.ui_accent, foreground="#FFFFFF", padding=8, relief="flat")
        style.map("Accent.TButton",
                  background=[("active", accent_hover), ("pressed", accent_hover), ("disabled", _blend(self.ui_accent, bg, 0.4))],
                  foreground=[("disabled", _blend("#FFFFFF", bg, 0.4))])

        style.configure("TScale", background=bg)
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("TRadiobutton", background=bg, foreground=fg)
        style.configure("TPanedwindow", background=bg)

        row_h = int(22 * max(0.9, min(1.6, self.ui_scale / 100.0)))
        style.configure("Treeview",
                        background=tree_bg, fieldbackground=tree_bg, foreground=fg,
                        rowheight=row_h, borderwidth=0)
        style.map("Treeview",
                  background=[("selected", tree_sel)],
                  foreground=[("selected", "#FFFFFF")])
        style.configure("Treeview.Heading",
                        background=panel2, foreground=fg, relief="flat", padding=6)
        style.map("Treeview.Heading",
                  relief=[("active", "flat"), ("pressed", "flat")])

        try: self.text.configure(bg=text_bg, fg=text_fg, insertbackground=text_fg, bd=0, highlightthickness=0)
        except Exception: pass

        try: self.status.configure(background=panel, foreground=sub)
        except Exception: pass

        try:
            self.btn_settings.configure(style="Accent.TButton")
            self.btn_start.configure(style="Toolbar.TButton")
            self.btn_stop.configure(style="Toolbar.TButton")
        except Exception: pass

    # ---- LIVE масштаб извне ----
    def _apply_scaling_live(self, scale_percent: int):
        self.ui_scale = max(80, min(150, int(scale_percent)))
        # Сохраняем сразу, чтобы повторное открытие настроек показывало текущее значение
        save_settings(
            self.wake_phrase, self.game_path, self.input_device,
            self.use_custom_dict, self.volume_percent,
            self.show_recognition_log, self.show_event_log,
            self.glyph_phrase, self.buyback_phrase,
            self.kw_pause, self.kw_resume, self.kw_cancel, self.kw_all,
            self.ui_theme, self.ui_accent, self.ui_scale,
        )
        self._apply_theme()

    # ---- Панель таймеров ----
    def _build_timers_panel(self, parent):
        ttk.Label(parent, text="Таймеры", font=("Segoe UI", 10, "bold")).pack(fill="x")
        self.tree = ttk.Treeview(parent, columns=("name", "remain"), show="headings", height=12)
        self.tree.heading("name", text="Название")
        self.tree.heading("remain", text="Осталось")
        self.tree.column("name", width=180, anchor="w")
        self.tree.column("remain", width=110, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=4)

        btns1 = ttk.Frame(parent); btns1.pack(fill="x", pady=(2, 0))
        ttk.Button(btns1, text="⏸ Пауза выбранного", command=self._pause_selected, style="TButton").pack(side="left")
        ttk.Button(btns1, text="▶ Продолжить выбранного", command=self._resume_selected, style="TButton").pack(side="left", padx=6)
        ttk.Button(btns1, text="🛑 Отмена выбранного", command=self._cancel_selected, style="TButton").pack(side="left")

        btns2 = ttk.Frame(parent); btns2.pack(fill="x", pady=(4, 6))
        ttk.Button(btns2, text="⏸ Пауза все", command=self.timers.pause_all, style="TButton").pack(side="left")
        ttk.Button(btns2, text="▶ Продолжить все", command=self.timers.resume_all, style="TButton").pack(side="left", padx=6)
        ttk.Button(btns2, text="🛑 Отмена все", command=self.timers.cancel_all, style="TButton").pack(side="left")

        self.tree.bind("<Double-1>", self._toggle_selected)
        self._refresh_timers_view()

    def _selected_timer_name(self) -> str | None:
        sel = self.tree.selection()
        if not sel: return None
        return sel[0]

    def _toggle_selected(self, _evt=None):
        name = self._selected_timer_name()
        if not name: self._event("ℹ️ Выберите таймер в списке."); return
        state = self.timers.timers.get(name)
        if not state: self._event("ℹ️ Таймер не найден."); return
        if state.get("paused"): self.timers.resume_timer(name)
        else: self.timers.pause_timer(name)

    def _pause_selected(self):
        name = self._selected_timer_name()
        if not name: self._event("ℹ️ Выберите таймер для паузы."); return
        self.timers.pause_timer(name)

    def _resume_selected(self):
        name = self._selected_timer_name()
        if not name: self._event("ℹ️ Выберите таймер для продолжения."); return
        self.timers.resume_timer(name)

    def _cancel_selected(self):
        name = self._selected_timer_name()
        if not name: self._event("ℹ️ Выберите таймер для отмены."); return
        self.timers.cancel_timer(name)

    def _refresh_timers_view(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        for n in sorted(self.timers.timers.keys()):
            state = self.timers.timers[n]
            secs = int(state["remain"]); m, s = divmod(max(0, secs), 60)
            suffix = " ⏸ Пауза" if state.get("paused") else ""
            self.tree.insert("", "end", iid=n, values=(n + suffix, f"{m:02d}:{s:02d}"))

    # ---- Логирование ----
    def _append_text(self, s: str):
        self.text.config(state="normal"); self.text.insert("end", s + "\n"); self.text.see("end"); self.text.config(state="disabled")

    def _recog(self, s: str):
        if self.show_recognition_log: self.after(0, self._append_text, s)

    def _event(self, s: str):
        if self.show_event_log: self.after(0, self._append_text, s)
        try: self.status.config(text=s)
        except Exception: pass

    # ---- Статусы ----
    def _update_mic_status(self):
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            name = "(не выбран)"
            if self.input_device is not None and 0 <= self.input_device < len(devs):
                name = f"{self.input_device}: {devs[self.input_device]['name']}"
            self.lbl_mic.config(text=f"Микрофон: {name}")
        except Exception:
            self.lbl_mic.config(text="Микрофон: (ошибка определения)")

    def _update_dict_status(self):
        self.lbl_dict.config(text="Словарь: стандартный (полная модель) — ограничений нет")

    # ---- Фаззи ----
    @staticmethod
    def _fuzzy_contains(text, phrase, thr=SIM_THRESHOLD):
        text, phrase = (text or "").lower().strip(), (phrase or "").lower().strip()
        if not text or not phrase: return False
        if phrase in text: return True
        n = len(phrase); lo, hi = max(1, n - 2), n + 2
        best = 0.0
        for L in range(lo, hi + 1):
            if L > len(text): continue
            for i in range(0, len(text) - L + 1):
                r = difflib.SequenceMatcher(None, text[i:i + L], phrase).ratio()
                if r > best:
                    best = r
                    if best >= thr: return True
        return False

    def _best_timer_match(self, spoken: str) -> str | None:
        if not self.timers.timers: return None
        spoken = (spoken or "").lower()
        numbers = {"один": "1", "два": "2", "три": "3", "четыре": "4", "пять": "5"}
        for w, d in numbers.items(): spoken = spoken.replace(f" {w} ", f" {d} ")
        candidates = list(self.timers.timers.keys())
        for name in candidates:
            if name.lower() in spoken: return name
        best_name, best_score = None, 0.0
        for name in candidates:
            score = difflib.SequenceMatcher(None, spoken, name.lower()).ratio()
            if score > best_score: best_name, best_score = name, score
        return best_name if best_score >= 0.65 else None

    # ---- Распознавание ----
    def _on_text(self, text):
        self._recog(f"🗣 {text}")

        if self._fuzzy_contains(text, self.wake_phrase):
            self._event("🎮 Запускаю игру…"); self._launch_game(); return

        if self._fuzzy_contains(text, self.glyph_phrase):
            self.timers.start_timer("Глиф", 300); return

        mapping = {"один": 1, "1": 1, "два": 2, "2": 2, "три": 3, "3": 3, "четыре": 4, "4": 4, "пять": 5, "5": 5}
        if self._fuzzy_contains(text, self.buyback_phrase):
            for token, num in mapping.items():
                if self._fuzzy_contains(text, token, 0.9 if token.isdigit() else 0.85):
                    self.timers.start_timer(f"Байбек {num}", 480); return

        if self._fuzzy_contains(text, self.kw_all) or self._fuzzy_contains(text, "всё"):
            if self._fuzzy_contains(text, self.kw_pause):  self.timers.pause_all();  return
            if self._fuzzy_contains(text, self.kw_resume): self.timers.resume_all(); return
            if self._fuzzy_contains(text, self.kw_cancel): self.timers.cancel_all(); return

        if self._fuzzy_contains(text, self.kw_pause):
            name = self._best_timer_match(text)
            if name: self.timers.pause_timer(name)
            else:    self._event("ℹ️ Не удалось определить, какой таймер поставить на паузу.")
            return

        if self._fuzzy_contains(text, self.kw_resume):
            name = self._best_timer_match(text)
            if name: self.timers.resume_timer(name)
            else:    self._event("ℹ️ Не удалось определить, какой таймер продолжить.")
            return

        if self._fuzzy_contains(text, self.kw_cancel):
            name = self._best_timer_match(text)
            if name: self.timers.cancel_timer(name)
            else:    self._event("ℹ️ Не удалось определить, какой таймер отменить.")
            return

    def _on_audio_error(self, e):
        messagebox.showerror("Аудио", f"Не удалось открыть микрофон:\n{e}")
        self.btn_start.config(state="normal"); self.btn_stop.config(state="disabled"); self.status.config(text="Аудио: ошибка")

    # ---- Звуки ----
    def _on_timer_finished(self, name: str):
        name_l = (name or "").lower()
        if "глиф" in name_l:
            filename = "glyph.wav"
        elif name_l.startswith("байбек"):
            try:
                num = int(name_l.split()[1]); filename = f"buyback{num}.wav"
            except Exception:
                filename = "buyback.wav"
        else:
            return
        self._play_sound_file(filename)

    def _play_sound_file(self, filename: str, volume_override: int | None = None):
        path = resource_path(filename)
        if not os.path.isfile(path):
            if self.show_event_log: self._event(f"🔇 Нет файла: {filename}")
            return
        try:
            import platform
            if platform.system().lower().startswith("win"):
                import wave, array, winsound
                vol = int(volume_override) if volume_override is not None else int(getattr(self, "volume_percent", 100))
                vol = max(0, min(100, vol)); factor = vol / 100.0
                with wave.open(path, "rb") as wf:
                    params = wf.getparams(); sampwidth = params.sampwidth
                    frames = wf.readframes(params.nframes)
                if sampwidth == 2:
                    samples = array.array("h"); samples.frombytes(frames)
                    for i in range(len(samples)):
                        v = int(samples[i] * factor); v = -32768 if v < -32768 else (32767 if v > 32767 else v)
                        samples[i] = v
                    out_bytes = samples.tobytes()
                elif sampwidth == 1:
                    samples = array.array("B"); samples.frombytes(frames)
                    for i in range(len(samples)):
                        s = int((samples[i] - 128) * factor); s = max(-128, min(127, s))
                        samples[i] = s + 128
                    out_bytes = samples.tobytes()
                else:
                    out_bytes = frames
                tmp_dir = os.path.join(os.getenv("TEMP", "."), "ExortCache")
                os.makedirs(tmp_dir, exist_ok=True)
                tmp_path = os.path.join(tmp_dir, f"__snd_{filename}")
                with wave.open(tmp_path, "wb") as wf:
                    wf.setparams(params); wf.writeframes(out_bytes)
                winsound.PlaySound(tmp_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                try: self.bell()
                except Exception: pass
        except Exception as e:
            if self.show_event_log: self._event(f"⚠️ Ошибка воспроизведения: {e}")

    # ---- Управление ----
    def start_listening(self):
        self.engine.start()
        self.btn_start.config(state="disabled"); self.btn_stop.config(state="normal")
        self._event("🎧 Прослушивание запущено")

    def stop_listening(self):
        self.engine.stop()
        self.btn_start.config(state="normal"); self.btn_stop.config(state="disabled")
        self._event("⏸ Прослушивание остановлено")

    def open_settings(self):
        SettingsDialog(
            self,
            resource_path("icon.ico"),
            self.wake_phrase,
            self.game_path,
            self.input_device,
            self.use_custom_dict,
            int(getattr(self, "volume_percent", 100)),
            bool(getattr(self, "show_recognition_log", True)),
            bool(getattr(self, "show_event_log", True)),
            # команды
            self.glyph_phrase,
            self.buyback_phrase,
            self.kw_pause,
            self.kw_resume,
            self.kw_cancel,
            self.kw_all,
            # внешний вид
            self.ui_theme,
            self.ui_accent,
            self.ui_scale,
            # callbacks
            self._apply_settings,
            self._test_sound_with_volume,
        )

    def _test_sound_with_volume(self, filename: str, volume_percent: int):
        self._play_sound_file(filename, volume_override=int(volume_percent))

    def _apply_settings(self, phrase, game, dev, use_dict, vol, show_recog, show_events,
                        glyph, buyback, kw_pause, kw_resume, kw_cancel, kw_all,
                        ui_theme, ui_accent, ui_scale):
        self.wake_phrase = (phrase or "").strip().lower()
        self.game_path = (game or "").strip()
        self.input_device = dev
        self.use_custom_dict = bool(use_dict)
        self.volume_percent = int(vol)
        self.show_recognition_log = bool(show_recog)
        self.show_event_log = bool(show_events)

        self.glyph_phrase   = (glyph or "").strip().lower()
        self.buyback_phrase = (buyback or "").strip().lower()
        self.kw_pause       = (kw_pause or "").strip().lower()
        self.kw_resume      = (kw_resume or "").strip().lower()
        self.kw_cancel      = (kw_cancel or "").strip().lower()
        self.kw_all         = (kw_all or "").strip().lower()

        self.ui_theme  = (ui_theme or "dark").strip().lower()
        self.ui_accent = (ui_accent or "#00A2FF").strip()
        self.ui_scale  = max(80, min(150, int(ui_scale)))

        save_settings(
            self.wake_phrase, self.game_path, self.input_device,
            self.use_custom_dict, self.volume_percent,
            self.show_recognition_log, self.show_event_log,
            self.glyph_phrase, self.buyback_phrase,
            self.kw_pause, self.kw_resume, self.kw_cancel, self.kw_all,
            self.ui_theme, self.ui_accent, self.ui_scale,
        )

        self._update_mic_status(); self._update_dict_status()
        if self.show_event_log:
            self._event(f"⚙️ Настройки сохранены • громкость {self.volume_percent}% • тема {self.ui_theme} • масштаб {self.ui_scale}%")

        self._apply_theme()
        try:
            self.engine.stop()
            self.engine = RecognizerEngine(
                model=self.model,
                grammar_provider=lambda: None,
                on_text=self._on_text,
                on_error=self._on_audio_error,
                device=self.input_device,
                emit_partials=False,
            )
            self.engine.start()
            self.btn_start.config(state="disabled"); self.btn_stop.config(state="normal")
        except Exception:
            pass

    # ---- Запуск игры ----
    def _launch_game(self):
        try:
            os.startfile(self.game_path)
        except Exception:
            try: subprocess.Popen([self.game_path], shell=True)
            except Exception as e:
                messagebox.showerror("Ошибка запуска игры", str(e))

    # ---- Закрытие ----
    def on_close(self):
        try: self.engine.stop()
        except Exception: pass
        self.destroy()
