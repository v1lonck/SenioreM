// Облачный ИИ для SenioreM — Cloudflare Worker (бесплатно: 100 000 запросов в день).
// Программа шлёт сюда вопросы, а Worker передаёт их в Groq (бесплатный ключ хранится
// только здесь, в «секретах» Worker, — в программу он не попадает).
//
// Настройка: Settings → Variables and Secrets:
//   GROQ_KEY   (Secret) — ключ с https://console.groq.com/keys
//   APP_TOKEN  (Text, необязательно) — пароль программы, по умолчанию "seniorem-app"

const MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]; // умная, при лимите — быстрая

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return new Response("ok");
    }
    if (request.method !== "POST" || !url.pathname.endsWith("/chat/completions")) {
      return new Response("not found", { status: 404 });
    }
    const token = env.APP_TOKEN || "seniorem-app";
    if ((request.headers.get("Authorization") || "") !== `Bearer ${token}`) {
      return new Response("forbidden", { status: 403 });
    }
    const raw = await request.text();
    if (raw.length > 40000) return new Response("too large", { status: 413 });
    let body;
    try { body = JSON.parse(raw); } catch { return new Response("bad json", { status: 400 }); }
    const out = {
      messages: (body.messages || []).slice(-20),
      temperature: Math.min(Number(body.temperature ?? 0.5), 1.2),
      max_tokens: Math.min(Number(body.max_tokens ?? 300), 600),
      stream: !!body.stream,
    };
    for (const model of MODELS) {
      const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.GROQ_KEY}` },
        body: JSON.stringify({ ...out, model }),
      });
      if (r.status === 429 && model !== MODELS[MODELS.length - 1]) continue; // лимит — пробуем быструю
      return new Response(r.body, {
        status: r.status,
        headers: { "Content-Type": r.headers.get("Content-Type") || "application/json" },
      });
    }
    return new Response("busy", { status: 503 });
  },
};
