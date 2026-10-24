"""Перед сборкой: записывает config.json с почтой-отправителем из секретов GitHub.
Если секретов нет — программа соберётся в тестовом режиме (код показывается на экране)."""
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parent.parent
cfg = json.loads((root / "config.example.json").read_text(encoding="utf-8"))

user = os.environ.get("SMTP_USER", "").strip()
password = os.environ.get("SMTP_PASSWORD", "").strip()
if user and password:
    domain = user.split("@")[-1].lower()
    known = {
        "gmail.com": "smtp.gmail.com", "googlemail.com": "smtp.gmail.com",
        "yandex.ru": "smtp.yandex.ru", "ya.ru": "smtp.yandex.ru", "yandex.com": "smtp.yandex.ru",
        "mail.ru": "smtp.mail.ru", "bk.ru": "smtp.mail.ru", "inbox.ru": "smtp.mail.ru",
        "list.ru": "smtp.mail.ru", "internet.ru": "smtp.mail.ru",
        "rambler.ru": "smtp.rambler.ru",
    }
    cfg["smtp"].update(
        host=os.environ.get("SMTP_HOST", "").strip() or known.get(domain, f"smtp.{domain}"),
        port=int(os.environ.get("SMTP_PORT", "").strip() or 465),
        user=user,
        password=password,
    )
    print(f"Почта для кодов: {user} через {cfg['smtp']['host']}:{cfg['smtp']['port']}")
else:
    print("Секреты SMTP_USER / SMTP_PASSWORD не заданы — сборка в тестовом режиме.")

cfg["version"] = os.environ.get("APP_VERSION", "").strip() or "0.0.0"
cfg["update_repo"] = os.environ.get("GITHUB_REPOSITORY", "").strip()
print(f"Версия {cfg['version']}, обновления из {cfg['update_repo'] or '—'}")

(root / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
