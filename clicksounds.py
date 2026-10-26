"""Звуки нажатия на кнопки: стекло, бабл, капля, щелчок… Синтезируются кодом при первом
использовании (никаких файлов скачивать не нужно)."""
import threading
import time

import numpy as np

RATE = 44100
SOUNDS = [
    ("none", "Без звука"),
    ("glass", "Стекло"),
    ("bubble", "Бабл"),
    ("drop", "Капля"),
    ("pop", "Поп"),
    ("click", "Щелчок"),
    ("tap", "Дерево"),
    ("soft", "Мягкий"),
    ("key", "Клавиатура"),
    ("crystal", "Кристалл"),
]
_CACHE = {}
_LAST = [0.0]


def _env(n, attack=0.002, decay=0.05):
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / decay), t


def _synth(name):
    if name == "glass":
        n = int(RATE * 0.35)
        e, t = _env(n, 0.001, 0.09)
        y = (np.sin(2 * np.pi * 2637 * t) + 0.5 * np.sin(2 * np.pi * 3951 * t) * np.exp(-t / 0.04)
             + 0.25 * np.sin(2 * np.pi * 5274 * t) * np.exp(-t / 0.02)) * e
    elif name == "crystal":
        n = int(RATE * 0.5)
        e, t = _env(n, 0.001, 0.16)
        y = (np.sin(2 * np.pi * 1760 * t) + 0.6 * np.sin(2 * np.pi * 2217 * t + 0.4)
             + 0.35 * np.sin(2 * np.pi * 2637 * t)) * e * (1 + 0.15 * np.sin(2 * np.pi * 7 * t))
    elif name == "bubble":
        n = int(RATE * 0.11)
        e, t = _env(n, 0.003, 0.035)
        f = 380 + 1500 * (t / t[-1]) ** 1.6
        y = np.sin(2 * np.pi * np.cumsum(f) / RATE) * e
    elif name == "drop":
        n = int(RATE * 0.16)
        e, t = _env(n, 0.002, 0.05)
        f = 1500 * np.exp(-t / 0.035) + 420
        y = np.sin(2 * np.pi * np.cumsum(f) / RATE) * e
    elif name == "pop":
        n = int(RATE * 0.08)
        e, t = _env(n, 0.001, 0.022)
        f = 260 * np.exp(-t / 0.03) + 120
        y = np.sin(2 * np.pi * np.cumsum(f) / RATE) * e * 1.3
    elif name == "click":
        n = int(RATE * 0.025)
        e, t = _env(n, 0.0003, 0.004)
        rng = np.random.default_rng(1)
        y = (rng.standard_normal(n) * 0.5 + np.sin(2 * np.pi * 3200 * t)) * e
    elif name == "tap":
        n = int(RATE * 0.09)
        e, t = _env(n, 0.0005, 0.018)
        y = (np.sin(2 * np.pi * 820 * t) + 0.5 * np.sin(2 * np.pi * 1930 * t) * np.exp(-t / 0.008)) * e
    elif name == "soft":
        n = int(RATE * 0.18)
        e, t = _env(n, 0.012, 0.06)
        y = (np.sin(2 * np.pi * 660 * t) + 0.3 * np.sin(2 * np.pi * 990 * t)) * e
    elif name == "key":
        n = int(RATE * 0.06)
        rng = np.random.default_rng(2)
        e1, t = _env(n, 0.0002, 0.003)
        e2 = np.zeros(n)
        k = int(RATE * 0.022)
        e2[k:] = _env(n - k, 0.0002, 0.004)[0]
        y = rng.standard_normal(n) * (e1 + 0.6 * e2) * 0.6 + np.sin(2 * np.pi * 1800 * t) * e1 * 0.5
    else:
        return None
    y = y / max(1e-6, float(np.max(np.abs(y))))
    return y


def _pcm(name, volume):
    key = (name, round(volume, 2))
    if key not in _CACHE:
        y = _synth(name)
        if y is None:
            return None
        _CACHE[key] = (np.clip(y * volume, -1, 1)).astype(np.float32)
    return _CACHE[key]


def play(name=None, volume=None):
    """Играет звук нажатия (по настройке оформления, если не указан). Играет отдельным
    потоком звука — голос помощника и сигнал обращения не прерываются."""
    import theme as T
    name = name or T.APPEARANCE.get("click_sound") or "none"
    if name == "none":
        return
    now = time.monotonic()
    if now - _LAST[0] < 0.04:              # двойной щелчок — один звук
        return
    _LAST[0] = now
    vol = float(volume if volume is not None else T.APPEARANCE.get("click_volume", 0.35))

    def go():
        try:
            import sounddevice as sd
            y = _pcm(name, vol)
            if y is not None:
                sd.play(y, RATE, blocking=False)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=go, daemon=True).start()
