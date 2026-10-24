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


class Speaker(QThread):
    speaking = Signal(bool)

    def __init__(self, voice_cfg: dict, parent=None):
        super().__init__(parent)
        self.voice = voice_cfg.get("edge_voice") or "ru-RU-DmitryNeural"
        self.rate = voice_cfg.get("rate") or "+0%"
        self.q = queue.Queue()
        self._stop_now = threading.Event()
        self._edge_off_until = 0.0
        self._engine = None

    def say(self, text: str):
        if text:
            self.q.put(text)

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
            text = self.q.get()
            if text is None:
                break
            self._stop_now.clear()
            self.speaking.emit(True)
            try:
                self._speak(text)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.15)  # чтобы микрофон не поймал «хвост» речи
            if self.q.empty():
                self.speaking.emit(False)

    # ---------- озвучка ----------
    def _speak(self, text):
        if time.time() > self._edge_off_until:
            try:
                self._speak_edge(text)
                return
            except Exception:  # noqa: BLE001
                self._edge_off_until = time.time() + 120  # нет интернета — 2 минуты офлайн-голос
        self._speak_sapi(text)

    def _speak_edge(self, text):
        import edge_tts
        path = os.path.join(tempfile.gettempdir(), f"seniorem_{uuid.uuid4().hex}.mp3")

        async def gen():
            await edge_tts.Communicate(text, self.voice, rate=self.rate).save(path)

        asyncio.run(asyncio.wait_for(gen(), timeout=8))
        try:
            self._play_mp3(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

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
    """Короткий мягкий сигнал «слушаю»."""

    def __init__(self):
        self.path = os.path.join(tempfile.gettempdir(), "seniorem_chime.wav")
        if not os.path.exists(self.path):
            self._make()

    def _make(self):
        rate = 44100
        frames = bytearray()
        for freq, dur in ((784, 0.09), (1175, 0.14)):
            n = int(rate * dur)
            for i in range(n):
                env = min(1.0, i / (rate * 0.008)) * (1 - i / n) ** 2
                v = 0.22 * env * math.sin(2 * math.pi * freq * i / rate)
                frames += struct.pack("<h", int(v * 32767))
        with wave.open(self.path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(frames))

    def play(self):
        if not IS_WIN:
            return
        try:
            import winsound
            winsound.PlaySound(self.path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:  # noqa: BLE001
            pass
