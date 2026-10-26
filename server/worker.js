// Облачный сервер SenioreM — Cloudflare Worker (бесплатно: 100 000 запросов в день).
// Что делает:
//   /v1/chat/completions   — ответы ИИ: умная платная модель (DeepSeek через посредника,
//                            ключ хранится только здесь), а если её нет или кончились деньги —
//                            бесплатная модель Cloudflare Workers AI.
//   /v1/audio/transcriptions — точное распознавание речи (Whisper в Cloudflare, бесплатно).
//   /v1/images/generations   — картинки по описанию (FLUX в Cloudflare, бесплатно).
//
// Настройка Worker → Settings:
//   Bindings → Workers AI, имя переменной: AI            (обязательно)
//   Variables and Secrets:
//     LLM_KEY   (Secret) — ключ посредника (VseGPT, ProxyAPI…) или DeepSeek/OpenRouter/Groq
//     LLM_URL   (Text)   — адрес …/chat/completions этого сервиса (см. его документацию)
//     LLM_MODEL (Text, необязательно) — модель; если не указать, сервер сам выберет
//               быструю (flash) для обычных вопросов и умную (pro) для «расскажи подробно»
//     APP_TOKEN (Text, необязательно) — пароль программы, по умолчанию "seniorem-app"
//     USER_DAY_TOKENS   (Text, необязательно) — лимит токенов на одного пользователя в день (150000)
//     USER_MONTH_TOKENS (Text, необязательно) — лимит в месяц (3000000). Программа узнаёт их сама.

const FREE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";
const FREE_MODEL_LIGHT = "@cf/meta/llama-3.1-8b-instruct-fast";
const WHISPER = "@cf/openai/whisper-large-v3-turbo";

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

// ответ бесплатной модели в формате OpenAI (обычный или «потоком» одной порцией)
function openaiReply(text, stream) {
  if (!stream) {
    return json({ choices: [{ index: 0, message: { role: "assistant", content: text } }] });
  }
  const chunk = JSON.stringify({ choices: [{ index: 0, delta: { content: text } }] });
  return new Response(`data: ${chunk}\n\ndata: [DONE]\n\n`, {
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
  });
}

// модель не указана — берём из списка сервиса: быстрая (flash) обычно, умная (pro) для длинных ответов
let MODELS_CACHE = null;
async function pickModel(env, smart) {
  if (env.LLM_MODEL) return env.LLM_MODEL;
  if (!MODELS_CACHE) {
    try {
      const r = await fetch(env.LLM_URL.replace(/\/chat\/completions$/, "/models"),
                            { headers: { Authorization: `Bearer ${env.LLM_KEY}` } });
      MODELS_CACHE = ((await r.json()).data || []).map((m) => m.id).filter(Boolean);
    } catch (e) { MODELS_CACHE = []; }
  }
  const words = smart ? ["v4-pro", "pro", "reasoner", "v4", "chat"] : ["v4-flash", "flash", "chat", "mini", "v4"];
  for (const w of words) {
    const hit = MODELS_CACHE.find((id) => id.toLowerCase().includes(w) && !/embed|whisper|tts/i.test(id));
    if (hit) return hit;
  }
  return MODELS_CACHE[0] || "deepseek-chat";
}

async function freeAnswer(env, out, light) {
  const r = await env.AI.run(light ? FREE_MODEL_LIGHT : FREE_MODEL, {
    messages: out.messages, max_tokens: out.max_tokens, temperature: out.temperature,
  });
  return (r && (r.response || r.result?.response)) || "";
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return json({
        ok: true, paid: !!env.LLM_KEY, ai: !!env.AI,
        limits: { day: Number(env.USER_DAY_TOKENS || 150000), month: Number(env.USER_MONTH_TOKENS || 3000000) },
      });
    }
    if (request.method !== "POST") return new Response("not found", { status: 404 });
    const token = env.APP_TOKEN || "seniorem-app";
    if ((request.headers.get("Authorization") || "") !== `Bearer ${token}`) {
      return new Response("forbidden", { status: 403 });
    }
    const raw = await request.text();
    if (raw.length > 1500000) return new Response("too large", { status: 413 });
    let body;
    try { body = JSON.parse(raw); } catch { return new Response("bad json", { status: 400 }); }

    // ---- распознавание речи: {audio: base64 WAV, prompt?}
    if (url.pathname.endsWith("/audio/transcriptions")) {
      if (!env.AI) return json({ error: "no AI binding" }, 503);
      try {
        const r = await env.AI.run(WHISPER, {
          audio: body.audio, language: "ru", initial_prompt: (body.prompt || "").slice(0, 400),
        });
        return json({ text: (r && r.text) || "" });
      } catch (e) {
        return json({ error: String(e) }, 503);
      }
    }

    // ---- картинка по описанию: {prompt} -> {image: base64}
    if (url.pathname.endsWith("/images/generations")) {
      if (!env.AI) return json({ error: "no AI binding" }, 503);
      try {
        const r = await env.AI.run("@cf/black-forest-labs/flux-1-schnell",
                                   { prompt: String(body.prompt || "").slice(0, 1500), steps: 6 });
        return json({ image: r.image });
      } catch (e) {
        return json({ error: String(e) }, 503);
      }
    }

    if (!url.pathname.endsWith("/chat/completions")) return new Response("not found", { status: 404 });
    const out = {
      messages: (body.messages || []).slice(-20),
      temperature: Math.min(Number(body.temperature ?? 0.5), 1.2),
      max_tokens: Math.min(Number(body.max_tokens ?? 300), 1500),
      stream: !!body.stream,
    };
    // программа подсказывает, какая модель нужна: быстрая (flash) или умная (pro)
    const smart = body.model_hint ? body.model_hint === "pro" : out.max_tokens > 300;
    // 1) умная платная модель (если настроена)
    if (env.LLM_KEY && env.LLM_URL) {
      try {
        const r = await fetch(env.LLM_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.LLM_KEY}` },
          body: JSON.stringify({ ...out, model: await pickModel(env, smart) }),
        });
        if (r.ok) {
          return new Response(r.body, {
            headers: { "Content-Type": r.headers.get("Content-Type") || "application/json" },
          });
        }
      } catch (e) { /* сервис недоступен — дальше бесплатная модель */ }
    }
    // 2) бесплатная модель Cloudflare (при лимите — облегчённая)
    if (!env.AI) return json({ error: "no model configured" }, 503);
    try {
      return openaiReply(await freeAnswer(env, out, false), out.stream);
    } catch (e) {
      try {
        return openaiReply(await freeAnswer(env, out, true), out.stream);
      } catch (e2) {
        return json({ error: String(e2) }, 503);
      }
    }
  },
};
