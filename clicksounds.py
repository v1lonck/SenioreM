"""Звуки нажатия на кнопки: стекло, бабл, капля, щелчок… Синтезируются кодом при первом
использовании (никаких файлов скачивать не нужно)."""
import threading
import time

import numpy as np

RATE = 44100
SOUNDS = [
    ("none", "Без звука"),
    ("tick", "Тик (как iPhone)"),
    ("glass", "Стекло"),
    ("bubble", "Бабл"),
    ("drop", "Капля"),
    ("pop", "Поп"),
    ("soft", "Маримба"),
    ("key", "Клавиатура"),
    ("tap", "Дерево"),
    ("crystal", "Кристалл"),
]
_CACHE = {}
_LAST = [0.0]


def _t(sec):
    return np.arange(int(RATE * sec)) / RATE


def _adsr(t, attack, decay):
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _lowpass(y, cutoff):
    a = np.exp(-2 * np.pi * cutoff / RATE)
    out = np.empty_like(y)
    acc = 0.0
    for i, v in enumerate(y):
        acc = (1 - a) * v + a * acc
        out[i] = acc
    return out


def _reverb(y, amount=0.12, length=0.28):
    """Небольшая «комната» — звук не сухой, а объёмный."""
    rng = np.random.default_rng(7)
    ir_t = _t(length)
    ir = rng.standard_normal(len(ir_t)) * np.exp(-ir_t / (length / 4))
    ir = _lowpass(ir, 5000)
    ir /= np.max(np.abs(ir)) + 1e-9
    wet = np.convolve(y, ir)[: len(y) + len(ir_t)] * amount / np.sqrt(len(ir_t)) * 18
    out = np.zeros(len(wet))
    out[: len(y)] += y
    return out + wet


def _sweep(t, f0, f1, curve=1.0):
    f = f0 + (f1 - f0) * (t / t[-1]) ** curve
    return np.sin(2 * np.pi * np.cumsum(f) / RATE)


def _synth(name):
    rng = np.random.default_rng(3)
    if name == "tick":                                   # короткий «тик» клавиатуры iPhone
        t = _t(0.035)
        noise = _lowpass(rng.standard_normal(len(t)), 6000) * _adsr(t, 0.0002, 0.0025)
        body = np.sin(2 * np.pi * 1700 * t) * _adsr(t, 0.0003, 0.004)
        y = noise * 0.7 + body * 0.6
        y = _reverb(y, 0.05, 0.12)
    elif name == "glass":
        t = _t(0.45)
        y = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / d)
                for f, a, d in ((1568, 1.0, 0.16), (2349, 0.5, 0.10), (3920, 0.25, 0.05), (5270, 0.12, 0.03)))
        y = y * np.minimum(1.0, t / 0.001)
        y = _reverb(y, 0.14, 0.35)
    elif name == "crystal":
        t = _t(0.6)
        y = sum(a * np.sin(2 * np.pi * f * t + ph) * np.exp(-t / d)
                for f, a, d, ph in ((2093, 1.0, 0.22, 0), (2637, 0.6, 0.18, 0.5), (3136, 0.35, 0.14, 1.0)))
        y = y * np.minimum(1.0, t / 0.002) * (1 + 0.08 * np.sin(2 * np.pi * 6 * t))
        y = _reverb(y, 0.18, 0.45)
    elif name == "bubble":
        t = _t(0.12)
        y = _sweep(t, 420, 1400, 1.8) * _adsr(t, 0.004, 0.035)
        y = _reverb(_lowpass(y, 4000), 0.1, 0.2)
    elif name == "drop":
        t = _t(0.18)
        y = _sweep(t, 700, 1900, 0.5) * _adsr(t, 0.002, 0.03)
        y = _reverb(_lowpass(y, 5000), 0.14, 0.3)
    elif name == "pop":
        t = _t(0.09)
        f = 300 * np.exp(-t / 0.02) + 140
        y = np.sin(2 * np.pi * np.cumsum(f) / RATE) * _adsr(t, 0.0008, 0.02)
        y = y + _lowpass(rng.standard_normal(len(t)), 3000) * _adsr(t, 0.0002, 0.002) * 0.3
        y = _reverb(y, 0.06, 0.15)
    elif name == "soft":                                 # маримба: тёплая деревянная нота
        t = _t(0.35)
        y = (np.sin(2 * np.pi * 784 * t) * np.exp(-t / 0.12)
             + 0.35 * np.sin(2 * np.pi * 784 * 4 * t) * np.exp(-t / 0.02)
             + 0.15 * np.sin(2 * np.pi * 784 * 10 * t) * np.exp(-t / 0.006)) * np.minimum(1.0, t / 0.002)
        y = _reverb(y, 0.1, 0.3)
    elif name == "key":                                  # механическая клавиатура: «тук»
        t = _t(0.07)
        thump = np.sin(2 * np.pi * 150 * t) * _adsr(t, 0.0005, 0.012)
        click = _lowpass(rng.standard_normal(len(t)), 7000) * _adsr(t, 0.0002, 0.003)
        y = thump * 0.9 + click * 0.6
        y = _reverb(y, 0.05, 0.1)
    elif name == "tap":
        t = _t(0.12)
        y = (np.sin(2 * np.pi * 620 * t) + 0.45 * np.sin(2 * np.pi * 1510 * t) * np.exp(-t / 0.01)) \
            * _adsr(t, 0.0005, 0.025)
        y = _reverb(y, 0.08, 0.2)
    else:
        return None
    fade = min(len(y) // 4, int(RATE * 0.02))           # мягкий хвост — без щелчка в конце
    y[-fade:] *= np.linspace(1, 0, fade)
    return y / max(1e-6, float(np.max(np.abs(y)))) * 0.85


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
