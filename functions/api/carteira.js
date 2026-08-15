import { json } from "../_lib/http.js";
import { sel } from "../_lib/db.js";

// GET /api/carteira — posições da carteira (ticker, quantidade, preço médio).
// O front cruza cada ticker com o objeto de ação já carregado (/api/stocks) p/ preço, justo, TIR etc.
export async function onRequestGet(context) {
  const rows = await sel(
    context.env,
    "carteira?select=ticker,quantidade,preco_medio,updated_at&order=ticker.asc"
  );
  return json(rows);
}
