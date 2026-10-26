// Облачный сервер SenioreM — Cloudflare Worker (бесплатно: 100 000 запросов в день).
// Что делает:
//   /v1/chat/completions   — ответы ИИ: умная платная модель (DeepSeek через посредника,
//                            ключ хранится только здесь), а если её нет или кончились деньги —
//                            бесплатная модель Cloudflare Workers AI.
//   /v1/audio/transcriptions — точное распознавание речи (Whisper в Cloudflare, бесплатно).
//
// Настройка Worker → Settings:
//   Bindings → Workers AI, имя переменной: AI            (обязательно)
//   Variables and Secrets:
//     LLM_KEY   (Secret) — ключ посредника (VseGPT, ProxyAPI…) или DeepSeek/OpenRouter/Groq
//     LLM_URL   (Text)   — адрес …/chat/completions этого сервиса (см. его документацию)
//     LLM_MODEL (Text)   — модель, например deepseek-chat (как называет её сервис)
//     APP_TOKEN (Text, необязательно) — пароль программы, по умолчанию "seniorem-app"

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
      return json({ ok: true, paid: !!env.LLM_KEY, ai: !!env.AI });
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

    if (!url.pathname.endsWith("/chat/completions")) return new Response("not found", { status: 404 });
    const out = {
      messages: (body.messages || []).slice(-20),
      temperature: Math.min(Number(body.temperature ?? 0.5), 1.2),
      max_tokens: Math.min(Number(body.max_tokens ?? 300), 700),
      stream: !!body.stream,
    };
    // 1) умная платная модель (если настроена)
    if (env.LLM_KEY && env.LLM_URL) {
      try {
        const r = await fetch(env.LLM_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.LLM_KEY}` },
          body: JSON.stringify({ ...out, model: env.LLM_MODEL || "deepseek-chat" }),
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
