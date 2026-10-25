"""Аккаунты (хранятся на этом компьютере) и отправка кода на почту."""
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

LOGIN_RE = re.compile(r"^[a-zа-я0-9._-]{3,24}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
CODE_TTL = 10 * 60          # код действует 10 минут
RESEND_COOLDOWN = 60        # повторная отправка не чаще раза в минуту
MAX_ATTEMPTS = 5
PBKDF2_ROUNDS = 200_000


class AuthError(Exception):
    pass


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS
    ).hex()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class AuthStore:
    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.users_path = self.dir / "users.json"
        self.session_path = self.dir / "session.json"
        self.users = self._load(self.users_path, {})
        self.pending = {}

    # ---------- файлы ----------
    @staticmethod
    def _load(path: Path, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    @staticmethod
    def _save(path: Path, data):
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    # ---------- проверки ----------
    @staticmethod
    def normalize_email(email: str) -> str:
        return (email or "").strip().lower()

    def _check_email(self, email: str) -> str:
        email = self.normalize_email(email)
        if not email:
            raise AuthError("Введите почту.")
        if not EMAIL_RE.match(email):
            raise AuthError("Почта выглядит неверно.")
        return email

    # ---------- регистрация ----------
    def start_registration(self, email: str, password: str, password2: str) -> str:
        email = self._check_email(email)
        if email in self.users:
            raise AuthError("Аккаунт с этой почтой уже есть — нажмите «Войти».")
        if len(password) < 6:
            raise AuthError("Пароль — минимум 6 символов.")
        if password != password2:
            raise AuthError("Пароли не совпадают.")
        salt = secrets.token_hex(16)
        code = f"{secrets.randbelow(10**6):06d}"
        self.pending[email] = {
            "salt": salt,
            "hash": _hash_password(password, salt),
            "code": _hash_code(code),
            "expires": time.time() + CODE_TTL,
            "attempts": 0,
            "sent": time.time(),
        }
        return code

    def resend_wait(self, email: str) -> int:
        p = self.pending.get(self.normalize_email(email))
        if not p:
            return 0
        return max(0, int(p["sent"] + RESEND_COOLDOWN - time.time() + 0.999))

    def new_code(self, email: str) -> str:
        email = self.normalize_email(email)
        p = self.pending.get(email)
        if not p:
            raise AuthError("Начните регистрацию заново.")
        wait = self.resend_wait(email)
        if wait:
            raise AuthError(f"Повторно можно через {wait} с.")
        code = f"{secrets.randbelow(10**6):06d}"
        p.update(code=_hash_code(code), expires=time.time() + CODE_TTL,
                 attempts=0, sent=time.time())
        return code

    def verify(self, email: str, code: str) -> str:
        email = self.normalize_email(email)
        p = self.pending.get(email)
        if not p:
            raise AuthError("Начните регистрацию заново.")
        code = (code or "").strip()
        if len(code) != 6 or not code.isdigit():
            raise AuthError("Введите 6 цифр из письма.")
        if time.time() > p["expires"]:
            raise AuthError("Код устарел — отправьте новый.")
        if p["attempts"] >= MAX_ATTEMPTS:
            raise AuthError("Слишком много попыток — отправьте новый код.")
        if not hmac.compare_digest(p["code"], _hash_code(code)):
            p["attempts"] += 1
            left = MAX_ATTEMPTS - p["attempts"]
            raise AuthError(f"Неверный код. Осталось попыток: {left}." if left
                            else "Неверный код. Отправьте новый.")
        self.users[email] = {
            "salt": p["salt"],
            "hash": p["hash"],
            "verified": True,
            "created": int(time.time()),
        }
        self._save(self.users_path, self.users)
        del self.pending[email]
        self.set_session(email)
        return email

    # ---------- регистрация по логину (без почты) ----------
    def _check_login(self, name: str) -> str:
        name = self.normalize_email(name).replace("ё", "е")
        if not name:
            raise AuthError("Введите логин.")
        if "@" in name:
            return self._check_email(name)
        if len(name) < 3:
            raise AuthError("Логин — минимум 3 символа.")
        if not LOGIN_RE.match(name):
            raise AuthError("В логине можно использовать буквы, цифры, точку, дефис и _.")
        return name

    def register(self, name: str, password: str, password2: str) -> str:
        name = self._check_login(name)
        if name in self.users:
            raise AuthError("Такой логин уже занят — выберите другой или нажмите «Войти».")
        if len(password) < 6:
            raise AuthError("Пароль — минимум 6 символов.")
        if password != password2:
            raise AuthError("Пароли не совпадают.")
        salt = secrets.token_hex(16)
        self.users[name] = {"salt": salt, "hash": _hash_password(password, salt),
                            "verified": False, "created": int(time.time())}
        self._save(self.users_path, self.users)
        self.set_session(name)
        return name

    # ---------- вход / выход ----------
    def login(self, email: str, password: str) -> str:
        email = self._check_login(email)
        if not password:
            raise AuthError("Введите пароль.")
        user = self.users.get(email)
        if not user:
            raise AuthError("Аккаунт не найден — зарегистрируйтесь.")
        if not hmac.compare_digest(user["hash"], _hash_password(password, user["salt"])):
            raise AuthError("Неверный пароль.")
        self.set_session(email)
        return email

    def change_password(self, email: str, old: str, new: str, new2: str):
        user = self.users.get(self.normalize_email(email))
        if not user:
            raise AuthError("Аккаунт не найден.")
        if not hmac.compare_digest(user["hash"], _hash_password(old, user["salt"])):
            raise AuthError("Текущий пароль указан неверно.")
        if len(new) < 6:
            raise AuthError("Новый пароль — минимум 6 символов.")
        if new != new2:
            raise AuthError("Новые пароли не совпадают.")
        salt = secrets.token_hex(16)
        user.update(salt=salt, hash=_hash_password(new, salt))
        self._save(self.users_path, self.users)

    def rename(self, old: str, new: str, password: str) -> str:
        """Сменить логин (пароль подтверждает, что это вы). Настройки переносятся."""
        old = self.normalize_email(old)
        user = self.users.get(old)
        if not user:
            raise AuthError("Аккаунт не найден.")
        if not hmac.compare_digest(user["hash"], _hash_password(password, user["salt"])):
            raise AuthError("Пароль указан неверно.")
        new = self._check_login(new)
        if new == old:
            return old
        if new in self.users:
            raise AuthError("Такой логин уже занят.")
        self.users[new] = self.users.pop(old)
        self._save(self.users_path, self.users)
        # профиль (настройки, история, сценарии) — под новым именем
        import hashlib
        prof = self.dir / "profiles"
        a = prof / (hashlib.sha1(old.encode()).hexdigest()[:16] + ".json")
        b = prof / (hashlib.sha1(new.encode()).hexdigest()[:16] + ".json")
        try:
            if a.exists():
                os.replace(a, b)
        except OSError:
            pass
        self.set_session(new)
        return new

    def created(self, email: str) -> int:
        return int((self.users.get(self.normalize_email(email)) or {}).get("created", 0))

    def set_session(self, email: str):
        self._save(self.session_path, {"email": email, "since": int(time.time())})

    def session_email(self):
        s = self._load(self.session_path, {})
        email = s.get("email")
        return email if email in self.users else None

    def logout(self):
        try:
            self.session_path.unlink()
        except OSError:
            pass

    @property
    def has_users(self) -> bool:
        return bool(self.users)


def _code_html(code: str, logo_cid: str) -> str:
    cells = "".join(
        '<td style="width:52px;height:64px;background:#F2F5FF;border:1px solid #DCE4FF;'
        'border-radius:12px;text-align:center;vertical-align:middle;font-family:\'Segoe UI\','
        'Arial,sans-serif;font-size:30px;font-weight:700;color:#0B1A4A">' + d + "</td>"
        '<td style="width:8px"></td>' for d in code)
    logo = (f'<img src="cid:{logo_cid}" width="56" height="56" alt="S" '
            f'style="display:block;border:0;border-radius:14px">') if logo_cid else (
        '<div style="width:56px;height:56px;border-radius:14px;background:#2E6BFF;color:#fff;'
        'font:700 30px Arial;line-height:56px;text-align:center">S</div>')
    return f"""\
<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Код подтверждения SenioreM</title></head>
<body style="margin:0;padding:0;background:#EEF1F7">
<div style="display:none;max-height:0;overflow:hidden;color:transparent">
Ваш код для входа в SenioreM: {code}. Он действует 10 минут.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF1F7">
<tr><td align="center" style="padding:40px 16px">
<table role="presentation" width="480" cellpadding="0" cellspacing="0"
 style="max-width:480px;width:100%;background:#FFFFFF;border-radius:20px;overflow:hidden;
 box-shadow:0 10px 40px rgba(20,40,110,0.10)">
  <tr><td style="background:#0B1230;background-image:linear-gradient(135deg,#0E1E5A 0%,#2E6BFF 100%);
   padding:36px 40px 32px 40px">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle">{logo}</td>
      <td style="padding-left:16px;vertical-align:middle;font-family:'Segoe UI',Arial,sans-serif">
        <div style="font-size:22px;font-weight:600;color:#FFFFFF;letter-spacing:.3px">SenioreM</div>
        <div style="font-size:12px;color:#BFD0FF;letter-spacing:1.6px;text-transform:uppercase;
         padding-top:2px">голосовой помощник</div>
      </td></tr></table>
  </td></tr>
  <tr><td style="padding:38px 40px 8px 40px;font-family:'Segoe UI',Arial,sans-serif;color:#141A2E">
    <div style="font-size:26px;font-weight:300;line-height:1.3">Подтвердите почту</div>
    <div style="font-size:15px;line-height:1.6;color:#5A6378;padding-top:12px">
      Здравствуйте! Вы создаёте аккаунт в SenioreM. Чтобы закончить регистрацию,
      введите этот код в окне программы:</div>
  </td></tr>
  <tr><td align="center" style="padding:26px 40px 10px 40px">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>{cells}</tr></table>
  </td></tr>
  <tr><td align="center" style="padding:6px 40px 30px 40px;font-family:'Segoe UI',Arial,sans-serif;
   font-size:13px;color:#8A93A6">Код действует 10 минут</td></tr>
  <tr><td style="padding:0 40px"><div style="height:1px;background:#E8ECF4"></div></td></tr>
  <tr><td style="padding:26px 40px 34px 40px;font-family:'Segoe UI',Arial,sans-serif;font-size:14px;
   line-height:1.6;color:#5A6378">
    После входа просто скажите <b style="color:#141A2E">«Сеньор»</b> — и он сделает остальное:
    поменяет громкость, откроет сайт или программу, найдёт нужное в интернете.
    <div style="padding-top:18px;font-size:12px;color:#9AA2B4">
      Если вы не регистрировались в SenioreM, просто удалите это письмо — без кода
      никто не сможет войти с вашей почтой.</div>
  </td></tr>
</table>
<div style="font-family:'Segoe UI',Arial,sans-serif;font-size:12px;color:#9AA2B4;padding-top:18px">
  © SenioreM · письмо отправлено автоматически, отвечать на него не нужно</div>
</td></tr></table>
</body></html>"""


def build_code_email(from_name: str, sender: str, to: str, code: str) -> EmailMessage:
    """Красивое письмо с кодом: синяя шапка с логотипом S, код в отдельных ячейках."""
    from email.utils import make_msgid
    msg = EmailMessage()
    msg["Subject"] = f"{code} — ваш код для SenioreM"
    msg["From"] = formataddr((from_name, sender))
    msg["To"] = to
    msg.set_content(
        "Здравствуйте!\n\n"
        f"Ваш код подтверждения SenioreM: {code}\n"
        "Введите его в окне программы. Код действует 10 минут.\n\n"
        "Если вы не регистрировались в SenioreM, просто удалите это письмо.\n"
    )
    logo_bytes = None
    try:
        import config
        p = config.resource_path("assets/icon_mail.png")
        if not p.exists():
            p = config.resource_path("assets/icon.png")
        logo_bytes = p.read_bytes()
    except Exception:  # noqa: BLE001
        pass
    cid = make_msgid(domain="seniorem.app")[1:-1] if logo_bytes else ""
    msg.add_alternative(_code_html(code, cid), subtype="html")
    if logo_bytes:
        msg.get_payload()[1].add_related(logo_bytes, maintype="image", subtype="png",
                                         cid=f"<{cid}>", filename="seniorem.png")
    return msg


class Mailer:
    def __init__(self, cfg: dict):
        smtp = cfg.get("smtp") or {}
        self.host = (smtp.get("host") or "").strip()
        self.port = int(smtp.get("port") or 465)
        self.user = (smtp.get("user") or "").strip()
        self.password = smtp.get("password") or ""
        self.from_name = smtp.get("from_name") or "SenioreM"

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password)

    def send_code(self, to: str, code: str):
        msg = build_code_email(self.from_name, self.user, to, code)
        ctx = ssl.create_default_context()
        try:
            if self.port == 465:
                with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=20) as s:
                    s.login(self.user, self.password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=20) as s:
                    s.ehlo()
                    s.starttls(context=ctx)
                    s.ehlo()
                    s.login(self.user, self.password)
                    s.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            raise AuthError("Почтовый сервер не принял логин или пароль отправителя "
                            "(проверьте пароль приложения в config.json).")
        except smtplib.SMTPRecipientsRefused:
            raise AuthError("Такой почты не существует.")
        except (smtplib.SMTPException, OSError) as e:
            raise AuthError(f"Не удалось отправить письмо: {e}")
