"""Распознавание речи (Vosk, офлайн) и озвучка (нейроголос / голос Windows)."""
import array
import asyncio
import ctypes
import json
import math
import os
import queue
import struct
import sys
import tempfile
import threading
import time
import uuid
import wave

from PySide6.QtCore import QThread, Signal

IS_WIN = sys.platform == "win32"


def _co_init():
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass


class Listener(QThread):
    level = Signal(float)
    partial = Signal(str)
    final = Signal(str)
    failed = Signal(str)
    ready = Signal()

    def __init__(self, model, parent=None):
        """model — уже загруженная vosk.Model (готовится в окне загрузки)."""
        super().__init__(parent)
        self.model = model
        self._running = True
        self._paused = False
        self._reset = False

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
                    self._reset = False
                    last_partial = ""
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            break
                    continue

                samples = array.array("h", data)
                if samples:
                    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0
                    self.level.emit(min(1.0, rms * 7))

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


VOICES = {
    "dmitry": ("Дмитрий — мужской, спокойный", "ru-RU-DmitryNeural", "-6%", "-3Hz"),
    "dmitry_fast": ("Дмитрий — мужской, бодрый", "ru-RU-DmitryNeural", "+6%", "+0Hz"),
    "svetlana": ("Светлана — женский", "ru-RU-SvetlanaNeural", "-2%", "+0Hz"),
    "dariya": ("Дария — женский, мягкий", "ru-RU-DariyaNeural", "-2%", "+0Hz"),
}


def _log(text):
    try:
        import config
        with open(config.data_dir() / "error.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except Exception:  # noqa: BLE001
        pass


class Speaker(QThread):
    speaking = Signal(bool)

    def __init__(self, voice_cfg: dict, parent=None):
        super().__init__(parent)
        self.q = queue.Queue()
        self._stop_now = threading.Event()
        self._edge_off_until = 0.0
        self._engine = None
        self._logged = False
        self.enabled = True
        self.configure(voice_cfg.get("voice_id", "dmitry"))
        try:
            import config
            self.cache = config.local_dir() / "voice_cache"
            self.cache.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            self.cache = None

    def configure(self, voice_id="dmitry", enabled=True):
        self.voice_id = voice_id if voice_id in VOICES else "dmitry"
        self.enabled = enabled

    def say(self, text: str, force=False, voice_id=None):
        """voice_id — разово другим голосом (например, «Послушать» в настройках)."""
        if text and (self.enabled or force):
            self.q.put((text, voice_id or self.voice_id))

    def prefetch(self, texts):
        """Заранее готовит частые фразы, чтобы они звучали мгновенно."""
        def work():
            for t in texts:
                try:
                    self._edge_file(t, self.voice_id)
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
            text, voice_id = item
            self._stop_now.clear()
            self.speaking.emit(True)
            try:
                self._speak(text, voice_id)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.15)  # чтобы микрофон не поймал «хвост» речи
            if self.q.empty():
                self.speaking.emit(False)

    # ---------- озвучка ----------
    def _speak(self, text, voice_id="dmitry"):
        if time.time() > self._edge_off_until:
            try:
                self._play_mp3(self._edge_file(text, voice_id))
                return
            except Exception:  # noqa: BLE001
                if not self._logged:
                    import traceback
                    _log("Нейроголос недоступен, использую голос Windows:\n" + traceback.format_exc())
                    self._logged = True
                self._edge_off_until = time.time() + 120  # нет интернета — 2 минуты офлайн-голос
        self._speak_sapi(text)

    def _edge_file(self, text, voice_id="dmitry"):
        """mp3 с фразой: из кэша или свежесинтезированный нейроголосом."""
        import hashlib
        _, voice, rate, pitch = VOICES.get(voice_id, VOICES["dmitry"])
        key = hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()
        folder = self.cache or tempfile.gettempdir()
        path = os.path.join(str(folder), f"{key}.mp3")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        import edge_tts
        tmp = path + f".{uuid.uuid4().hex[:6]}.part"

        async def gen():
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(tmp)

        asyncio.run(asyncio.wait_for(gen(), timeout=8))
        os.replace(tmp, path)
        return path

    def _play_mp3(self, path):
        winmm = ctypes.windll.winmm
        alias = "s" + uuid.uuid4().hex[:8]
        buf = ctypes.create_unicode_buffer(128)

        def mci(cmd):
            return winmm.mciSendStringW(cmd, buf, 127, 0)

        if mci(f'open "{path}" type mpegvideo alias {alias}') != 0:
            raise RuntimeError("mci open failed")
        try:
            mci(f"play {alias}")
            while not self._stop_now.is_set():
                mci(f"status {alias} mode")
                if buf.value != "playing":
                    break
                time.sleep(0.05)
        finally:
            mci(f"stop {alias}")
            mci(f"close {alias}")

    def _speak_sapi(self, text):
        if self._engine is None:
            import pyttsx3
            self._engine = pyttsx3.init("sapi5")
            for v in self._engine.getProperty("voices"):
                meta = f"{v.name} {v.id} {getattr(v, 'languages', '')}".lower()
                if any(k in meta for k in ("russian", "ru-ru", "irina", "pavel", "русск")):
                    self._engine.setProperty("voice", v.id)
                    break
            self._engine.setProperty("rate", 185)
        self._engine.say(text)
        self._engine.runAndWait()


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
