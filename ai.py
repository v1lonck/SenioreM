"""ИИ-собеседник. Бесплатно и без интернета: открытая модель Qwen 2.5 работает прямо на
компьютере через llama.cpp (llama-server). Можно подключить и свой OpenAI-совместимый API."""
import datetime
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import config

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
LLAMA_ZIP = "llama-server-win-x64.zip"
LLAMA_GPU_ZIP = "llama-server-win-vulkan.zip"     # для видеокарт: ответы в разы быстрее
MODELS = {
    "smart": ("Qwen2.5-3B-Instruct-Q4_K_M.gguf", 1_930_000_000,
              "https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/"),
    "fast": ("Qwen2.5-1.5B-Instruct-Q4_K_M.gguf", 990_000_000,
             "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"),
}
CLOUD_TOKEN = "seniorem-app"   # не секрет: просто чтобы облачный адрес не дёргали посторонние боты


_MODELS_CACHE = {}


def auto_model(chat_url, key, smart=False):
    """Модель не указана — берём из списка сервиса: обычно быструю (flash/mini/chat),
    для просьб «расскажи подробно», «объясни» — самую умную (pro/reasoner)."""
    base = chat_url.rsplit("/chat/completions", 1)[0]
    ids = _MODELS_CACHE.get(base)
    if ids is None:
        ids = []
        try:
            req = urllib.request.Request(base + "/models", headers={
                "Authorization": f"Bearer {key}", "User-Agent": "SenioreM"})
            with urllib.request.urlopen(req, timeout=10) as r:
                ids = [m.get("id", "") for m in json.load(r).get("data", []) if m.get("id")]
        except Exception:  # noqa: BLE001
            ids = []
        _MODELS_CACHE[base] = ids
    low = [(i, i.lower()) for i in ids]

    def pick(*words):
        for w in words:
            for i, li in low:
                if w in li and "embed" not in li and "whisper" not in li and "tts" not in li:
                    return i
        return None
    if smart:
        m = pick("v4-pro", "v4 pro", "pro", "reasoner", "v4", "chat")
    else:
        m = pick("v4-flash", "v4 flash", "flash", "chat", "mini", "v4")
    return m or (ids[0] if ids else "deepseek-chat")


def cloud_url():
    """Адрес облачного ИИ (Cloudflare Worker), если он настроен в сборке."""
    u = (config.load_config().get("ai_proxy_url") or "").strip().rstrip("/")
    if u and not u.endswith("/chat/completions"):
        u += "/v1/chat/completions"
    return u


MEMORY_TURNS = 6          # сколько последних реплик помнит (меньше — дешевле и быстрее)
MEMORY_CHARS = 600        # длинные реплики в памяти укорачиваем — меньше работы ИИ на каждый вопрос
MEMORY_IDLE = 15 * 60     # через 15 минут тишины начинает разговор заново


def ai_dir() -> Path:
    d = config.local_dir() / "ai"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _repo():
    return config.load_config().get("update_repo") or ""


def _mirror(name):
    r = _repo()
    return [f"https://github.com/{r}/releases/download/models/{name}"] if r else []


def model_file(kind) -> Path:
    return ai_dir() / MODELS[kind][0]


def server_exe(gpu=False):
    for p in (ai_dir() / ("llama-gpu" if gpu else "llama")).rglob("llama-server.exe"):
        return p
    return None


_GPU = None


def has_gpu():
    """Есть ли настоящая видеокарта (не «базовый адаптер» и не виртуальная)."""
    global _GPU
    if _GPU is None:
        if os.environ.get("SENIOREM_FORCE_GPU"):
            _GPU = True
            return _GPU
        _GPU = False
        if sys.platform == "win32":
            try:
                r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                    "(Get-CimInstance Win32_VideoController).Name"],
                                   capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW)
                names = [n.strip().lower() for n in r.stdout.splitlines() if n.strip()]
                bad = ("basic", "hyper-v", "remote", "virtual", "vmware", "virtualbox", "parsec",
                       "citrix", "mirror", "displaylink")
                _GPU = any(any(k in n for k in ("nvidia", "geforce", "radeon", "amd", "intel", "arc"))
                           and not any(b in n for b in bad) for n in names)
            except Exception:  # noqa: BLE001
                _GPU = False
    return _GPU


def _gpu_failed_flag():
    return ai_dir() / "gpu_failed"


def gpu_usable():
    return has_gpu() and not _gpu_failed_flag().exists()


def download_gpu(progress=None):
    """Сборка llama.cpp для видеокарты (Vulkan) — докачивается в фоне, если видеокарта есть."""
    if server_exe(gpu=True) is not None or not _mirror(LLAMA_GPU_ZIP):
        return server_exe(gpu=True) is not None
    import tts
    z = ai_dir() / LLAMA_GPU_ZIP
    tts.download(_mirror(LLAMA_GPU_ZIP), z, progress or (lambda d, t: None), expect=30_000_000)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(ai_dir() / "llama-gpu")
    z.unlink(missing_ok=True)
    return server_exe(gpu=True) is not None


_JOB = None


def _bind_to_app(proc):
    """Движок ИИ закрывается вместе с SenioreM — даже если программа упала или её сняли
    в диспетчере задач (объект задания Windows с «убить при закрытии»)."""
    global _JOB
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        if _JOB is None:
            job = k32.CreateJobObjectW(None, None)

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                            ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t),
                            ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                            ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

            class IO(ctypes.Structure):
                _fields_ = [(n, ctypes.c_uint64) for n in ("a", "b", "c", "d", "e", "f")]

            class EXT(ctypes.Structure):
                _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]
            info = EXT()
            info.Basic.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
            _JOB = job
        k32.AssignProcessToJobObject(_JOB, wintypes.HANDLE(int(proc._handle)))
    except Exception:  # noqa: BLE001
        pass


IDLE_STOP = 30 * 60          # полчаса без вопросов — выключаем движок ИИ, чтобы не занимал память


def _threads():
    """Потоки для ИИ: по числу настоящих ядер (не логических) — так быстрее всего."""
    try:
        import psutil
        phys = psutil.cpu_count(logical=False) or 0
    except Exception:  # noqa: BLE001
        phys = 0
    if not phys:
        phys = max(2, (os.cpu_count() or 4) // 2)
    # одно ядро оставляем свободным — для игр, браузера и самой программы
    return max(2, min(12, phys - 1 if phys >= 4 else phys))


def local_ready(kind) -> bool:
    if kind not in MODELS:
        return False
    m = model_file(kind)
    return server_exe() is not None and m.is_file() and m.stat().st_size > 100_000_000


def download_local(kind, progress=None):
    """Скачивает движок llama.cpp и модель. progress(доля 0..1, текст)."""
    import tts
    say = progress or (lambda f, t: None)
    if server_exe() is None:
        z = ai_dir() / LLAMA_ZIP
        urls = _mirror(LLAMA_ZIP) + _llama_github_urls()
        tts.download(urls, z, lambda d, t: say(0.05 * min(1.0, d / max(t, 1)),
                                               "Скачиваю движок ИИ"), expect=30_000_000)
        target = ai_dir() / "llama"
        with zipfile.ZipFile(z) as zf:
            zf.extractall(target)
        z.unlink(missing_ok=True)
        if server_exe() is None:
            raise RuntimeError("в архиве нет llama-server.exe")
    name, size, hf = MODELS[kind]
    m = model_file(kind)
    if not (m.is_file() and m.stat().st_size > 100_000_000):
        tts.download(_mirror(name) + [hf + name], m,
                     lambda d, t: say(0.05 + 0.95 * min(1.0, d / max(t, 1)),
                                      f"Скачиваю модель · {d / 1e9:.2f} из {t / 1e9:.2f} ГБ"),
                     expect=size)
    say(1.0, "Готово")


def _llama_github_urls():
    """Запасной путь: последняя сборка llama.cpp для Windows прямо с GitHub."""
    try:
        req = urllib.request.Request("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
                                     headers={"User-Agent": "SenioreM"})
        with urllib.request.urlopen(req, timeout=15) as r:
            rel = json.load(r)
        return [a["browser_download_url"] for a in rel.get("assets", [])
                if re.search(r"bin-win-cpu-x64\.zip$", a.get("name", ""))][:1]
    except Exception:  # noqa: BLE001
        return []


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _post(url, payload, key="", timeout=120):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "SenioreM"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _stream(url, payload, key="", timeout=120):
    """Ответ по кусочкам (как печатает): -> генератор строк."""
    payload = dict(payload, stream=True)
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "SenioreM",
               "Accept": "text/event-stream"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                delta = json.loads(body)["choices"][0].get("delta", {}).get("content") or ""
            except Exception:  # noqa: BLE001
                continue
            if delta:
                yield delta


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def clean_reply(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"[*_#`>]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"\s*\n\s*", " ", text).strip()
    return text


class AIError(Exception):
    pass


class AI:
    """Один экземпляр на программу. Потокобезопасный: вопросы обрабатываются по очереди."""

    def __init__(self):
        self.proc = None
        self.port = 0
        self.kind = None
        self.lock = threading.Lock()
        self.gpu = False
        self.key = ""
        self.history = []
        self.last_time = 0.0
        self.started = 0.0

    # ---------- локальный сервер ----------
    @staticmethod
    def kill_stale():
        """Закрывает «осиротевший» llama-server от прошлого запуска."""
        try:
            import psutil
            root = str(ai_dir()).lower()
            for p in psutil.process_iter(["name", "exe"]):
                if (p.info["name"] or "").lower() == "llama-server.exe" and \
                        (p.info["exe"] or "").lower().startswith(root):
                    p.kill()
        except Exception:  # noqa: BLE001
            pass

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start_local(self, kind, wait=True, timeout=180):
        if self.running() and self.kind == kind:
            return
        self.stop()
        if server_exe() is None or not model_file(kind).is_file():
            raise AIError("ИИ ещё не скачан — откройте профиль → «ИИ-собеседник».")
        # сначала пробуем видеокарту; не вышло — один раз запоминаем и дальше работаем на процессоре
        if gpu_usable() and server_exe(gpu=True) is not None:
            try:
                self._launch(kind, gpu=True)
                if wait:
                    self._wait_ready(min(timeout, 90))
                return
            except AIError:
                self.stop()
                try:
                    _gpu_failed_flag().write_text("1", encoding="utf-8")
                except OSError:
                    pass
        self._launch(kind, gpu=False)
        if wait:
            self._wait_ready(timeout)

    def _launch(self, kind, gpu):
        exe = server_exe(gpu=gpu)
        self.port = _free_port()
        threads = _threads()
        import secrets
        self.key = secrets.token_hex(16)        # только SenioreM может обращаться к своему движку ИИ
        args = [str(exe), "-m", str(model_file(kind)), "--host", "127.0.0.1", "--port", str(self.port),
                "--api-key", self.key,
                "-c", "4096", "-t", str(threads), "-tb", str(max(threads, os.cpu_count() or threads)),
                "-b", "512"]
        if gpu:
            args += ["-ngl", "99"]
        log = open(ai_dir() / "server.log", "w", encoding="utf-8", errors="ignore")
        self.proc = subprocess.Popen(args, cwd=str(exe.parent), stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=NO_WINDOW | 0x00004000)  # BELOW_NORMAL: не тормозит ПК
        _bind_to_app(self.proc)
        self._watch_idle()
        self.kind = kind
        self.gpu = gpu
        self.started = time.time()

    def _watch_idle(self):
        if getattr(self, "_idle_thread", None) is not None:
            return

        def work():
            while True:
                time.sleep(60)
                last = max(self.last_time, self.started)
                if self.running() and time.time() - last > IDLE_STOP and self.lock.acquire(False):
                    try:
                        self.stop()
                    finally:
                        self.lock.release()
        self._idle_thread = threading.Thread(target=work, daemon=True)
        self._idle_thread.start()

    def _wait_ready(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if not self.running():
                raise AIError("Движок ИИ не запустился (подробности в server.log).")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:  # noqa: BLE001 — сервер ещё загружает модель
                pass
            time.sleep(0.4)
        raise AIError("Движок ИИ слишком долго запускается.")

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.kill()
            except Exception:  # noqa: BLE001
                pass
            self.proc = None

    # ---------- разговор ----------
    def forget(self):
        self.history = []

    def _system(self, name, address, chat=False, code=False):
        now = datetime.datetime.now()
        who = f" Обращайся к пользователю «{address}»." if address else ""
        if chat:
            return (f"Ты — {name}, ИИ-помощник программы SenioreM (чат на экране). Отвечай по-русски, "
                    f"грамотно, точно и по существу, сначала главное. Можно использовать Markdown: "
                    f"списки, **жирный**, блоки кода с указанием языка. "
                    + ("Сейчас пользователь просит помощи с программированием: пиши рабочий, полный "
                       "код и коротко объясняй его. " if code else
                       "Обычно 2–6 предложений, подробнее — если просят. ")
                    + f"Если не уверен — честно скажи.{who} Сегодня {now:%d.%m.%Y}.")
        return (f"Ты — {name}, голосовой ИИ-помощник программы SenioreM на компьютере "
                f"пользователя. Отвечай по-русски, грамотно, дружелюбно, точно и по существу: "
                f"сначала главное, без вступлений и повторов вопроса. Обычно 1–3 законченных "
                f"предложения, потому что ответ звучит вслух; если просят рассказать подробно или "
                f"объяснить — до 5–6 предложений. Числа, даты и факты называй точно; если не "
                f"уверен — честно скажи. Не используй списки, разметку, "
                f"эмодзи и ссылки. Если просят что-то сделать на компьютере, а ты не можешь, "
                f"подскажи голосовую команду, например «{name}, открой телеграм» или "
                f"«{name}, громкость 30».{who} Сегодня {now:%d.%m.%Y}.")

    @staticmethod
    def _ask_stream(url, payload, on_sentence, key=""):
        buf, full = "", ""
        for piece in _stream(url, payload, key):
            buf += piece
            full += piece
            # отдаём законченные фразы сразу — помощник начинает говорить, пока ИИ дописывает
            while True:
                m = re.search(r"[.!?…](\s|$)", buf)
                if not m or m.end() < 12:
                    break
                sent, buf = buf[:m.end()], buf[m.end():]
                sent = clean_reply(sent)
                if sent:
                    on_sentence(sent)
        tail = clean_reply(buf)
        if tail:
            on_sentence(tail)
        return strip_think(full)

    def ask(self, text, settings, context="", on_sentence=None, images=None, prefer="auto",
            chat=False):
        """-> ответ строкой. settings — профиль; context — свежие данные из интернета.
        on_sentence(фраза) — вызывается по мере готовности каждой фразы (чтобы сразу озвучивать).
        images — пути к картинкам (ИИ их «видит», если умеет; иначе — распознанный на них текст).
        prefer — auto / fast / smart / local. chat — ответ в чат (можно длиннее, чем голосом)."""
        with self.lock:
            if time.time() - self.last_time > MEMORY_IDLE:
                self.history = []
            name = getattr(settings, "name", "Сеньор")
            system = self._system(name, settings["address"], chat, prefer == "code")
            msgs = [{"role": "system", "content": system}]
            msgs += self.history[-MEMORY_TURNS:]
            extra = f"(Сейчас {datetime.datetime.now():%H:%M}.)"
            if context:
                extra += ("\nСвежие данные из интернета (точные — отвечай по ним, называй конкретные "
                          "числа; не говори, что у тебя нет доступа к интернету):\n" + context[:2500])
            user_text = (text or "Что на картинке?") + "\n\n" + extra
            msgs.append({"role": "user", "content": user_text})
            mode = settings["ai_mode"] or "smart"
            if mode == "cloud" and not cloud_url():
                mode = recommended_kind()          # облако не настроено — работаем на компьютере
            long_ask = prefer in ("smart", "code") or (prefer == "auto" and re.search(
                r"подробн|расскажи|объясни|история|почему|как работает|сравни|напиши|придумай|код|"
                r"программ|скрипт|функци|python|питон|реши|задач", (text or "").lower()) is not None) \
                or bool(images)
            if prefer == "fast":
                long_ask = False
            # запас по длине: ответ не обрывается на полуслове (модель сама решает, сколько писать)
            if prefer == "code":
                max_tok = 3500
            elif chat:
                max_tok = 2000 if long_ask else 1000
            else:
                max_tok = 700 if long_ask else 400
            payload = {"messages": msgs, "temperature": 0.2 if prefer == "code" else 0.4, "top_p": 0.9,
                       "max_tokens": max_tok, "stream": False, "cache_prompt": True,
                       "model_hint": "pro" if long_ask else "flash"}
            remote = mode in ("api", "cloud") and prefer != "local"
            if remote and over_limit(settings):
                if local_ready(recommended_kind()):
                    remote, mode = False, recommended_kind()
                else:
                    raise AIError(limit_text(settings))
            if not remote and mode in ("api", "cloud"):
                mode = recommended_kind()
                if not local_ready(mode):
                    raise AIError("ИИ на компьютере ещё не скачан — профиль → «ИИ-собеседник».")
            # картинки: облачная модель смотрит сама; на компьютере — только распознанный текст
            vision = bool(images) and remote
            if images and not vision:
                msgs[-1]["content"] = user_text + _ocr_note(images)
            elif vision:
                msgs[-1]["content"] = [{"type": "text", "text": user_text}] + [
                    {"type": "image_url", "image_url": {"url": _data_url(p)}} for p in images]
            reply, data = "", None
            try:
                try:
                    reply, data = self._run(mode, settings, payload, on_sentence, long_ask, remote)
                except urllib.error.HTTPError as e:
                    if vision and e.code in (400, 404, 413, 415, 422, 500, 502, 503):
                        # модель не принимает картинки — отправляем распознанный на них текст
                        msgs[-1]["content"] = user_text + _ocr_note(images)
                        reply, data = self._run(mode, settings, payload, on_sentence, long_ask, remote)
                    else:
                        raise
                if data is not None:
                    reply = strip_think(data["choices"][0]["message"]["content"])
                reply = reply if chat else clean_reply(reply)
            except AIError:
                raise
            except urllib.error.HTTPError as e:
                raise AIError(f"Сервер ИИ ответил ошибкой {e.code}. Проверьте адрес, ключ и модель.")
            except Exception as e:  # noqa: BLE001
                raise AIError(f"ИИ сейчас недоступен: {e}")
            if remote:
                usage_add(_estimate(msgs, reply, len(images or [])))
            if not reply:
                reply = "Не знаю, что ответить. Спросите иначе."
            mark = " [фото]" if images else ""
            self.history += [{"role": "user", "content": (text or "")[:MEMORY_CHARS] + mark},
                             {"role": "assistant", "content": reply[:MEMORY_CHARS]}]
            self.history = self.history[-MEMORY_TURNS:]
            self.last_time = time.time()
            return reply

    def _run(self, mode, settings, payload, on_sentence, smart, remote):
        """Один запрос к нужному ИИ. -> (ответ из потока, данные обычного ответа)."""
        if remote and mode == "cloud":
            payload.pop("cache_prompt", None)
            try:
                if on_sentence is not None:
                    return self._ask_stream(cloud_url(), payload, on_sentence, CLOUD_TOKEN), None
                return "", _post(cloud_url(), payload, CLOUD_TOKEN, 40)
            except urllib.error.HTTPError:
                raise
            except Exception:  # noqa: BLE001 — нет интернета / облако занято: ИИ на компьютере
                kind = recommended_kind()
                if not local_ready(kind):
                    raise
                return self._run(kind, settings, payload, on_sentence, smart, False)
        if remote and mode == "api":
            base = (settings["ai_api_url"] or "").strip().rstrip("/")
            if not base:
                raise AIError("Укажите адрес API в профиле → «ИИ-собеседник».")
            if not base.endswith("/chat/completions"):
                base += "/chat/completions"
            payload.pop("cache_prompt", None)
            key = (settings["ai_api_key"] or "").strip()
            payload.pop("model_hint", None)
            payload["model"] = (settings["ai_api_model"] or "").strip() or auto_model(base, key, smart)
            if on_sentence is not None:
                try:              # потоком: первая фраза звучит, пока ИИ дописывает остальное
                    return self._ask_stream(base, payload, on_sentence, key), None
                except urllib.error.HTTPError:
                    raise
                except Exception:  # noqa: BLE001 — сервис не умеет потоком
                    pass
            return "", _post(base, payload, key, 60)
        payload["cache_prompt"] = True
        payload.pop("model", None)
        payload.pop("model_hint", None)
        self.start_local(mode)
        url = f"http://127.0.0.1:{self.port}/v1/chat/completions"
        if on_sentence is not None:
            return self._ask_stream(url, payload, on_sentence, self.key), None
        return "", _post(url, payload, self.key)

    def route_command(self, text, settings):
        """Быстрая модель переводит свободную фразу в команду SenioreM. -> команда или None."""
        mode = settings["ai_mode"] or "smart"
        if mode == "cloud" and not cloud_url():
            return None
        if mode not in ("api", "cloud") or over_limit(settings):
            return None
        payload = {"messages": [{"role": "system", "content": ROUTER_PROMPT},
                                {"role": "user", "content": text}],
                   "temperature": 0.0, "max_tokens": 60, "stream": False, "model_hint": "flash"}
        try:
            _r, data = self._run(mode, settings, payload, None, False, True)
            out = clean_reply(data["choices"][0]["message"]["content"]) if data else ""
        except Exception:  # noqa: BLE001
            return None
        usage_add(_estimate(payload["messages"], out, 0))
        out = out.strip().strip("«»\"'.")
        if out.upper().startswith("CMD:"):
            cmd = out[4:].strip().strip("«»\"'.")
            return cmd or None
        return None


ROUTER_PROMPT = (
    "Ты переводишь фразы пользователя в команды голосового помощника SenioreM для Windows. "
    "Если фраза — просьба что-то сделать на компьютере, ответь ОДНОЙ строкой «CMD: команда» в одном "
    "из видов: «громкость 30», «громче», «тише», «выключи звук», «включи звук», «яркость 50», "
    "«открой <программа или сайт>», «закрой <программа>», «сверни все окна», «найди <запрос>», "
    "«найди ролик <запрос>», «включи ролик <запрос>», «пауза», «следующий трек», «таймер на 5 минут», "
    "«разбуди в 7:30», «напомни через 10 минут <что>», «сделай скриншот», «заблокируй компьютер», "
    "«погода», «курс доллара», «который час», «закрой эту вкладку», «нажми <клавиша>». "
    "Если это вопрос, разговор или что-то другое — ответь ровно «ASK». Никаких пояснений."
)


# ---------------- картинки ----------------
def _data_url(path, side=1024):
    """Картинка -> data:image/jpeg;base64 (уменьшенная — меньше токенов и быстрее)."""
    import base64
    import io
    from PIL import Image
    im = Image.open(path)
    im = im.convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _ocr_note(images):
    """Текст, распознанный на картинках (для ИИ, который картинки не видит)."""
    parts = []
    for p in images:
        try:
            import control
            t = control.ocr_file(p)
        except Exception:  # noqa: BLE001
            t = ""
        parts.append(t.strip()[:1500])
    found = [t for t in parts if t]
    if not found:
        return ("\n\n(К сообщению приложена картинка, но разглядеть её этот ИИ не может и текста на ней "
                "нет. Честно скажи об этом и предложи выбрать облачный ИИ.)")
    return "\n\n(Текст, распознанный на приложенной картинке:\n" + "\n---\n".join(found) + ")"


# ---------------- расход токенов и лимиты ----------------
# Лимиты облачного ИИ одинаковы для всех и задаются владельцем SenioreM: в Cloudflare (переменные
# USER_DAY_TOKENS и USER_MONTH_TOKENS у сервера) — программа узнаёт их сама. Пользователь их не меняет.
DAY_LIMIT = 150_000           # по умолчанию: ~100 вопросов в день
MONTH_LIMIT = 3_000_000       # и ~2000 в месяц на одного пользователя
_SERVER = {"t": 0.0, "info": {}}


def server_info(refresh=False):
    """Сведения облачного сервера (/health): лимиты и что он умеет. Кэш на час."""
    u = cloud_url()
    if not u:
        return {}
    if not refresh and time.time() - _SERVER["t"] < 3600:
        return _SERVER["info"]
    _SERVER["t"] = time.time()
    try:
        base = u.split("/v1/")[0] if "/v1/" in u else u.rsplit("/chat/completions", 1)[0]
        req = urllib.request.Request(base + "/health", headers={"User-Agent": "SenioreM"})
        with urllib.request.urlopen(req, timeout=6) as r:
            info = json.loads(r.read().decode("utf-8"))
        if isinstance(info, dict):
            _SERVER["info"] = info
    except Exception:  # noqa: BLE001
        pass
    return _SERVER["info"]


def _usage_file():
    return config.data_dir() / "ai_usage.json"


def usage_get():
    today = datetime.date.today()
    try:
        d = json.loads(_usage_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if d.get("day") != today.isoformat():
        d["day"], d["day_tokens"] = today.isoformat(), 0
    if d.get("month") != today.strftime("%Y-%m"):
        d["month"], d["month_tokens"] = today.strftime("%Y-%m"), 0
    return d


def usage_add(n):
    d = usage_get()
    d["day_tokens"] = int(d.get("day_tokens", 0)) + int(n)
    d["month_tokens"] = int(d.get("month_tokens", 0)) + int(n)
    try:
        _usage_file().write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def limits(_settings=None):
    """-> (в день, в месяц) — как задал владелец (сервер), иначе из сборки, иначе по умолчанию."""
    cfg = config.load_config()
    day = int(cfg.get("ai_day_limit") or DAY_LIMIT)
    month = int(cfg.get("ai_month_limit") or MONTH_LIMIT)
    lim = (_SERVER["info"] or {}).get("limits") or {}
    try:
        day = int(lim.get("day") or day)
        month = int(lim.get("month") or month)
    except (TypeError, ValueError):
        pass
    return day, month


def limited(settings):
    """Лимиты действуют только на общий облачный ИИ (свой ключ — без лимитов)."""
    return settings is not None and (settings["ai_mode"] or "") == "cloud"


def over_limit(settings):
    if not limited(settings):
        return False
    d = usage_get()
    day, month = limits()
    return d["day_tokens"] >= day or d["month_tokens"] >= month


def limit_text(settings=None):
    d = usage_get()
    _day, month = limits()
    if d["month_tokens"] >= month:
        return ("Лимит облачного ИИ на этот месяц закончился — в следующем месяце снова. "
                "Пока можно скачать ИИ на компьютер: профиль → «ИИ-собеседник».")
    return "Лимит облачного ИИ на сегодня закончился — завтра снова."


def _estimate(msgs, reply, images):
    """Примерно сколько токенов ушло (русский текст ≈ 3 символа на токен)."""
    chars = 0
    for m in msgs:
        c = m.get("content")
        if isinstance(c, list):
            chars += sum(len(x.get("text", "")) for x in c if isinstance(x, dict))
        else:
            chars += len(c or "")
    return int((chars + len(reply or "")) / 3) + 900 * images


def fmt_tokens(n):
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} млн".replace(".0 ", " ")
    if n >= 1000:
        return f"{n // 1000} тыс."
    return str(n)


ENGINE = AI()


# ---------------- фоновое скачивание (одно на всю программу) ----------------
class Downloader:
    def __init__(self):
        self.active = False
        self.kind = None
        self.frac = 0.0
        self.text = ""
        self.error = ""
        self.done_kind = None

    def start(self, kind):
        if self.active:
            return
        self.active, self.kind, self.frac, self.error = True, kind, 0.0, ""
        self.text = "Готовлю ИИ"

        def work():
            try:
                download_local(kind, self._progress)
                self.done_kind = kind
            except Exception as e:  # noqa: BLE001
                self.error = f"Не удалось скачать ИИ: {e}"
            finally:
                self.active = False

        threading.Thread(target=work, daemon=True).start()

    def _progress(self, frac, text):
        self.frac, self.text = frac, text


DOWNLOADS = Downloader()


def recommended_kind() -> str:
    """«Умный», если хватает памяти и места на диске, иначе «Быстрый»."""
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / 1e9
    except Exception:  # noqa: BLE001
        ram_gb = 8
    try:
        import shutil
        free_gb = shutil.disk_usage(str(ai_dir())).free / 1e9
    except Exception:  # noqa: BLE001
        free_gb = 10
    return "smart" if ram_gb >= 7 and free_gb >= 4 else "fast"
