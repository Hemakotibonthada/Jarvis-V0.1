"""
Web Server — Serves the JARVIS Control Board UI.
Simple aiohttp static file server alongside the WebSocket server.
"""

import logging
from pathlib import Path
from aiohttp import web

logger = logging.getLogger("Jarvis.Web")

WEB_DIR = Path(__file__).parent.parent / "web"

MIME_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


async def handle_root(request):
    return await serve_file("index.html")


async def handle_static(request):
    filename = request.match_info.get("filename", "index.html")
    return await serve_file(filename)


async def serve_file(filename: str):
    file_path = (WEB_DIR / filename).resolve()

    # Security: ensure we don't serve files outside WEB_DIR
    if not str(file_path).startswith(str(WEB_DIR.resolve())):
        return web.Response(status=403, text="Forbidden")

    if not file_path.exists() or not file_path.is_file():
        return web.Response(status=404, text="Not found")

    content_type = MIME_TYPES.get(file_path.suffix, "application/octet-stream")
    content = file_path.read_bytes()

    return web.Response(
        body=content,
        content_type=content_type,
        headers={"Cache-Control": "no-cache"},
    )


async def start_web_server(port: int = 8080):
    """Start the HTTP server for the web UI. Returns the runner for cleanup."""
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/{filename:.+}", handle_static)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"Web UI serving at http://0.0.0.0:{port}")
    return runner
