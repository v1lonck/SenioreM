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

    # ---------- вход / выход ----------
    def login(self, email: str, password: str) -> str:
        email = self._check_email(email)
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
        msg = EmailMessage()
        msg["Subject"] = f"{code} — код подтверждения SenioreM"
        msg["From"] = formataddr((self.from_name, self.user))
        msg["To"] = to
        msg.set_content(
            f"Ваш код подтверждения: {code}\n\n"
            "Код действует 10 минут. Если вы не регистрировались в SenioreM — "
            "просто удалите это письмо."
        )
        spaced = "&nbsp;".join(code)
        msg.add_alternative(f"""\
<!doctype html><html><body style="margin:0;background:#f4f2ee;padding:40px 0;
font-family:'Segoe UI',Arial,sans-serif;color:#1a1918">
<table role="presentation" width="100%"><tr><td align="center">
<table role="presentation" width="440" style="background:#ffffff;border-radius:14px;padding:40px">
<tr><td style="font-size:15px;font-weight:600;letter-spacing:.5px">SenioreM</td></tr>
<tr><td style="padding-top:28px;font-size:22px;font-weight:300">Код подтверждения</td></tr>
<tr><td style="padding-top:8px;font-size:14px;color:#77726b">Введите его в окне программы.</td></tr>
<tr><td style="padding:28px 0;font-size:38px;font-weight:600;letter-spacing:6px">{spaced}</td></tr>
<tr><td style="font-size:13px;color:#77726b;border-top:1px solid #ece9e4;padding-top:20px">
Код действует 10 минут. Если вы не регистрировались — просто удалите письмо.</td></tr>
</table></td></tr></table></body></html>""", subtype="html")

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
