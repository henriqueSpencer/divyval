// Basic Auth (paridade com o _auth de app.py). Roda em TODAS as rotas — inclusive o HTML
// estático. Sem APP_PASSWORD o app fica aberto (igual ao dev local de hoje).
function unauthorized() {
  return new Response("Autenticação necessária", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="DIVYVAL"' },
  });
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const pw = env.APP_PASSWORD;
  if (pw) {
    const hdr = request.headers.get("authorization") || "";
    let ok = false;
    if (hdr.startsWith("Basic ")) {
      try {
        const dec = atob(hdr.slice(6));
        const i = dec.indexOf(":");
        ok = (i >= 0 ? dec.slice(i + 1) : dec) === pw; // usuário ignorado, só a senha
      } catch (_) {
        ok = false;
      }
    }
    if (!ok) return unauthorized();
  }
  const res = await next();
  // HTML não deve ser servido "stale" após um deploy (paridade com app.py).
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("text/html")) {
    const r = new Response(res.body, res);
    r.headers.set("Cache-Control", "no-cache");
    return r;
  }
  return res;
}
