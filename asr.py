"""Точное распознавание речи: Whisper (faster-whisper, модель small, работает на компьютере).
Быстрый Vosk слушает постоянно и ловит «Сеньор», а саму команду после обращения
распознаёт Whisper — он гораздо лучше понимает тихую речь, шёпот, названия игр и программ."""
import os
import sys
import threading
import types
from pathlib import Path

import config

FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
HF = "https://huggingface.co/Systran/faster-whisper-small/resolve/main/"
MIRROR_PREFIX = "whisper-small-"
PROMPT = ("Сеньор, открой телеграм. Громкость десять. Запусти Steam, Discord, Dota 2, "
          "Counter-Strike 2, osu!, Minecraft. Найди погоду. Который час?")
VOCAB = ""            # названия программ и игр этого компьютера — Whisper пишет их правильно


def set_vocab(names):
    global VOCAB
    picked, total = [], 0
    for n in names:
        n = n.strip()
        if not (3 <= len(n) <= 24) or n in picked:
            continue
        if total + len(n) > 260:
            break
        picked.append(n)
        total += len(n) + 2
    VOCAB = ", ".join(picked)


def prompt():
    return PROMPT + (" Программы: " + VOCAB + "." if VOCAB else "")


HALLUCINATIONS = ("субтитр", "продолжение следует", "редактор субтитров", "спасибо за просмотр",
                  "подписывайтесь", "dimatorzok")


def model_dir() -> Path:
    d = config.local_dir() / "whisper-small"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ready() -> bool:
    d = model_dir()
    mb = d / "model.bin"
    return all((d / f).is_file() for f in FILES) and mb.stat().st_size > 100_000_000


def download(progress=None):
    import tts
    repo = config.load_config().get("update_repo") or ""
    d = model_dir()
    for f in FILES:
        if (d / f).is_file() and (f != "model.bin" or (d / f).stat().st_size > 100_000_000):
            continue
        urls = ([f"https://github.com/{repo}/releases/download/models/{MIRROR_PREFIX}{f}"]
                if repo else []) + [HF + f]
        cb = None
        if f == "model.bin" and progress:
            def cb(done, total):
                progress(min(1.0, done / max(total, 1)),
                         f"Скачиваю точное распознавание · {done / 1e6:.0f} из {total / 1e6:.0f} МБ")
        tts.download(urls, d / f, cb, expect=484_000_000 if f == "model.bin" else 0)


def _stub_av():
    """faster-whisper импортирует PyAV для чтения файлов; нам он не нужен (звук уже в памяти)."""
    try:
        import av  # noqa: F401
    except Exception:  # noqa: BLE001
        sys.modules["av"] = types.ModuleType("av")


class Recognizer:
    def __init__(self):
        self.model = None
        self.lock = threading.Lock()
        self.error = ""

    def load(self):
        if self.model is not None:
            return self.model
        _stub_av()
        from faster_whisper import WhisperModel
        threads = max(2, (os.cpu_count() or 4) // 3)    # не нагружаем весь процессор
        self.model = WhisperModel(str(model_dir()), device="cpu", compute_type="int8",
                                  cpu_threads=threads)
        return self.model

    @property
    def available(self):
        return self.model is not None

    def transcribe(self, pcm16: bytes, rate: int = 16000) -> str:
        """pcm16 — моно 16 бит. Возвращает текст или "" (если ничего не разобрал)."""
        import numpy as np
        if self.model is None or not pcm16:
            return ""
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if rate != 16000:
            idx = np.linspace(0, len(audio) - 1, int(len(audio) * 16000 / rate))
            audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak < 0.003:
            return ""
        audio = audio * min(8.0, 0.6 / peak)          # нормализуем громкость (шёпот)
        with self.lock:
            segments, _info = self.model.transcribe(
                audio, language="ru", beam_size=2 if len(audio) < 16000 * 7 else 1,
                initial_prompt=prompt(),
                condition_on_previous_text=False, vad_filter=False,
                no_speech_threshold=0.6, temperature=0.0)
            text = " ".join(s.text.strip() for s in segments).strip()
        low = text.lower()
        if any(h in low for h in HALLUCINATIONS) or "программы:" in low:
            return ""
        return text


class Downloader:
    def __init__(self):
        self.active = False
        self.frac = 0.0
        self.text = ""
        self.error = ""

    def start(self, on_done=None):
        if self.active:
            return
        self.active, self.frac, self.error = True, 0.0, ""
        self.text = "Готовлю точное распознавание"

        def work():
            import config
            config.low_priority_thread()
            try:
                download(self._progress)
                RECOGNIZER.load()
            except Exception as e:  # noqa: BLE001
                self.error = f"Точное распознавание недоступно: {e}"
            finally:
                self.active = False
                if on_done:
                    on_done()

        threading.Thread(target=work, daemon=True).start()

    def _progress(self, frac, text):
        self.frac, self.text = frac, text


RECOGNIZER = Recognizer()
DOWNLOADS = Downloader()
