import { json } from "../_lib/http.js";
import { getMacro } from "../_lib/macro.js";

// GET /api/macro -> Selic e IPCA-12m do Banco Central (cache 12h no edge).
// Degrada gracioso: se o BCB cair, devolve nulos (o front cai no último conhecido).
export async function onRequestGet(context) {
  try {
    return json(await getMacro(context));
  } catch (_) {
    return json({ selic: null, ipca12m: null, fonte: "BCB" });
  }
}
