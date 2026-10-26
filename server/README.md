# Облачный ИИ для SenioreM (бесплатно)

Программа отправляет вопросы на ваш маленький сервер в Cloudflare (Worker), а он — в Groq.
Ключ Groq хранится только на сервере, в программу он не попадает.

## 1. Ключ Groq
1. Зарегистрируйтесь на https://console.groq.com (можно через Google).
2. API Keys → Create API Key → скопируйте ключ (начинается с `gsk_`).

## 2. Worker в Cloudflare
1. Зарегистрируйтесь на https://dash.cloudflare.com.
2. Workers & Pages → Create → Create Worker → имя, например `seniorem-ai` → Deploy.
3. Edit code → удалите всё и вставьте содержимое `server/worker.js` → Deploy.
4. Settings → Variables and Secrets → Add → тип **Secret**, имя `GROQ_KEY`, значение — ключ Groq → Deploy.
5. Адрес Worker вида `https://seniorem-ai.ИМЯ.workers.dev` — проверьте: `…/health` должен ответить `ok`.

## 3. Подключить к программе
GitHub → репозиторий → Settings → Secrets and variables → Actions → вкладка **Variables** →
New repository variable: имя `AI_PROXY_URL`, значение — адрес Worker. Следующая версия программы
сама начнёт пользоваться облачным ИИ (в профиле → «ИИ-собеседник» появится «Облачный»).
