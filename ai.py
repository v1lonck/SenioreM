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


def cloud_url():
    """Адрес облачного ИИ (Cloudflare Worker), если он настроен в сборке."""
    u = (config.load_config().get("ai_proxy_url") or "").strip().rstrip("/")
    if u and not u.endswith("/chat/completions"):
        u += "/v1/chat/completions"
    return u


MEMORY_TURNS = 8          # сколько последних реплик помнит
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

    def _system(self, name, address):
        now = datetime.datetime.now()
        who = f" Обращайся к пользователю «{address}»." if address else ""
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
        return clean_reply(full)

    def ask(self, text, settings, context="", on_sentence=None):
        """-> ответ строкой. settings — профиль; context — свежие данные из интернета.
        on_sentence(фраза) — вызывается по мере готовности каждой фразы (чтобы сразу озвучивать)."""
        with self.lock:
            if time.time() - self.last_time > MEMORY_IDLE:
                self.history = []
            name = getattr(settings, "name", "Сеньор")
            system = self._system(name, settings["address"])
            # системное сообщение не меняется между вопросами — сервер ИИ не пересчитывает его
            # каждый раз (это главное ускорение); время и свежие данные — в конце
            msgs = [{"role": "system", "content": system}]
            msgs += self.history[-MEMORY_TURNS:]
            extra = f"(Сейчас {datetime.datetime.now():%H:%M}.)"
            if context:
                extra += ("\nСвежие данные из интернета (точные — отвечай по ним, называй конкретные "
                          "числа; не говори, что у тебя нет доступа к интернету):\n" + context)
            msgs.append({"role": "user", "content": text + "\n\n" + extra})
            mode = settings["ai_mode"] or "smart"
            long_ask = re.search(r"подробн|расскажи|объясни|история|почему|как работает|сравни",
                                 text.lower()) is not None
            payload = {"messages": msgs, "temperature": 0.4, "top_p": 0.9,
                       "max_tokens": 420 if long_ask else 220, "stream": False, "cache_prompt": True}
            try:
                if mode == "cloud" and not cloud_url():
                    mode = recommended_kind()          # облако не настроено — работаем на компьютере
                if mode == "cloud":
                    payload.pop("cache_prompt", None)
                    try:
                        if on_sentence is not None:
                            reply = self._ask_stream(cloud_url(), payload, on_sentence, CLOUD_TOKEN)
                            data = None
                        else:
                            data = _post(cloud_url(), payload, CLOUD_TOKEN, 40)
                    except Exception:  # noqa: BLE001 — нет интернета / облако занято: ИИ на компьютере
                        kind = recommended_kind()
                        if not local_ready(kind):
                            raise
                        payload["cache_prompt"] = True
                        self.start_local(kind)
                        url = f"http://127.0.0.1:{self.port}/v1/chat/completions"
                        data = None
                        if on_sentence is not None:
                            reply = self._ask_stream(url, payload, on_sentence, self.key)
                        else:
                            data = _post(url, payload, self.key)
                elif mode == "api":
                    base = (settings["ai_api_url"] or "").strip().rstrip("/")
                    if not base:
                        raise AIError("Укажите адрес API в профиле → «ИИ-собеседник».")
                    if not base.endswith("/chat/completions"):
                        base += "/chat/completions"
                    payload.pop("cache_prompt", None)
                    payload["model"] = (settings["ai_api_model"] or "").strip() or "gpt-4o-mini"
                    key = (settings["ai_api_key"] or "").strip()
                    data = None
                    if on_sentence is not None:
                        try:              # потоком: первая фраза звучит, пока ИИ дописывает остальное
                            reply = self._ask_stream(base, payload, on_sentence, key)
                        except urllib.error.HTTPError:
                            raise
                        except Exception:  # noqa: BLE001 — сервис не умеет потоком
                            data = _post(base, payload, key, 60)
                    else:
                        data = _post(base, payload, key, 60)
                else:
                    self.start_local(mode)
                    url = f"http://127.0.0.1:{self.port}/v1/chat/completions"
                    data = None
                    if on_sentence is not None:
                        reply = self._ask_stream(url, payload, on_sentence, self.key)
                    else:
                        data = _post(url, payload, self.key)
                if data is not None:
                    reply = clean_reply(data["choices"][0]["message"]["content"])
            except AIError:
                raise
            except urllib.error.HTTPError as e:
                raise AIError(f"Сервер ИИ ответил ошибкой {e.code}. Проверьте адрес, ключ и модель.")
            except Exception as e:  # noqa: BLE001
                raise AIError(f"ИИ сейчас недоступен: {e}")
            if not reply:
                reply = "Не знаю, что ответить. Спросите иначе."
            self.history += [{"role": "user", "content": text[:MEMORY_CHARS]},
                             {"role": "assistant", "content": reply[:MEMORY_CHARS]}]
            self.history = self.history[-MEMORY_TURNS:]
            self.last_time = time.time()
            return reply


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
