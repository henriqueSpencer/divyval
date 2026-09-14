import { json } from "../_lib/http.js";
import { issueToken, cookieHeader, safeEqual } from "../_lib/session.js";

// POST {password} → cookie de sessão (180 dias, renovado no uso). Sem APP_PASSWORD o app é aberto.
export async function onRequestPost({ request, env }) {
  const pw = env.APP_PASSWORD;
  if (!pw) return json({ ok: true, open: true });
  let body = {};
  try { body = await request.json(); } catch (_) {}
  if (!safeEqual(body.password, pw)) return json({ ok: false, error: "Senha incorreta" }, 401);
  const res = json({ ok: true });
  res.headers.set("Set-Cookie", cookieHeader(request, await issueToken(pw)));
  return res;
}
