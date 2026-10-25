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
MODELS = {
    "smart": ("Qwen2.5-3B-Instruct-Q4_K_M.gguf", 1_930_000_000,
              "https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/"),
    "fast": ("Qwen2.5-1.5B-Instruct-Q4_K_M.gguf", 990_000_000,
             "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"),
}
MEMORY_TURNS = 8          # сколько последних реплик помнит
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


def server_exe():
    for p in (ai_dir() / "llama").rglob("llama-server.exe"):
        return p
    return None


def local_ready(kind) -> bool:
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
        self.history = []
        self.last_time = 0.0

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
        exe = server_exe()
        if exe is None or not model_file(kind).is_file():
            raise AIError("ИИ ещё не скачан — откройте профиль → «ИИ-собеседник».")
        self.port = _free_port()
        threads = max(2, (os.cpu_count() or 4) // 2)
        log = open(ai_dir() / "server.log", "w", encoding="utf-8", errors="ignore")
        self.proc = subprocess.Popen(
            [str(exe), "-m", str(model_file(kind)), "--host", "127.0.0.1", "--port", str(self.port),
             "-c", "4096", "-t", str(threads)],
            cwd=str(exe.parent), stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        self.kind = kind
        if wait:
            self._wait_ready(timeout)

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
                f"пользователя. Отвечай по-русски, грамотно, дружелюбно и по существу вопроса, "
                f"коротко: обычно 1–3 законченных предложения, потому что ответ звучит вслух. "
                f"Если не знаешь — честно скажи. Не используй списки, разметку, "
                f"эмодзи и ссылки. Если просят что-то сделать на компьютере, а ты не можешь, "
                f"подскажи голосовую команду, например «{name}, открой телеграм» или "
                f"«{name}, громкость 30».{who} Сейчас {now:%d.%m.%Y}, {now:%H:%M}.")

    def ask(self, text, settings, context=""):
        """-> ответ строкой. settings — профиль; context — свежие данные из интернета."""
        with self.lock:
            if time.time() - self.last_time > MEMORY_IDLE:
                self.history = []
            name = getattr(settings, "name", "Сеньор")
            system = self._system(name, settings["address"])
            if context:
                system += ("\n\nСвежие данные из интернета (точные и актуальные — отвечай по ним, "
                           "называй конкретные числа; не говори, что у тебя нет доступа к "
                           "интернету):\n" + context)
            msgs = [{"role": "system", "content": system}]
            msgs += self.history[-MEMORY_TURNS:]
            msgs.append({"role": "user", "content": text})
            mode = settings["ai_mode"] or "smart"
            payload = {"messages": msgs, "temperature": 0.5, "max_tokens": 260, "stream": False}
            try:
                if mode == "api":
                    base = (settings["ai_api_url"] or "").strip().rstrip("/")
                    if not base:
                        raise AIError("Укажите адрес API в профиле → «ИИ-собеседник».")
                    if not base.endswith("/chat/completions"):
                        base += "/chat/completions"
                    payload["model"] = (settings["ai_api_model"] or "").strip() or "gpt-4o-mini"
                    data = _post(base, payload, (settings["ai_api_key"] or "").strip(), 60)
                else:
                    self.start_local(mode)
                    data = _post(f"http://127.0.0.1:{self.port}/v1/chat/completions", payload)
                reply = clean_reply(data["choices"][0]["message"]["content"])
            except AIError:
                raise
            except urllib.error.HTTPError as e:
                raise AIError(f"Сервер ИИ ответил ошибкой {e.code}. Проверьте адрес, ключ и модель.")
            except Exception as e:  # noqa: BLE001
                raise AIError(f"ИИ сейчас недоступен: {e}")
            if not reply:
                reply = "Не знаю, что ответить. Спросите иначе."
            self.history += [{"role": "user", "content": text},
                             {"role": "assistant", "content": reply}]
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
