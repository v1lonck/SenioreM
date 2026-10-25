"""Голос помощника: бесплатный офлайн-синтез Piper (голос «Руслан», ru_RU-ruslan-medium).
Голосовые модели Piper: https://huggingface.co/rhasspy/piper-voices (лицензия открытая)."""
import hashlib
import os
import urllib.request
import wave
from pathlib import Path

import config

VOICE_NAME = "ru_RU-ruslan-medium"
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium/"
SPEEDS = {"slow": 1.15, "normal": 1.0, "fast": 0.88}   # length_scale: больше — медленнее


def voice_dir() -> Path:
    d = config.local_dir() / "voice"
    d.mkdir(parents=True, exist_ok=True)
    return d


def voice_files():
    d = voice_dir()
    return d / f"{VOICE_NAME}.onnx", d / f"{VOICE_NAME}.onnx.json"


def voice_ready() -> bool:
    onnx, js = voice_files()
    return onnx.is_file() and onnx.stat().st_size > 1_000_000 and js.is_file()


def mirror_urls(filename: str):
    """Сначала зеркало в релизах GitHub (доступно везде), затем Hugging Face."""
    urls = []
    repo = config.load_config().get("update_repo") or ""
    if repo:
        urls.append(f"https://github.com/{repo}/releases/download/models/{filename}")
    urls.append(HF_BASE + filename)
    return urls


def download(urls, dest: Path, progress=None, expect=0):
    """Скачивает первый доступный адрес в dest. progress(done, total)."""
    last = None
    for url in urls:
        tmp = dest.with_name(dest.name + ".part")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SenioreM"})
            with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0) or expect
                done = 0
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
            os.replace(tmp, dest)
            return
        except Exception as e:  # noqa: BLE001 — пробуем следующий адрес
            last = e
            try:
                tmp.unlink()
            except OSError:
                pass
    raise OSError(f"не удалось скачать {dest.name}: {last}")


def download_voice(progress=None):
    onnx, js = voice_files()
    download(mirror_urls(js.name), js)
    download(mirror_urls(onnx.name), onnx, progress, expect=63_000_000)


def load_voice():
    from piper import PiperVoice
    onnx, js = voice_files()
    return PiperVoice.load(str(onnx), config_path=str(js))


def _syn_config(scale):
    """Живая, но ровная интонация: noise — выразительность голоса, noise_w — разброс длины звуков."""
    from piper import SynthesisConfig
    try:
        return SynthesisConfig(length_scale=scale, noise_scale=0.6, noise_w_scale=0.7)
    except TypeError:
        return SynthesisConfig(length_scale=scale)


# паузы: после точки — короткая, как в живой речи; в начале и в конце — почти без тишины
MAX_GAP = 0.24        # самая длинная пауза внутри фразы, сек
LEAD, TAIL = 0.06, 0.05


def _tighten(path, lead=LEAD, tail=TAIL, max_gap=MAX_GAP):
    """Убирает лишнюю тишину: обрезает края и сокращает долгие паузы между предложениями.
    Колонки и Bluetooth-наушники не «съедают» первый слог — короткая тишина в начале остаётся."""
    import numpy as np
    with wave.open(path, "rb") as r:
        params = r.getparams()
        raw = r.readframes(r.getnframes())
    if params.sampwidth != 2 or params.nchannels != 1:
        return
    a = np.frombuffer(raw, dtype=np.int16)
    sr = params.framerate
    win = max(1, int(sr * 0.01))                       # окна по 10 мс
    n = len(a) // win
    if n < 3:
        return
    rms = np.sqrt((a[:n * win].astype(np.float32).reshape(n, win) ** 2).mean(axis=1))
    loud = rms > max(120.0, float(np.percentile(rms, 95)) * 0.04)
    idx = np.nonzero(loud)[0]
    if len(idx) == 0:
        return
    first, last = int(idx[0]), int(idx[-1])
    keep = []
    i = first
    gap_max = int(max_gap / 0.01)
    while i <= last:
        if loud[i]:
            keep.append(a[i * win:(i + 1) * win])
            i += 1
            continue
        j = i
        while j <= last and not loud[j]:
            j += 1
        span = j - i
        if span > gap_max:
            # сохраняем начало и конец паузы (затухание и вдох), середину выкидываем
            h = gap_max // 2
            keep.append(a[i * win:(i + h) * win])
            keep.append(a[(j - (gap_max - h)) * win:j * win])
        else:
            keep.append(a[i * win:j * win])
        i = j
    keep.append(a[(last + 1) * win:min(len(a), (last + 4) * win)])    # мягкий хвост 30 мс
    out = np.concatenate([np.zeros(int(sr * lead), np.int16)] + keep +
                         [np.zeros(int(sr * tail), np.int16)])
    with wave.open(path, "wb") as w:
        w.setparams(params)
        w.writeframes(out.tobytes())


_PV = set("aɐʌɑeɛiɪɨoɵuʊəæyɯ")
_STRESSED = {"а": "ɑ", "о": "o", "у": "u", "ы": "y", "и": "i", "е": "e", "э": "ɛ", "я": "a",
             "ю": "u", "ё": "ɵ"}
_REDUCED = {"о": "ʌ", "а": "ʌ", "е": "i", "я": "i"}
_RU_V = "аеёиоуыэюя"
_PH_FIX = {}


def _move_stress(ph, word, mark):
    """Переносит ударение в фонемах слова: «pˈoisk» + «по+иск» -> «pʌˈisk»."""
    letters = [c for c in word if c in _RU_V]
    k = sum(1 for c in mark[:mark.index("+")] if c in _RU_V)
    clean = ph.replace("ˈ", "").replace("ˌ", "")
    vpos = [i for i, c in enumerate(clean) if c in _PV]
    if len(vpos) != len(letters) or k >= len(letters):
        return None
    j = None
    n = 0
    for c in ph:
        if c == "ˈ":
            j = n
            break
        if c in _PV:
            n += 1
    out = list(clean)
    if j is not None and j != k:
        out[vpos[j]] = _REDUCED.get(letters[j], out[vpos[j]])
    out[vpos[k]] = _STRESSED.get(letters[k], out[vpos[k]])
    out.insert(vpos[k], "ˈ")
    return "".join(out)


def _stress_fixes(voice, text):
    """[(как голос читает, как надо)] для слов из словаря ударений, встречающихся в тексте."""
    import re
    import speechtext
    fixes = []
    for w in set(re.findall(r"[а-яё]+", text.lower())):
        mark = speechtext.STRESS.get(w)
        if not mark:
            continue
        if w not in _PH_FIX:
            bad = "".join(sum(voice.phonemize(w), [])).strip(" .,!?")
            good = _move_stress(bad, w, mark)
            _PH_FIX[w] = (bad, good) if good and good != bad else None
        if _PH_FIX[w]:
            fixes.append(_PH_FIX[w])
    return sorted(fixes, key=lambda x: -len(x[0]))


def _synth_fixed(voice, text, wf, cfg):
    """Синтез с исправленными ударениями (через фонемы). -> False, если исправлять нечего."""
    import unicodedata
    import numpy as np
    fixes = _stress_fixes(voice, text)
    if not fixes:
        return False
    parts = []
    for sent in voice.phonemize(text):
        joined = unicodedata.normalize("NFD", "".join(sent))
        for bad, good in fixes:
            joined = joined.replace(unicodedata.normalize("NFD", bad), unicodedata.normalize("NFD", good))
        ids = voice.phonemes_to_ids(list(joined))
        audio = voice.phoneme_ids_to_audio(ids, cfg)
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        parts.append(np.clip(audio * 32767.0, -32768, 32767).astype(np.int16))
    wf.setframerate(voice.config.sample_rate)
    wf.setsampwidth(2)
    wf.setnchannels(1)
    wf.writeframes(np.concatenate(parts).tobytes() if parts else b"")
    return True


def synth_wav(voice, text: str, path: str, speed: str = "normal"):
    """Синтезирует фразу в WAV. Поддерживает API piper-tts 1.3 и старее."""
    import speechtext
    text = speechtext.prepare(text)
    scale = SPEEDS.get(speed, 1.0)
    tmp = path + ".part"
    try:
        cfg = _syn_config(scale)
        done = False
        try:
            with wave.open(tmp, "wb") as wf:
                done = _synth_fixed(voice, text, wf, cfg)
        except Exception:  # noqa: BLE001 — старая версия piper и т.п.: синтезируем как обычно
            done = False
        if not done:
            with wave.open(tmp, "wb") as wf:
                voice.synthesize_wav(text, wf, syn_config=cfg)
    except ImportError:
        with wave.open(tmp, "wb") as wf:
            if hasattr(voice, "synthesize_wav"):
                voice.synthesize_wav(text, wf)
            else:
                wf.setframerate(voice.config.sample_rate)
                wf.setsampwidth(2)
                wf.setnchannels(1)
                voice.synthesize(text, wf, length_scale=scale)
    try:
        _tighten(tmp)
    except Exception:  # noqa: BLE001
        pass
    os.replace(tmp, path)


def wav_seconds(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate() or 22050)


def cache_path(text: str, speed: str) -> str:
    d = config.local_dir() / "voice_cache"
    d.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{VOICE_NAME}|v3|{speed}|{text}".encode()).hexdigest()
    return str(d / f"{key}.wav")


# ---------------- Голоса Яндекса (SpeechKit), по ключу API ----------------
YANDEX_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
YANDEX_VOICES = [
    ("filipp", "Филипп", "мужской, спокойный"),
    ("ermil", "Ермил", "мужской, мягкий"),
    ("zahar", "Захар", "мужской, деловой"),
    ("alexander", "Александр", "мужской"),
    ("kirill", "Кирилл", "мужской"),
    ("anton", "Антон", "мужской"),
    ("alena", "Алёна", "женский, как у Алисы"),
    ("jane", "Джейн", "женский"),
    ("marina", "Марина", "женский"),
    ("dasha", "Даша", "женский"),
]
YANDEX_SPEED = {"slow": "0.9", "normal": "1.0", "fast": "1.15"}


def yandex_synth(text: str, path: str, key: str, voice: str = "filipp", speed: str = "normal"):
    """Синтез голосом Яндекса в WAV (48 кГц). Ключ — API-ключ сервисного аккаунта Yandex Cloud."""
    import urllib.error
    import urllib.parse

    import speechtext
    data = urllib.parse.urlencode({
        "text": speechtext.prepare(text), "lang": "ru-RU", "voice": voice, "format": "lpcm",
        "sampleRateHertz": "48000", "speed": YANDEX_SPEED.get(speed, "1.0"),
    }).encode("utf-8")
    req = urllib.request.Request(YANDEX_URL, data=data, method="POST",
                                 headers={"Authorization": f"Api-Key {key.strip()}",
                                          "User-Agent": "SenioreM"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            pcm = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("Яндекс не принял ключ API — проверьте его в профиле.")
        raise RuntimeError(f"Яндекс ответил ошибкой {e.code}.")
    tmp = path + ".part"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(pcm)
    try:
        _tighten(tmp)
    except Exception:  # noqa: BLE001
        pass
    os.replace(tmp, path)
