"""Сценарии — свои фразы и что по ним делать: «игровой режим», «я дома», «включи впн».

Сценарий: {"id", "name", "phrases": [...], "steps": [...]}
Шаги:
  {"type": "app", "name": "Steam", "target": ["lnk", "C:\\...\\Steam.lnk"], "admin": false}
  {"type": "file", "name": "general", "path": "C:\\...\\general.bat", "admin": true}
  {"type": "site", "url": "https://music.yandex.ru"}
  {"type": "command", "text": "громкость 30"}            — любая команда SenioreM
  {"type": "click", "text": "Подключить", "wait": 15}    — нажать кнопку в открывшемся окне
  {"type": "vpn"}                                        — включить VPN (см. настройки VPN)
  {"type": "wait", "seconds": 3}
"""
import json
import os
import re
import time
import uuid
from difflib import SequenceMatcher

DEFAULT = [
    {"id": "game", "name": "Игровой режим",
     "phrases": ["игровой режим", "режим игры", "включи игровой режим", "давай поиграем"],
     "steps": []},
    {"id": "home", "name": "Я дома",
     "phrases": ["я дома", "я пришел", "я вернулся"],
     "steps": [{"type": "command", "text": "открой яндекс музыку"}]},
]
VPN_HINTS = ("vpn", "впн", "hiddify", "v2ray", "nekoray", "nekobox", "happ", "amnezia", "outline",
             "wireguard", "openvpn", "proton", "windscribe", "warp", "1 1 1 1", "clash", "karing",
             "throne", "psiphon", "hotspot shield", "invizible", "adguard vpn", "planet", "lantern",
             "streisand", "sing box", "singbox", "v2rayn", "foxray", "shadowsocks", "radmin")
CONNECT_WORDS = ("Подключить", "Подключиться", "Connect", "Включить", "Старт", "Start", "Запустить",
                 "Turn on", "Вкл", "ON", "Tap to connect")
ACTIONS = ("scenario", "vpn", "vpn_off")


def new_id():
    return uuid.uuid4().hex[:8]


def get(settings):
    sc = settings["scenarios"] if settings is not None else None
    if sc is None:
        sc = json.loads(json.dumps(DEFAULT))
    return sc


def _norm(t):
    import commands
    return commands.normalize(t)


def match(text, settings):
    """Фраза пользователя -> intent сценария / VPN или None."""
    t = _norm(text)
    if not t:
        return None
    if re.search(r"^(включи|открой|запусти|подключи|врубай|вруби)\s+(мне\s+)?(впн|vpn|випиэн|впнку)\b", t) \
            or t in ("впн", "vpn", "подключи впн", "подключись к впн"):
        return {"action": "vpn", "vpn": dict(settings["vpn"] or {}) if settings is not None else {}}
    if re.search(r"^(выключи|отключи|закрой|вырубай|выруби)\s+(впн|vpn|випиэн|впнку)\b", t):
        return {"action": "vpn_off", "vpn": dict(settings["vpn"] or {}) if settings is not None else {}}
    if settings is None:
        return None
    for sc in get(settings):
        for ph in sc.get("phrases") or []:
            p = _norm(ph)
            if not p:
                continue
            if t == p or t.startswith(p + " ") or (len(p) >= 6 and p in t) or \
                    SequenceMatcher(None, t, p).ratio() >= 0.86:
                return {"action": "scenario", "scenario": sc,
                        "vpn": dict(settings["vpn"] or {})}
    return None


# ------------------------------------------------------------------ запуск
def launch(target, name="", admin=False, why="сценарий"):
    """Запустить программу; admin=True — от имени администратора."""
    import sites
    kind, value = target
    if not admin:
        return sites.launch(tuple(target), name, why)
    import elevate
    sites.log_launch(name or value, tuple(target), why + " (от администратора)")
    path = value
    if kind == "app":
        import procs
        _dirs, exes, _pkg = procs.locate(("app", value))
        if not exes:
            return sites.launch(("app", value), name, why)
        path = sorted(exes)[0]
    elif kind == "url":
        return sites.launch(("url", value), name, why)
    elif kind == "path" and os.path.isdir(path):
        path = sites._pick_launcher(path) or path
    elevate.run_as_admin(path, "", wait=False, show=1)
    return "Запускаю"


def _last_vpn_file():
    import config
    return config.data_dir() / "last_vpn.json"


def remember_if_vpn(name, target):
    """Запомнить VPN, который открывали последним (для «включи впн»)."""
    if not is_vpn(name):
        return
    try:
        with open(_last_vpn_file(), "w", encoding="utf-8") as f:
            json.dump({"name": name, "target": list(target)}, f, ensure_ascii=False)
    except OSError:
        pass


def is_vpn(name):
    import sites
    n = " " + sites._norm(name or "") + " "
    return any((" " + h + " ") in n or (len(h) >= 5 and h in n) for h in VPN_HINTS)


def installed_vpns():
    import sites
    sites.refresh_apps()
    return [(o, t) for n, o, t in sites._apps if is_vpn(o) and not n.endswith(" bluestacks")]


def pick_vpn(cfg):
    if cfg.get("app"):
        return cfg["app"]["name"], tuple(cfg["app"]["target"])
    try:
        with open(_last_vpn_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d["name"], tuple(d["target"])
    except (OSError, ValueError, KeyError):
        pass
    found = installed_vpns()
    return found[0] if found else (None, None)


def vpn_on(cfg):
    import control
    import procs
    name, target = pick_vpn(cfg)
    if not name:
        return ("Не нашёл VPN на компьютере. Укажите его в профиле → «Сценарии» → «VPN» "
                "или откройте его один раз командой «открой …».")
    admin = cfg.get("admin", True)
    state = procs.bring_up(name, target)
    if state is None:
        launch(target, name, admin, "включи впн")
    remember_if_vpn(name, target)
    if not cfg.get("click", True):
        return f"Открываю {name}."
    words = [cfg["button"]] if cfg.get("button") else []
    words += list(CONNECT_WORDS)
    end = time.time() + 25
    clicked = None
    while time.time() < end and not clicked:
        time.sleep(2.0)
        wins, _ = procs.find(name, target)
        if not wins:
            continue
        clicked = control.click_in(wins[0], words, min_score=0.93)
    if clicked:
        return f"Включил {name} и нажал «{clicked}»."
    import elevate
    if admin and not elevate.is_admin():
        return (f"Открыл {name}. Нажать «Подключить» в программе, запущенной от администратора, "
                f"SenioreM сможет, если включить «Работать с правами администратора» в профиле → «Запуск».")
    return (f"Открыл {name}, но не нашёл кнопку подключения (возможно, уже подключено). Если кнопка "
            f"называется иначе — впишите её текст в профиле → «Сценарии» → «VPN».")


def vpn_off(cfg):
    import procs
    name, target = pick_vpn(cfg)
    if not name:
        return "Не знаю, какой у вас VPN."
    n, _ = procs.close(name, target)
    return f"Закрыл {name}." if n else f"{name} сейчас не запущен."


def run_steps(sc, cfg, depth=0):
    import actions
    import commands
    import control
    import system
    import timers
    import webbrowser
    done = []
    last_win_name, last_target = None, None
    for st in sc.get("steps") or []:
        kind = st.get("type")
        try:
            if kind == "app":
                import procs
                tgt = tuple(st["target"])
                if procs.bring_up(st.get("name", ""), tgt) is None:
                    launch(tgt, st.get("name", ""), st.get("admin", False), "сценарий: " + sc["name"])
                last_win_name, last_target = st.get("name", ""), tgt
                done.append(st.get("name", ""))
                time.sleep(1.0)
            elif kind == "file":
                launch(("path", st["path"]), st.get("name", ""), st.get("admin", False),
                       "сценарий: " + sc["name"])
                last_win_name, last_target = st.get("name", ""), ("path", st["path"])
                done.append(st.get("name") or os.path.basename(st["path"]))
                time.sleep(1.0)
            elif kind == "site":
                webbrowser.open(st["url"])
                done.append(re.sub(r"^https?://(www\.)?", "", st["url"]).split("/")[0])
            elif kind == "vpn":
                done.append(vpn_on(cfg).split(".")[0])
            elif kind == "wait":
                time.sleep(max(0, min(60, float(st.get("seconds", 2)))))
            elif kind == "click":
                import procs
                end = time.time() + float(st.get("wait", 15))
                ok = None
                while time.time() < end and not ok:
                    time.sleep(1.5)
                    wins = procs.find(last_win_name, last_target)[0] if last_target else []
                    win = wins[0] if wins else procs.foreground()
                    if win is not None:
                        ok = control.click_in(win, [st["text"]], min_score=0.85)
                if ok:
                    done.append(f"нажал «{ok}»")
            elif kind == "command" and depth < 2:
                text = st.get("text", "")
                intent = (timers.parse(text) or system.parse(text) or control.parse(text)
                          or commands.parse(text))
                if intent["action"] in ACTIONS:
                    continue
                if intent["action"].startswith("timer_"):
                    continue                        # таймеры ставятся только из главного окна
                reply, _ui = actions.run(intent, {})
                done.append(text)
                time.sleep(0.4)
        except Exception as e:  # noqa: BLE001
            done.append(f"ошибка: {e}")
    return done


def run(intent, cfg):
    a = intent["action"]
    vcfg = intent.get("vpn") or {}
    if a == "vpn":
        return vpn_on(vcfg)
    if a == "vpn_off":
        return vpn_off(vcfg)
    sc = intent["scenario"]
    if not sc.get("steps"):
        return (f"Сценарий «{sc['name']}» пока пустой. Добавьте, что запускать: профиль → "
                f"«Сценарии».")
    done = [d for d in run_steps(sc, vcfg) if d]
    return f"{sc['name']}: готово." + (f" {', '.join(done[:6])}." if done else "")
