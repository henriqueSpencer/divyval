import { json } from "../_lib/http.js";
import { clearCookieHeader } from "../_lib/session.js";

export async function onRequestPost({ request }) {
  const res = json({ ok: true });
  res.headers.set("Set-Cookie", clearCookieHeader(request));
  return res;
}
