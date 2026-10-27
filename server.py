"""
Servidor puente de Videogram.
Usa tu cuenta de Telegram (Telethon) para buscar videos en los canales/grupos
que indiques y servirlos por HTTP con soporte de Range (adelantar/retroceder).

Variables de entorno:
  TG_API_ID, TG_API_HASH   -> las sacas en https://my.telegram.org (API development tools)
  CHATS                    -> canales/grupos separados por coma (@usuario o id numérico)
  TOKEN                    -> una clave larga que tú inventas (la misma va en Kino)
  PORT                     -> opcional, por defecto 8080

Instalar:  pip install telethon aiohttp
Ejecutar:  python server.py   (la primera vez pide tu teléfono y el código de Telegram)
"""
import os
import re

from aiohttp import web
from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterVideo

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
TOKEN = os.environ.get("TOKEN", "")
CHATS = [c.strip() for c in os.environ.get("CHATS", "").split(",") if c.strip()]
PORT = int(os.environ.get("PORT", "8080"))
CHUNK = 1024 * 1024

client = TelegramClient("videogram", API_ID, API_HASH)


def check_auth(req):
    if TOKEN and req.headers.get("Authorization") != "Bearer " + TOKEN:
        raise web.HTTPUnauthorized()


def entity_of(chat):
    return int(chat) if re.fullmatch(r"-?\d+", chat) else chat


async def search(req):
    check_auth(req)
    q = req.query.get("q", "").strip()
    out = []
    for chat in CHATS:
        try:
            async for m in client.iter_messages(
                entity_of(chat), search=q, filter=InputMessagesFilterVideo, limit=20
            ):
                if not m.file:
                    continue
                first_line = (m.message or "").strip().split("\n")[0]
                title = first_line or (m.file.name or "Video")
                out.append({"id": f"{m.chat_id}_{m.id}", "title": title[:200]})
        except Exception as e:  # un canal que falla no tumba los demás
            print("error buscando en", chat, e)
    return web.json_response(out[:100])


async def stream(req):
    check_auth(req)
    try:
        chat, msg = req.match_info["id"].rsplit("_", 1)
        m = await client.get_messages(int(chat), ids=int(msg))
    except Exception:
        raise web.HTTPNotFound()
    if not m or not m.file:
        raise web.HTTPNotFound()

    size = m.file.size
    start, end, status = 0, size - 1, 200
    rng = req.headers.get("Range")
    if rng:
        mm = re.match(r"bytes=(\d*)-(\d*)", rng)
        if mm:
            if mm.group(1):
                start = int(mm.group(1))
            if mm.group(2):
                end = min(int(mm.group(2)), size - 1)
            if start > end:
                raise web.HTTPRequestRangeNotSatisfiable()
            status = 206

    headers = {
        "Content-Type": m.file.mime_type or "video/mp4",
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    resp = web.StreamResponse(status=status, headers=headers)
    await resp.prepare(req)

    aligned = start - (start % CHUNK)
    skip = start - aligned
    remaining = end - start + 1
    try:
        async for chunk in client.iter_download(m.media, offset=aligned, request_size=CHUNK):
            if skip:
                chunk = chunk[skip:]
                skip = 0
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
            await resp.write(chunk)
            remaining -= len(chunk)
            if remaining <= 0:
                break
    except (ConnectionResetError, web.HTTPException):
        pass  # el reproductor cerró la conexión
    return resp


async def on_start(app):
    await client.start()
    await client.get_dialogs()  # para que Telethon conozca tus canales


def main():
    app = web.Application()
    app.add_routes([web.get("/search", search), web.get("/stream/{id}", stream)])
    app.on_startup.append(on_start)
    web.run_app(app, port=PORT)


if __name__ == "__main__":
    main()
