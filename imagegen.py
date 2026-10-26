"""Рисование картинок по описанию («нарисуй кота в космосе»).
Сначала — через облачный сервер SenioreM (Cloudflare Workers AI, модель FLUX, бесплатно),
если он настроен; иначе — бесплатный сервис Pollinations."""
import base64
import json
import time
import urllib.parse
import urllib.request

import config

UA = {"User-Agent": "Mozilla/5.0 SenioreM"}


def images_dir():
    d = config.data_dir() / "chat_images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _english(prompt, settings):
    """Описание на английском (так картинки получаются лучше) — быстрой моделью, если есть."""
    try:
        import ai
        mode = settings["ai_mode"] if settings is not None else ""
        if mode not in ("api", "cloud") or ai.over_limit(settings):
            return prompt
        payload = {"messages": [
            {"role": "system", "content": "Translate the image description to English for an image "
                                          "generator. Add 3-6 words about style and quality. "
                                          "Answer with the prompt only."},
            {"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 400, "stream": False,
            "model_hint": "flash"}
        _r, data = ai.ENGINE._run(mode, settings, payload, None, False, True)
        out = ai.clean_reply(data["choices"][0]["message"]["content"]) if data else ""
        ai.usage_add(ai._estimate(payload["messages"], out, 0))
        return out or prompt
    except Exception:  # noqa: BLE001
        return prompt


def _check_image(raw):
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    im.load()
    return im


def _cloud(prompt):
    import ai
    u = ai.cloud_url()
    if not u:
        return None
    url = u.replace("/chat/completions", "/images/generations")
    req = urllib.request.Request(url, data=json.dumps({"prompt": prompt}).encode("utf-8"),
                                 method="POST", headers={**UA, "Content-Type": "application/json",
                                                         "Authorization": f"Bearer {ai.CLOUD_TOKEN}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    b64 = d.get("image") or ((d.get("data") or [{}])[0].get("b64_json"))
    return base64.b64decode(b64) if b64 else None


def _pollinations(prompt):
    q = urllib.parse.quote(prompt[:600])
    url = (f"https://image.pollinations.ai/prompt/{q}?width=1024&height=1024&nologo=true"
           f"&seed={int(time.time()) % 100000}")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def generate(prompt, settings=None):
    """-> путь к готовой картинке. Исключение с понятным текстом, если не получилось."""
    en = _english(prompt, settings)
    raw, last = None, None
    for fn in (_cloud, _pollinations):
        try:
            raw = fn(en)
            if raw:
                _check_image(raw)
                break
        except Exception as e:  # noqa: BLE001
            last, raw = e, None
    if not raw:
        raise RuntimeError(f"Не получилось нарисовать картинку ({last}). Проверьте интернет.")
    path = images_dir() / f"gen_{int(time.time() * 1000)}.jpg"
    im = _check_image(raw).convert("RGB")
    im.save(path, "JPEG", quality=92)
    return str(path)
