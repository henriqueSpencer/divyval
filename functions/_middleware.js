// Autenticação em TODAS as rotas — inclusive o HTML estático. Sem APP_PASSWORD o app fica
// aberto (igual ao dev local). Duas formas de entrar:
//   1. cookie de sessão assinado (`dv_session`, HttpOnly, 180 dias, renovação deslizante) —
//      emitido por /api/login a partir de /login.html. É o caminho normal do navegador.
//   2. `Authorization: Basic` (compatibilidade com scripts/curl).
// Sem credencial: /api/* recebe 401 JSON (sem WWW-Authenticate, p/ o browser NÃO abrir o
// diálogo nativo — era isso que parecia "pedir para relogar"); páginas vão p/ /login.
import { COOKIE, readCookie, verifyToken, needsRenew, issueToken, cookieHeader, safeEqual } from "./_lib/session.js";

// O Pages faz 308 de /login.html → /login (clean URLs): as duas grafias precisam ser públicas.
const PUBLIC = new Set(["/login", "/login.html", "/api/login", "/favicon.svg", "/favicon-32.png", "/apple-touch-icon.png"]);

function basicOk(request, pw) {
  const hdr = request.headers.get("authorization") || "";
  if (!hdr.startsWith("Basic ")) return false;
  try {
    const dec = atob(hdr.slice(6));
    const i = dec.indexOf(":");
    return safeEqual(i >= 0 ? dec.slice(i + 1) : dec, pw); // usuário ignorado, só a senha
  } catch (_) {
    return false;
  }
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const pw = env.APP_PASSWORD;
  const url = new URL(request.url);
  let renewCookie = null;

  const isLogin = url.pathname === "/login" || url.pathname === "/login.html";
  if (pw && isLogin && await verifyToken(pw, readCookie(request, COOKIE))) {
    return Response.redirect(`${url.origin}/`, 303); // já logado: pula o login
  }
  if (pw && !PUBLIC.has(url.pathname)) {
    const sess = await verifyToken(pw, readCookie(request, COOKIE));
    if (sess) {
      if (needsRenew(sess.exp)) renewCookie = cookieHeader(request, await issueToken(pw));
    } else if (!basicOk(request, pw)) {
      if (url.pathname.startsWith("/api/")) {
        return new Response(JSON.stringify({ error: "unauthorized" }), {
          status: 401, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
        });
      }
      return Response.redirect(`${url.origin}/login`, 303);
    }
  }

  const res = await next();
  const ct = res.headers.get("content-type") || "";
  const isHtml = ct.includes("text/html");
  if (!isHtml && !renewCookie) return res;
  const r = new Response(res.body, res);
  // HTML não deve ser servido "stale" após um deploy (paridade com app.py).
  if (isHtml) r.headers.set("Cache-Control", "no-cache");
  if (renewCookie) r.headers.append("Set-Cookie", renewCookie);
  return r;
}
