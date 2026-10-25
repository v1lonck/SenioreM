"""Управление открытыми программами и играми голосом:
«нажми пробел», «нажми на да», «кликни», «включи первое видео», «включи на ютубе котиков»,
«перемотай вперёд», «на весь экран».

Как это работает:
* клавиши отправляются в окно, которое было открыто перед SenioreM (игра, браузер);
* «нажми на <текст>» ищет кнопку с таким текстом через специальные возможности Windows
  (UI Automation), а если это игра и кнопок там нет — распознаёт текст на экране встроенным
  в Windows распознаванием (OCR) и нажимает мышкой в это место;
* YouTube: адрес открытой страницы читается из браузера, список видео берётся с сайта."""
import ctypes
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

NO_WINDOW = 0x08000000

KEYS = {
    "пробел": 0x20, "space": 0x20, "спейс": 0x20, "энтер": 0x0D, "enter": 0x0D, "ввод": 0x0D,
    "интер": 0x0D, "эскейп": 0x1B, "escape": 0x1B, "esc": 0x1B, "эскейт": 0x1B, "таб": 0x09,
    "tab": 0x09, "шифт": 0x10, "shift": 0x10, "контрл": 0x11, "ctrl": 0x11, "контрол": 0x11,
    "альт": 0x12, "alt": 0x12, "бэкспейс": 0x08, "backspace": 0x08, "удалить": 0x2E, "делит": 0x2E,
    "delete": 0x2E, "вверх": 0x26, "вниз": 0x28, "влево": 0x25, "вправо": 0x27,
    "стрелку вверх": 0x26, "стрелку вниз": 0x28, "стрелку влево": 0x25, "стрелку вправо": 0x27,
    "стрелка вверх": 0x26, "стрелка вниз": 0x28, "стрелка влево": 0x25, "стрелка вправо": 0x27,
    "home": 0x24, "end": 0x23, "пейдж ап": 0x21, "пейдж даун": 0x22,
}
# буквы, как их произносят: «нажми вэ», «нажми дабл ю», «нажми е»
LETTER_NAMES = {
    "а": "A", "эй": "A", "би": "B", "бэ": "B", "си": "C", "ди": "D", "дэ": "D", "и": "E", "е": "E",
    "эф": "F", "джи": "G", "эйч": "H", "ай": "I", "джей": "J", "кей": "K", "ка": "K", "эл": "L",
    "эм": "M", "эн": "N", "о": "O", "пи": "P", "пэ": "P", "кью": "Q", "ар": "R", "эр": "R", "эс": "S",
    "ти": "T", "тэ": "T", "ю": "U", "у": "U", "ви": "V", "вэ": "V", "дабл ю": "W", "дабл": "W",
    "икс": "X", "уай": "Y", "игрек": "Y", "зет": "Z", "зэт": "Z",
    # одна русская буква, похожая на латинскую
    "с": "C", "к": "K", "м": "M", "т": "T", "р": "R", "х": "X", "з": "Z", "в": "V", "д": "D",
    "ф": "F", "г": "G", "л": "L", "п": "P", "н": "N", "б": "B", "ш": "W", "ж": "J", "й": "Q",
}
NUM_WORDS = {"один": 1, "одну": 1, "раз": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
             "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "ноль": 0}
ORDINALS = {"первое": 1, "первый": 1, "1": 1, "второе": 2, "второй": 2, "2": 2, "третье": 3,
            "третий": 3, "3": 3, "четвертое": 4, "четвертый": 4, "4": 4, "пятое": 5, "пятый": 5,
            "5": 5, "шестое": 6, "седьмое": 7, "восьмое": 8, "девятое": 9, "десятое": 10}
YT_KEYS = {"forward": ("L", "Перематываю вперёд."), "back": ("J", "Перематываю назад."),
           "full": ("F", "Готово."), "subs": ("C", "Готово."), "mute": ("M", "Готово."),
           "next": ("SHIFT+N", "Следующее видео."), "prev": ("SHIFT+P", "Предыдущее видео."),
           "pause": ("K", "Готово."), "theatre": ("T", "Готово.")}


# ------------------------------------------------------------------ разбор фраз
def _norm(text):
    import commands
    return commands.normalize(text)


def parse(text):
    """-> intent или None (если это не команда управления)."""
    t = _norm(text)
    if not t:
        return None
    # --- YouTube
    m = re.search(r"\b(включи|открой|запусти|поставь|покажи|давай)\s+(\w+)\s+(видео|ролик|видос)\w*", t)
    if m and m.group(2) in ORDINALS:
        return {"action": "yt_nth", "n": ORDINALS[m.group(2)]}
    verb = q = None
    m = re.search(r"\b(включи|поставь|найди|открой|покажи|запусти)\s+(на|в)\s+(ютуб\w*|youtube)\s+(.+)$", t)
    if m:
        verb, q = m.group(1), m.group(4)
    else:
        m = re.search(r"\b(включи|поставь|найди|покажи|запусти)\s+(.+?)\s+(на|в)\s+(ютуб\w*|youtube)$", t)
        if m:
            verb, q = m.group(1), m.group(2)
    if q:
        q = re.sub(r"^(видео|ролик|видос)\s+(про\s+)?", "", q).strip()
        if q:
            return {"action": "yt_play", "query": q, "search_only": verb == "найди"}
    if re.search(r"(видео|ролик|видос|ютуб)", t) or _yt_hint(t):
        if re.search(r"перемота\w* (вперед|дальше)|вперед на|промотай", t):
            return {"action": "yt_key", "key": "forward"}
        if re.search(r"перемота\w* назад|назад на", t):
            return {"action": "yt_key", "key": "back"}
        if re.search(r"на весь экран|полный экран|во весь экран", t):
            return {"action": "yt_key", "key": "full"}
        if re.search(r"субтитр", t):
            return {"action": "yt_key", "key": "subs"}
        if re.search(r"следующ", t):
            return {"action": "yt_key", "key": "next"}
        if re.search(r"предыдущ", t):
            return {"action": "yt_key", "key": "prev"}
    if re.search(r"^(перемотай|промотай) (вперед|дальше)", t):
        return {"action": "yt_key", "key": "forward"}
    if re.search(r"^перемотай назад", t):
        return {"action": "yt_key", "key": "back"}
    if re.search(r"^(сделай )?(на весь экран|во весь экран|полноэкранный)", t):
        return {"action": "yt_key", "key": "full"}
    # --- клавиши и клики
    m = re.match(r"^(нажми|нажать|жми|кликни|клик|тыкни|ткни|щелкни|нажмите|выбери)\b\s*(.*)$", t)
    if not m:
        return None
    verb, rest = m.group(1), m.group(2).strip()
    times = 1
    tm = re.search(r"\s(\d+|два|две|три|четыре|пять|десять)\s+раз\w*$", " " + rest)
    if tm:
        times = int(tm.group(1)) if tm.group(1).isdigit() else NUM_WORDS.get(tm.group(1), 1)
        rest = rest[: tm.start()].strip() if tm.start() > 0 else ""
        rest = re.sub(r"\s(\d+|два|две|три|четыре|пять|десять)\s+раз\w*$", "", " " + rest).strip()
    rest = re.sub(r"^(на|по)\s+", "", rest)
    if rest in ("", "мышкой", "мышью", "левой", "левой кнопкой", "мышку"):
        return {"action": "mouse_click", "button": "left", "times": times}
    if rest in ("правой", "правой кнопкой", "правой кнопкой мыши"):
        return {"action": "mouse_click", "button": "right", "times": times}
    key = key_for(re.sub(r"^(кнопку|клавишу|клавиша|кнопка)\s+", "", rest))
    if key and not rest.startswith(("кнопку ", "кнопка ")):
        return {"action": "press_key", "keys": key, "times": times, "name": rest}
    target = re.sub(r"^(кнопку|кнопка|ссылку|пункт|надпись|слово)\s+", "", rest)
    om = re.match(r"^(\w+)\s+(видео|ролик|видос)", target)
    if om and om.group(1) in ORDINALS:
        return {"action": "yt_nth", "n": ORDINALS[om.group(1)]}
    return {"action": "click_text", "text": target}


def _yt_hint(t):
    """Открыт ли сейчас YouTube (тогда «следующее», «на весь экран» — про видео)."""
    try:
        import procs
        w = procs.foreground()
        return bool(w and "youtube" in (w.title or "").lower())
    except Exception:  # noqa: BLE001
        return False


def key_for(name):
    """«пробел» -> [0x20]; «контрл с» -> [0x11, 0x53]; «w» -> [0x57]; «ф5» -> [0x74]."""
    name = name.strip().lower()
    if not name:
        return None
    if name in KEYS:
        return [KEYS[name]]
    m = re.fullmatch(r"(f|ф|эф)\s*(\d{1,2})", name)
    if m and 1 <= int(m.group(2)) <= 12:
        return [0x70 + int(m.group(2)) - 1]
    if re.fullmatch(r"[a-z0-9]", name):
        return [ord(name.upper())]
    if name in LETTER_NAMES:
        return [ord(LETTER_NAMES[name])]
    parts = name.replace("+", " плюс ").split()
    if len(parts) >= 2 and ("плюс" in parts or parts[0] in KEYS):
        out = []
        for part in [x for x in parts if x != "плюс"]:
            k = key_for(part)
            if not k:
                return None
            out += k
        return out
    return None


# ------------------------------------------------------------------ ввод
def _target_window():
    import procs
    return procs.foreground()


def _focus(win):
    import procs
    if win is not None:
        procs.activate(win.hwnd)
        time.sleep(0.25)


def _send(vk, up=False):
    u = ctypes.windll.user32
    scan = u.MapVirtualKeyW(vk, 0)
    ext = vk in (0x25, 0x26, 0x27, 0x28, 0x2E, 0x24, 0x23, 0x21, 0x22)
    flags = (0x0002 if up else 0) | (0x0001 if ext else 0)
    u.keybd_event(vk, scan, flags, 0)


def press(keys, times=1):
    for _ in range(max(1, min(times, 30))):
        for k in keys:
            _send(k)
            time.sleep(0.02)
        time.sleep(0.04)
        for k in reversed(keys):
            _send(k, up=True)
            time.sleep(0.02)
        time.sleep(0.08)


def click_at(x, y, button="left", times=1):
    u = ctypes.windll.user32
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    down, up = (0x0002, 0x0004) if button == "left" else (0x0008, 0x0010)
    for _ in range(max(1, times)):
        u.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.04)
        u.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.08)


def type_text(text):
    """Печатает текст (любые буквы) — через Unicode-ввод."""
    for ch in text:
        code = ord(ch)
        _unicode(code, False)
        _unicode(code, True)
        time.sleep(0.004)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _unicode(code, up):
    inp = _INPUT()
    inp.type = 1
    inp.ki = _KEYBDINPUT(0, code, 0x0004 | (0x0002 if up else 0), 0, 0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


# ------------------------------------------------------------------ поиск текста на экране
def _rect(hwnd):
    import ctypes.wintypes as wt
    r = wt.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _similar(a, b):
    import sites
    a, b = sites._norm(a), sites._norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if b.startswith(a + " ") or b.startswith(a):
        return 0.9 if len(a) >= 3 or len(b) <= 4 else 0.75
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


_uia = None


def _uia_client():
    global _uia
    if _uia is None:
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
        _uia = comtypes.client.CreateObject(CUIAutomation._reg_clsid_, interface=IUIAutomation)
    return _uia


CLICKABLE = {50000, 50005, 50011, 50007, 50019, 50002, 50013, 50020, 50003, 50006, 50021, 50031}


def find_uia(hwnd, text, limit_s=2.5):
    """Элемент окна с похожей надписью (кнопка, ссылка, пункт меню). -> (x, y, имя) или None."""
    import comtypes
    try:
        comtypes.CoInitialize()
    except Exception:  # noqa: BLE001
        pass
    uia = _uia_client()
    root = uia.ElementFromHandle(hwnd)
    arr = root.FindAll(4, uia.CreateTrueCondition())        # TreeScope_Descendants
    best, best_sc = None, 0.0
    t0 = time.time()
    n = min(arr.Length, 4000)
    for i in range(n):
        if time.time() - t0 > limit_s:
            break
        try:
            el = arr.GetElement(i)
            name = el.CurrentName or ""
            if not name or len(name) > 80 or el.CurrentControlType not in CLICKABLE:
                continue
            sc = _similar(text, name)
            if sc > best_sc:
                if el.CurrentIsOffscreen:
                    continue
                r = el.CurrentBoundingRectangle
                if r.right - r.left < 2 or r.bottom - r.top < 2:
                    continue
                best, best_sc = ((r.left + r.right) / 2, (r.top + r.bottom) / 2, name), sc
        except Exception:  # noqa: BLE001
            continue
    return best if best_sc >= 0.78 else None


OCR_PS = r"""
param([string]$img, [int]$x, [int]$y, [int]$w, [int]$h)
Add-Type -Name D -Namespace W -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[W.D]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap([int]$w, [int]$h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, $bmp.Size)
$bmp.Save($img, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Foundation.IAsyncOperation`1, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($img)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$sb = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$res = @()
$langs = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages)
[Console]::Error.WriteLine("ocr langs: " + ($langs | ForEach-Object { $_.LanguageTag }) -join ",")
$engines = @()
foreach ($lang in $langs) { $e = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang); if ($e) { $engines += $e } }
if ($engines.Count -eq 0) { $e = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages(); if ($e) { $engines += $e } }
[Console]::Error.WriteLine("engines: " + $engines.Count + " bitmap: " + ($sb -ne $null))
foreach ($eng in $engines) {
  if ($eng -eq $null) { continue }
  $r = Await ($eng.RecognizeAsync($sb)) ([Windows.Media.Ocr.OcrResult])
  foreach ($l in $r.Lines) { foreach ($wd in $l.Words) {
    $res += [pscustomobject]@{t=$wd.Text; x=$wd.BoundingRect.X; y=$wd.BoundingRect.Y; w=$wd.BoundingRect.Width; h=$wd.BoundingRect.Height; line=$l.Text}
  } }
}
$stream.Dispose()
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$res | ConvertTo-Json -Compress
"""


OCR_ERR = ""


def ocr_words(left, top, width, height):
    """Слова на экране в прямоугольнике: [{t, x, y, w, h, line}] (координаты экрана)."""
    d = tempfile.gettempdir()
    script = os.path.join(d, "seniorem_ocr.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(OCR_PS)
    img = os.path.join(d, "seniorem_ocr.png")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                        img, str(left), str(top), str(width), str(height)],
                       capture_output=True, timeout=25, creationflags=NO_WINDOW)
    out = r.stdout.decode("utf-8", "ignore").strip()
    global OCR_ERR
    OCR_ERR = r.stderr.decode("utf-8", "ignore").strip()[:900]
    if not out:
        return []
    data = json.loads(out)
    if isinstance(data, dict):
        data = [data]
    for w in data:
        w["x"] += left
        w["y"] += top
    return data


def find_ocr(rect, text):
    left, top, right, bottom = rect
    words = ocr_words(left, top, right - left, bottom - top)
    if not words:
        return None
    import sites
    target = sites._norm(text).split()
    if not target:
        return None
    best, best_sc = None, 0.0
    for i, w in enumerate(words):
        # фраза из нескольких слов: берём подряд идущие слова той же строки
        group = [w]
        j = i + 1
        while len(group) < len(target) and j < len(words) and words[j].get("line") == w.get("line"):
            group.append(words[j])
            j += 1
        phrase = " ".join(g["t"] for g in group)
        sc = _similar(" ".join(target), phrase)
        if sc > best_sc:
            x1 = min(g["x"] for g in group)
            y1 = min(g["y"] for g in group)
            x2 = max(g["x"] + g["w"] for g in group)
            y2 = max(g["y"] + g["h"] for g in group)
            best, best_sc = ((x1 + x2) / 2, (y1 + y2) / 2, phrase), sc
    return best if best_sc >= 0.72 else None


def click_text(text):
    win = _target_window()
    if win is None:
        return "Не вижу открытых окон."
    _focus(win)
    hit = None
    try:
        hit = find_uia(win.hwnd, text)
    except Exception:  # noqa: BLE001
        hit = None
    how = "кнопку"
    if hit is None:
        try:
            hit = find_ocr(_rect(win.hwnd), text)
            how = "надпись"
        except Exception:  # noqa: BLE001
            hit = None
    if hit is None:
        return f"Не нашёл «{text}» в окне «{win.title[:40]}»."
    x, y, name = hit
    _focus(win)
    click_at(x, y)
    return f"Нажал «{name}»."


# ------------------------------------------------------------------ YouTube
BROWSER_EXES = {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "browser.exe", "brave.exe",
                "vivaldi.exe", "yandex.exe"}


def _browser_window(prefer_youtube=True):
    import procs
    wins = [w for w in procs.windows() if w.exe in BROWSER_EXES]
    if prefer_youtube:
        for w in wins:
            if "youtube" in w.title.lower():
                return w
    return wins[0] if wins else None


def browser_url(win):
    """Адрес открытой страницы из адресной строки браузера."""
    try:
        uia = _uia_client()
        root = uia.ElementFromHandle(win.hwnd)
        cond = uia.CreatePropertyCondition(30003, 50004)        # ControlType = Edit
        arr = root.FindAll(4, cond)
        for i in range(min(arr.Length, 12)):
            el = arr.GetElement(i)
            try:
                v = el.GetCurrentPropertyValue(30045) or ""     # Value
            except Exception:  # noqa: BLE001
                v = ""
            if v and ("." in v or v.startswith("http")) and " " not in v.strip():
                return v if v.startswith("http") else "https://" + v
    except Exception:  # noqa: BLE001
        pass
    return ""


def _fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0 Safari/537.36", "Accept-Language": "ru-RU,ru;q=0.9",
        "Cookie": "CONSENT=YES+1; SOCS=CAI"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8", "ignore")


def video_ids(page_url):
    """Видео на странице YouTube по порядку."""
    html = _fetch(page_url)
    ids = []
    for m in re.finditer(r'"(?:videoRenderer|gridVideoRenderer|compactVideoRenderer|'
                         r'richItemRenderer|lockupViewModel)".{0,400}?"(?:videoId|contentId)":"([\w-]{11})"',
                         html):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    if not ids:
        for m in re.finditer(r'"videoId":"([\w-]{11})"', html):
            if m.group(1) not in ids:
                ids.append(m.group(1))
    return ids


def search_url(query):
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)


def _navigate(win, url):
    """Открыть адрес в той же вкладке браузера."""
    _focus(win)
    press([0x11, 0x4C])            # Ctrl+L — адресная строка
    time.sleep(0.15)
    type_text(url)
    time.sleep(0.05)
    press([0x0D])


def yt_nth(n):
    win = _browser_window()
    url = browser_url(win) if win else ""
    if not url or "youtube.com" not in url:
        if win is None or "youtube" not in (win.title or "").lower():
            return "Сначала откройте YouTube — например, скажите «открой ютуб»."
        url = "https://www.youtube.com/"
    ids = video_ids(url)
    if len(ids) < n:
        return "Не получилось найти видео на этой странице."
    _navigate(win, f"https://www.youtube.com/watch?v={ids[n - 1]}")
    return "Включаю." if n == 1 else f"Включаю {n}-е видео."


def yt_play(query, search_only=False):
    import webbrowser
    if search_only:
        webbrowser.open(search_url(query))
        return f"Ищу на YouTube: {query}."
    ids = video_ids(search_url(query))
    if not ids:
        webbrowser.open(search_url(query))
        return f"Открыл поиск на YouTube: {query}."
    url = f"https://www.youtube.com/watch?v={ids[0]}"
    win = _browser_window()
    if win is not None and "youtube" in (win.title or "").lower():
        _navigate(win, url)
    else:
        webbrowser.open(url)
    return f"Включаю на YouTube: {query}."


def yt_key(name):
    keys, reply = YT_KEYS[name]
    win = _browser_window()
    if win is None:
        return "Не вижу открытого видео."
    _focus(win)
    seq = [0x10, ord("N")] if keys == "SHIFT+N" else ([0x10, ord("P")] if keys == "SHIFT+P" else [ord(keys)])
    press(seq)
    return reply


# ------------------------------------------------------------------ вход
def run(intent):
    a = intent["action"]
    if a == "press_key":
        win = _target_window()
        if win is None:
            return "Не вижу открытых окон."
        _focus(win)
        press(intent["keys"], intent.get("times", 1))
        return "Нажал." if intent.get("times", 1) == 1 else f"Нажал {intent['times']} раза."
    if a == "mouse_click":
        win = _target_window()
        _focus(win)
        import ctypes.wintypes as wt
        pt = wt.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        click_at(pt.x, pt.y, intent.get("button", "left"), intent.get("times", 1))
        return "Кликнул."
    if a == "click_text":
        return click_text(intent["text"])
    if a == "yt_nth":
        return yt_nth(intent["n"])
    if a == "yt_play":
        return yt_play(intent["query"], intent.get("search_only"))
    if a == "yt_key":
        return yt_key(intent["key"])
    return ""


ACTIONS = ("press_key", "mouse_click", "click_text", "yt_nth", "yt_play", "yt_key")
