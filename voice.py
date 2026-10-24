"""Распознавание речи (Vosk, офлайн) и озвучка (нейроголос / голос Windows)."""
import array
import json
import math
import os
import queue
import struct
import sys
import tempfile
import threading
import time
import wave

from PySide6.QtCore import QThread, Signal

IS_WIN = sys.platform == "win32"


def _co_init():
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass


GAINS = {"normal": 3.0, "high": 6.0, "whisper": 14.0}   # максимальное усиление микрофона
WAKE_GRAMMAR = ["сеньор", "сеньер", "синьор", "сеньора", "[unk]"]


class Listener(QThread):
    level = Signal(float)
    partial = Signal(str)
    final = Signal(str)
    wake = Signal()          # отдельный чуткий детектор слова «Сеньор»
    failed = Signal(str)
    ready = Signal()

    def __init__(self, model, parent=None):
        """model — уже загруженная vosk.Model (готовится в окне загрузки)."""
        super().__init__(parent)
        self.model = model
        self._running = True
        self._paused = False
        self._reset = False
        self.sensitivity = "high"

    def set_paused(self, flag: bool):
        self._paused = flag
        if not flag:
            self._reset = True

    def stop(self):
        self._running = False
        self.wait(3000)

    def run(self):
        if self.model is None:
            self.failed.emit("Речевая модель не загружена — голосовые команды недоступны, "
                             "но команды можно писать.")
            return
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer
            rec = KaldiRecognizer(self.model, 16000)
            try:
                wake_rec = KaldiRecognizer(self.model, 16000, json.dumps(WAKE_GRAMMAR,
                                                                         ensure_ascii=False))
            except Exception:  # noqa: BLE001 — модель без поддержки грамматик
                wake_rec = None
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Не удалось запустить распознавание: {e}")
            return
        if not self._running:
            return

        q = queue.Queue(maxsize=100)

        def callback(indata, frames, t, status):
            try:
                q.put_nowait(bytes(indata))
            except queue.Full:
                pass

        try:
            stream = sd.RawInputStream(samplerate=16000, blocksize=1600, dtype="int16",
                                       channels=1, callback=callback)
        except Exception:  # noqa: BLE001
            self.failed.emit("Микрофон не найден. Подключите микрофон и перезапустите программу.")
            return

        last_partial = ""
        gain = 1.0
        floor = 0.004            # оценка уровня тишины/шума
        with stream:
            self.ready.emit()
            while self._running:
                try:
                    data = q.get(timeout=0.3)
                except queue.Empty:
                    continue
                if self._paused:
                    continue
                if self._reset:
                    rec.Reset()
                    if wake_rec is not None:
                        wake_rec.Reset()
                    self._reset = False
                    last_partial = ""
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            break
                    continue

                # ---- автоусиление: тихая речь и шёпот подтягиваются до нормальной громкости
                samples = array.array("h", data)
                if not samples:
                    continue
                rms = math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768.0
                floor = floor * 0.9 + rms * 0.1 if rms < floor else floor * 1.002
                floor = max(0.0005, min(floor, 0.05))
                max_gain = GAINS.get(self.sensitivity, 6.0)
                if rms > floor * 1.6:                      # похоже на голос, а не тишину
                    want = max(1.0, min(max_gain, 0.08 / max(rms, 1e-5)))
                else:
                    want = max(1.0, gain * 0.98)           # в тишине шум не раздуваем
                gain += (want - gain) * (0.5 if want < gain else 0.12)
                if gain > 1.05:
                    g = gain
                    samples = array.array("h", (max(-32768, min(32767, int(x * g))) for x in samples))
                    data = samples.tobytes()
                    rms *= g
                self.level.emit(min(1.0, rms * 7))

                if wake_rec is not None and wake_rec.AcceptWaveform(data):
                    words = json.loads(wake_rec.Result()).get("text", "").split()
                    if words and all(w != "[unk]" for w in words):
                        self.wake.emit()

                if rec.AcceptWaveform(data):
                    text = json.loads(rec.Result()).get("text", "").strip()
                    last_partial = ""
                    if text:
                        self.final.emit(text)
                else:
                    p = json.loads(rec.PartialResult()).get("partial", "").strip()
                    if p != last_partial:
                        last_partial = p
                        self.partial.emit(p)


def _log(text):
    try:
        import config
        with open(config.data_dir() / "error.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except Exception:  # noqa: BLE001
        pass


class Speaker(QThread):
    """Озвучка фраз голосом Piper «Руслан» (офлайн). Запасной вариант — голос Windows."""
    speaking = Signal(bool)
    problem = Signal(str)

    def __init__(self, voice=None, parent=None):
        super().__init__(parent)
        self.q = queue.Queue()
        self._stop_now = threading.Event()
        self._engine = None
        self._piper = voice
        self._lock = threading.Lock()
        self.enabled = True
        self.speed = "normal"
        self._warned = False

    def set_voice(self, voice):
        self._piper = voice

    def configure(self, speed="normal", enabled=True):
        self.speed = speed if speed in ("slow", "normal", "fast") else "normal"
        self.enabled = enabled

    def say(self, text: str, force=False, speed=None):
        if text and (self.enabled or force):
            self.q.put((text, speed or self.speed))

    def prefetch(self, texts):
        """Заранее готовит частые фразы, чтобы они звучали мгновенно."""
        def work():
            for t in texts:
                try:
                    self._wav(t, self.speed)
                except Exception:  # noqa: BLE001
                    return
        threading.Thread(target=work, daemon=True).start()

    def interrupt(self):
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self._stop_now.set()
        self._stop_playback()

    def shutdown(self):
        self.interrupt()
        self.q.put(None)
        self.wait(3000)

    def run(self):
        _co_init()
        while True:
            item = self.q.get()
            if item is None:
                break
            text, speed = item
            self._stop_now.clear()
            self.speaking.emit(True)
            try:
                self._speak(text, speed)
            except Exception:  # noqa: BLE001
                import traceback
                _log("Ошибка озвучки:\n" + traceback.format_exc())
            time.sleep(0.15)  # чтобы микрофон не поймал «хвост» речи
            if self.q.empty():
                self.speaking.emit(False)

    # ---------- озвучка ----------
    def _wav(self, text, speed):
        import tts
        path = tts.cache_path(text, speed)
        if not os.path.exists(path):
            with self._lock:   # синтез одной модели — по очереди
                if not os.path.exists(path):
                    tts.synth_wav(self._piper, text, path, speed)
        return path

    def _speak(self, text, speed):
        if self._piper is not None:
            try:
                self._play_wav(self._wav(text, speed))
                return
            except Exception:  # noqa: BLE001
                import traceback
                _log("Голос Piper не сработал:\n" + traceback.format_exc())
                self.problem.emit("Основной голос не сработал — говорит голос Windows.")
        elif not self._warned:
            self._warned = True
            self.problem.emit("Голос ещё не скачан — пока говорит голос Windows. "
                              "Перезапустите программу при подключённом интернете.")
        if not self._stop_now.is_set():
            self._speak_sapi(text)

    def _play_wav(self, path):
        import tts
        import winsound
        dur = tts.wav_seconds(path)
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        end = time.monotonic() + dur + 0.05
        while time.monotonic() < end:
            if self._stop_now.is_set():
                winsound.PlaySound(None, 0)
                return
            time.sleep(0.03)

    def _stop_playback(self):
        if IS_WIN:
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except Exception:  # noqa: BLE001
                pass

    def _speak_sapi(self, text):
        """Встроенный голос Windows (через SAPI напрямую, без генерации модулей)."""
        try:
            if self._engine is None:
                import comtypes.client
                eng = comtypes.client.CreateObject("SAPI.SpVoice", dynamic=True)
                voices = eng.GetVoices()
                for i in range(voices.Count):
                    tok = voices.Item(i)
                    desc = str(tok.GetDescription()).lower()
                    if any(k in desc for k in ("russian", "русск", "irina", "pavel", "ru-ru")):
                        eng.Voice = tok
                        break
                eng.Rate = 0
                self._engine = eng
            self._engine.Speak(text, 0)
            return
        except Exception:  # noqa: BLE001
            import traceback
            _log("Голос Windows (SAPI) не сработал:\n" + traceback.format_exc())
            self._engine = None
        import subprocess
        safe = text.replace("'", "''")
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Add-Type -AssemblyName System.Speech; "
                        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                        f"$s.Speak('{safe}')"],
                       capture_output=True, timeout=30, creationflags=0x08000000)


class PlaybackError(Exception):
    pass


class Chime:
    """Мягкий «стеклянный» звук, когда помощник услышал обращение."""

    def __init__(self):
        self.path = os.path.join(tempfile.gettempdir(), "seniorem_chime_v2.wav")
        if not os.path.exists(self.path):
            self._make()

    def _make(self):
        rate = 44100
        total = int(rate * 1.1)
        buf = [0.0] * total
        # две ноты (ля и ми) с обертонами и мягким затуханием
        for start, freq in ((0.0, 880.0), (0.085, 1318.5)):
            s0 = int(start * rate)
            for i in range(total - s0):
                t = i / rate
                env = min(1.0, t / 0.006) * math.exp(-t / 0.32)
                v = (math.sin(2 * math.pi * freq * t)
                     + 0.22 * math.sin(2 * math.pi * freq * 2.0 * t) * math.exp(-t / 0.12)
                     + 0.08 * math.sin(2 * math.pi * freq * 3.01 * t) * math.exp(-t / 0.08))
                buf[s0 + i] += 0.16 * env * v
        # лёгкое эхо для «воздуха»
        d = int(0.095 * rate)
        for i in range(d, total):
            buf[i] += 0.22 * buf[i - d]
        frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, x)) * 32767)) for x in buf)
        with wave.open(self.path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(frames)

    def play(self):
        if not IS_WIN:
            return
        try:
            import winsound
            winsound.PlaySound(self.path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:  # noqa: BLE001
            pass
