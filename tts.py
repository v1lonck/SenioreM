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
                    chunk = r.read(256 * 1024)
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
    """Ровная, спокойная речь: меньше «дрожания» интонации и пауз (noise / noise_w)."""
    from piper import SynthesisConfig
    try:
        return SynthesisConfig(length_scale=scale, noise_scale=0.5, noise_w_scale=0.55)
    except TypeError:
        return SynthesisConfig(length_scale=scale)


def _pad(path, lead=0.12, tail=0.15):
    """Тишина в начале и в конце: колонки и Bluetooth-наушники не «съедают» первый слог."""
    with wave.open(path, "rb") as r:
        params = r.getparams()
        frames = r.readframes(r.getnframes())
    bpf = params.sampwidth * params.nchannels
    pre = b"\x00" * (int(params.framerate * lead) * bpf)
    post = b"\x00" * (int(params.framerate * tail) * bpf)
    with wave.open(path, "wb") as w:
        w.setparams(params)
        w.writeframes(pre + frames + post)


def synth_wav(voice, text: str, path: str, speed: str = "normal"):
    """Синтезирует фразу в WAV. Поддерживает API piper-tts 1.3 и старее."""
    import speechtext
    text = speechtext.prepare(text)
    scale = SPEEDS.get(speed, 1.0)
    tmp = path + ".part"
    try:
        cfg = _syn_config(scale)
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
    _pad(tmp)
    os.replace(tmp, path)


def wav_seconds(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate() or 22050)


def cache_path(text: str, speed: str) -> str:
    d = config.local_dir() / "voice_cache"
    d.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{VOICE_NAME}|v2|{speed}|{text}".encode()).hexdigest()
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
    _pad(tmp)
    os.replace(tmp, path)
