// Sessão em cookie assinado (HMAC-SHA256, Web Crypto — sem npm).
// Token: "v1.<exp_ms>.<sig>", onde sig = HMAC(chave, "divyval-session|<exp_ms>").
// A chave deriva de APP_PASSWORD (SHA-256), então trocar a senha invalida toda sessão.
// O cookie é HttpOnly (JS não lê, ao contrário de token em localStorage) e renovado
// de forma deslizante pelo middleware — quem usa o app não volta a ver o login.
export const COOKIE = "dv_session";
export const SESSION_MS = 180 * 24 * 3600 * 1000; // 180 dias
const RENEW_BELOW_MS = SESSION_MS / 2;             // renova quando falta menos da metade
const enc = new TextEncoder();

const b64url = (buf) =>
  btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

let keyCache = null, keyFor = null;
async function hmacKey(secret) {
  if (keyCache && keyFor === secret) return keyCache;
  const raw = await crypto.subtle.digest("SHA-256", enc.encode(secret + "|divyval-session-key"));
  keyCache = await crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  keyFor = secret;
  return keyCache;
}

async function sign(secret, exp) {
  const key = await hmacKey(secret);
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode("divyval-session|" + exp)));
}

// Comparação em tempo constante (evita vazar por timing o quanto da senha bateu).
export function safeEqual(a, b) {
  a = String(a ?? ""); b = String(b ?? "");
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}

export async function issueToken(secret, ttl = SESSION_MS) {
  const exp = Date.now() + ttl;
  return `v1.${exp}.${await sign(secret, exp)}`;
}

// Devolve { exp } se o token for válido e não expirado; senão null.
export async function verifyToken(secret, token) {
  if (!token) return null;
  const [v, expS, sig] = token.split(".");
  const exp = Number(expS);
  if (v !== "v1" || !isFinite(exp) || !sig || exp < Date.now()) return null;
  if (!safeEqual(sig, await sign(secret, exp))) return null;
  return { exp };
}

export const needsRenew = (exp) => exp - Date.now() < RENEW_BELOW_MS;

export function readCookie(request, name = COOKIE) {
  const raw = request.headers.get("cookie") || "";
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === name) return decodeURIComponent(part.slice(i + 1).trim());
  }
  return null;
}

// `Secure` só em https (no `wrangler pages dev` é http e o Safari descartaria o cookie).
export function cookieHeader(request, token, maxAgeSec = SESSION_MS / 1000) {
  const secure = new URL(request.url).protocol === "https:" ? "; Secure" : "";
  return `${COOKIE}=${token}; Path=/; Max-Age=${Math.floor(maxAgeSec)}; HttpOnly; SameSite=Lax${secure}`;
}
export const clearCookieHeader = (request) => cookieHeader(request, "", 0);
