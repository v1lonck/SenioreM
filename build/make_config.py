"""Перед сборкой: записывает config.json (версия и откуда брать обновления). Никаких паролей."""
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parent.parent
cfg = json.loads((root / "config.example.json").read_text(encoding="utf-8"))

# Пароли и ключи в программу НЕ вшиваются: всё, что лежит в .exe, может достать любой, кто его
# скачал. Поэтому почта-отправитель (SMTP) отключена, вход — по логину и паролю на этом компьютере.
cfg["smtp"] = {"host": "", "port": 465, "user": "", "password": "", "from_name": "SenioreM"}
cfg["email_verification"] = False
for leaked in ("SMTP_USER", "SMTP_PASSWORD"):
    if os.environ.get(leaked):
        print(f"::warning::Секрет {leaked} больше не используется и в программу не попадает — "
              f"удалите его в Settings → Secrets.")

cfg["version"] = os.environ.get("APP_VERSION", "").strip() or "0.0.0"
cfg["update_repo"] = os.environ.get("GITHUB_REPOSITORY", "").strip()
print(f"Версия {cfg['version']}, обновления из {cfg['update_repo'] or '—'}")

(root / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
