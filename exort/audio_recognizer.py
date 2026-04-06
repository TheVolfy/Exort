import json
import queue
import threading
from typing import Callable, Optional

import sounddevice as sd
import vosk

SAMPLE_RATE = 16000


class RecognizerEngine:
    """
    Инкапсулирует поток аудио и KaldiRecognizer.
    Поддерживает два режима:
      1) С ограничивающей грамматикой (список фраз/слов).
      2) Без грамматики (полная языковая модель Vosk).

    Новое:
      - emit_partials: если False — НЕ шлём partial-результаты (только финальные),
        что снижает дубли и ложные срабатывания.
    """

    def __init__(
        self,
        model: vosk.Model,
        grammar_provider: Callable[[], Optional[list[str]]],  # может вернуть None для режима «без грамматики»
        on_text: Callable[[str], None],
        on_error: Callable[[Exception], None],
        device: int | None,
        emit_partials: bool = False,
    ):
        self.model = model
        self.grammar_provider = grammar_provider
        self.on_text = on_text
        self.on_error = on_error
        self.device = device
        self.emit_partials = bool(emit_partials)

        self._q: "queue.Queue[bytes]" = queue.Queue()
        self._stop_evt = threading.Event()
        self._rebuild_evt = threading.Event()
        self._rec_lock = threading.Lock()

        self._rec = None
        self._stream = None
        self._thread = None

    # ---------- внутренние методы ----------

    def _audio_cb(self, indata, frames, time_info, status):  # noqa: ANN001
        """Callback от sounddevice — помещает фреймы в очередь."""
        if not self._stop_evt.is_set():
            self._q.put(bytes(indata))

    def _rebuild(self):
        """
        Пересоздаёт KaldiRecognizer:
          - если grammar_provider() вернул список — используем ограниченную грамматику;
          - если None — инициализируем без грамматики (полный словарь модели).
        """
        words = self.grammar_provider()
        with self._rec_lock:
            if words is None:
                self._rec = vosk.KaldiRecognizer(self.model, SAMPLE_RATE)
            else:
                self._rec = vosk.KaldiRecognizer(self.model, SAMPLE_RATE, json.dumps(words, ensure_ascii=False))

    # ---------- управление жизненным циклом ----------

    def start(self):
        """Запускает поток аудио и распознавания."""
        try:
            self._rebuild()
            self._stop_evt.clear()
            self._stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                dtype="int16",
                channels=1,
                callback=self._audio_cb,
                device=self.device,
            )
            self._stream.start()
        except Exception as e:  # noqa: BLE001
            self.on_error(e)
            return

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def rebuild_on_demand(self):
        """Выставляет флаг для перестройки распознавателя в фоне (например, при смене словаря)."""
        self._rebuild_evt.set()

    def _loop(self):
        """Главный цикл распознавания."""
        while not self._stop_evt.is_set():
            if self._rebuild_evt.is_set():
                self._rebuild_evt.clear()
                self._rebuild()
            try:
                data = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            with self._rec_lock:
                accept = self._rec.AcceptWaveform(data)
                if accept:
                    try:
                        res = json.loads(self._rec.Result())
                        text = (res.get("text") or "").strip().lower()
                    except Exception:
                        text = ""
                    if text:
                        self.on_text(text)
                else:
                    if not self.emit_partials:
                        continue
                    try:
                        res = json.loads(self._rec.PartialResult())
                        text = (res.get("partial") or "").strip().lower()
                    except Exception:
                        text = ""
                    if text:
                        self.on_text(text)

    def stop(self):
        """Останавливает поток распознавания и освобождает ресурсы."""
        self._stop_evt.set()
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=1.5)
