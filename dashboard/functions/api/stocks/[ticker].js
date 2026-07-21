import { json } from "../../_lib/http.js";
import { patch, del, ignoreDup } from "../../_lib/db.js";

const EDIT = ["nome", "setor", "subsetor", "segmento", "perfil", "tamanho", "gov", "ctrl", "modelo", "tags"];

// PATCH /api/stocks/{ticker} — atualiza só classificação/identidade (porta de editar_acao).
export async function onRequestPatch(context) {
  const tk = context.params.ticker.toUpperCase();
  const s = await context.request.json();
  const body = {};
  for (const f of EDIT)
    if (f in s) body[f] = f === "tags" ? JSON.stringify(s[f] || []) : s[f] || "";
  if (!Object.keys(body).length)
    return json({ ok: false, erro: "nada para atualizar" }, 400);
  const upd = await patch(context.env, "stocks", `ticker=eq.${tk}`, body);
  if (!upd.length) return json({ ok: false, erro: "ticker não encontrado" }, 404);
  return json({ ok: true });
}

// DELETE /api/stocks/{ticker} — apaga a ação e veta o re-semear (porta de remover_acao).
export async function onRequestDelete(context) {
  const tk = context.params.ticker.toUpperCase();
  await ignoreDup(context.env, "removed", [{ ticker: tk }]);
  for (const t of ["stocks", "watchlist", "premissa_atual", "premissa_hist"])
    await del(context.env, t, `ticker=eq.${tk}`);
  return json({ ok: true });
}
