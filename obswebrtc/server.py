"""Lightweight aiohttp server running on its own thread + event loop.

OBS calls script functions on its own thread, so the server must never block
it: start() returns once the sockets are bound, stop() shuts down cleanly.

Two listeners share one app:
  - HTTP on 127.0.0.1 for OBS Browser Sources (no certificate needed)
  - HTTPS on all interfaces for phones (browsers require HTTPS for cameras)
"""

import asyncio
import json
import ssl
import threading
from pathlib import Path

from aiohttp import WSMsgType, web

from .certs import ensure_certificate
from .log import get_logger
from .netinfo import lan_ips
from .qr import qr_svg
from .rooms import Rooms

log = get_logger("server")

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_CERT_DIR = Path(__file__).parent.parent / "certs"
ROOMS = web.AppKey("rooms", Rooms)
INFO = web.AppKey("info", dict)


async def sender_page(request):
    return web.FileResponse(STATIC_DIR / "sender.html")


async def viewer_page(request):
    return web.FileResponse(STATIC_DIR / "viewer.html")


async def help_page(request):
    return web.FileResponse(STATIC_DIR / "help.html")


async def info_api(request):
    rooms, info = request.app[ROOMS], request.app[INFO]
    return web.json_response({
        "phoneUrls": info["phone_urls"],
        "viewerUrls": info["viewer_urls"],
        "localUrl": info["local_url"],
        "httpsPort": info["https_port"],
        "customCert": info["custom_cert"],
        "maxCameras": rooms.max_cameras,
        "bufferMs": rooms.buffer_ms,
    })


async def qr_api(request):
    urls = request.app[INFO]["phone_urls"]
    index = int(request.match_info["index"])
    if index >= len(urls):
        raise web.HTTPNotFound()
    return web.Response(body=qr_svg(urls[index]), content_type="image/svg+xml")


async def config(request):
    rooms = request.app[ROOMS]
    return web.json_response({"maxCameras": rooms.max_cameras, "activeCams": rooms.active_cams(),
                              "bufferMs": rooms.buffer_ms})


async def health(request):
    return web.json_response({"status": "ok", "clients": len(request.app[ROOMS].peers)})


async def websocket(request):
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    rooms = request.app[ROOMS]
    peer = rooms.connect(ws)

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except ValueError:
                data = None
            if not isinstance(data, dict):
                await ws.send_json({"type": "error", "error": "expected a JSON object"})
                continue
            await rooms.handle(peer, data)
    finally:
        await rooms.disconnect(peer)
    return ws


async def _close_clients(app):
    for peer in list(app[ROOMS].peers.values()):
        await peer.ws.close(code=1001, message=b"server shutdown")


async def _no_cache(request, response):
    # Phones cache aggressively; always revalidate so page updates show up.
    response.headers.setdefault("Cache-Control", "no-cache")


def create_app(max_cameras=5, info=None, buffer_ms=0):
    app = web.Application()
    app[ROOMS] = Rooms(max_cameras, buffer_ms)
    app[INFO] = info or {"phone_urls": [], "viewer_urls": [], "local_url": "",
                         "https_port": None, "custom_cert": False}
    app.router.add_get("/", sender_page)
    app.router.add_get("/view", viewer_page)
    app.router.add_get("/help", help_page)
    app.router.add_get("/connect", help_page)  # old name
    app.router.add_get("/api/config", config)
    app.router.add_get("/api/info", info_api)
    app.router.add_get(r"/api/qr/{index:\d+}", qr_api)
    app.router.add_get("/health", health)
    app.router.add_get("/ws", websocket)
    app.router.add_static("/static", STATIC_DIR)
    app.on_shutdown.append(_close_clients)
    app.on_response_prepare.append(_no_cache)
    return app


class SignalingServer:
    def __init__(self, port=8080, max_cameras=5, https_port=None,
                 cert_dir=DEFAULT_CERT_DIR, host="127.0.0.1", buffer_ms=0):
        self.host = host
        self.port = port
        self.max_cameras = max_cameras
        self.buffer_ms = buffer_ms
        self._rooms = None
        self.https_port = https_port
        self.cert_dir = cert_dir
        self.phone_urls = []
        self.custom_cert = False
        self._ssl_context = None
        self._loop = None
        self._thread = None
        self._runner = None
        self._started = threading.Event()
        self._start_error = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def local_url(self):
        return f"http://127.0.0.1:{self.port}"

    def viewer_urls(self):
        return [f"{self.local_url}/view?cam={i}" for i in range(1, self.max_cameras + 1)]

    def start(self, timeout=5.0):
        if self.running:
            return
        self._prepare_https()
        self._started.clear()
        self._start_error = None
        self._thread = threading.Thread(target=self._run, name="obswebrtc-server", daemon=True)
        self._thread.start()
        if not self._started.wait(timeout):
            raise TimeoutError("server did not start in time")
        if self._start_error is not None:
            self._thread.join()
            self._thread = None
            raise self._start_error
        log.info("OBS: %s/view?cam=1..%d", self.local_url, self.max_cameras)
        if self.https_port:
            log.info("Phones: %s", ", ".join(self.phone_urls) or f"https://<this-pc>:{self.https_port}")

    def set_buffer_ms(self, buffer_ms):
        """Change the viewers' jitter buffer target live, without dropping streams."""
        if buffer_ms == self.buffer_ms:
            return
        self.buffer_ms = buffer_ms
        if self.running and self._rooms is not None:
            asyncio.run_coroutine_threadsafe(self._rooms.set_buffer_ms(buffer_ms), self._loop)
        log.info("Buffer target: %s", f"{buffer_ms} ms" if buffer_ms else "adaptive")

    def _prepare_https(self):
        self.phone_urls = []
        self._ssl_context = None
        if not self.https_port:
            return
        ips = lan_ips()
        cert, key, self.custom_cert = ensure_certificate(self.cert_dir, ips)
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(cert, key)
        self._ssl_context = ctx
        self.phone_urls = [f"https://{ip}:{self.https_port}" for ip in ips]

    def stop(self, timeout=5.0):
        if not self.running:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout)
        if self._thread.is_alive():
            log.warning("Server thread did not exit within %.1fs", timeout)
        self._thread = None
        log.info("Server stopped")

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._startup())
        except Exception as e:
            self._start_error = e
            self._started.set()
            loop.close()
            return

        self._started.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(self._runner.cleanup())
            loop.close()

    async def _startup(self):
        info = {"phone_urls": self.phone_urls, "viewer_urls": self.viewer_urls(),
                "local_url": self.local_url, "https_port": self.https_port,
                "custom_cert": self.custom_cert}
        app = create_app(self.max_cameras, info, self.buffer_ms)
        self._rooms = app[ROOMS]
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        sites = [web.TCPSite(self._runner, self.host, self.port)]
        if self._ssl_context is not None:
            sites.append(web.TCPSite(self._runner, "0.0.0.0", self.https_port,
                                     ssl_context=self._ssl_context))
        try:
            for site in sites:
                await site.start()
        except Exception:
            await self._runner.cleanup()
            raise
