// Videogram: películas de dominio público de archive.org.
const BASE = "https://archive.org";

// archive.org responde con error si la búsqueda trae símbolos raros u operadores sueltos.
function clean(text) {
  return String(text || "")
    .replace(/[^\p{L}\p{N}' ]+/gu, " ")
    .split(/\s+/)
    .filter((w) => w && !/^(AND|OR|NOT)$/i.test(w))
    .join(" ")
    .trim();
}

export async function search(query) {
  await null; // primero await, luego validar
  const q = clean(query && query.q);
  if (q.length < 2) return [];

  const lucene = "title:(" + q + ") AND mediatype:(movies)";
  const url =
    BASE +
    "/advancedsearch.php?q=" + encodeURIComponent(lucene) +
    "&fl%5B%5D=identifier&fl%5B%5D=title&fl%5B%5D=year" +
    "&sort%5B%5D=downloads+desc&rows=40&output=json";

  const r = await kino.fetch(url);
  if (!r.ok) throw kino.error("unavailable", "archive.org respondió " + r.status);

  const body = r.json();
  const docs = (body && body.response && body.response.docs) || [];
  const seen = {};
  const out = [];
  for (const d of docs) {
    const id = String(d.identifier || "");
    if (!/^[A-Za-z0-9._~-]{1,128}$/.test(id) || seen[id]) continue;
    seen[id] = true;
    const item = {
      id,
      ref: id,
      title: String(Array.isArray(d.title) ? d.title[0] : d.title || id).slice(0, 200),
      kind: "movie",
      poster: BASE + "/services/img/" + encodeURIComponent(id),
    };
    const year = parseInt(Array.isArray(d.year) ? d.year[0] : d.year, 10);
    if (year > 1800 && year < 2100) item.year = year;
    out.push(item);
  }
  return out;
}

export async function resolve(ref) {
  await null;
  const id = String(ref || "");
  if (!/^[A-Za-z0-9._~-]{1,128}$/.test(id)) throw kino.error("not_found", "id no válido");

  const r = await kino.fetch(BASE + "/metadata/" + encodeURIComponent(id));
  if (!r.ok) throw kino.error("not_found", "archive.org respondió " + r.status);

  const files = (r.json().files || []).filter((f) => /\.(mp4|webm)$/i.test(f.name || ""));
  if (!files.length) throw kino.error("not_found", "sin archivo de video");

  // Prefiere mp4 y, entre ellos, el más grande (mejor calidad).
  files.sort((a, b) => {
    const am = /\.mp4$/i.test(a.name) ? 1 : 0;
    const bm = /\.mp4$/i.test(b.name) ? 1 : 0;
    if (am !== bm) return bm - am;
    return (parseInt(b.size, 10) || 0) - (parseInt(a.size, 10) || 0);
  });

  const file = files[0];
  const path = String(file.name).split("/").map(encodeURIComponent).join("/");
  return { url: BASE + "/download/" + encodeURIComponent(id) + "/" + path };
}
